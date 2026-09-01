import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchRoute, type RouteVariant } from '../api/route';
import type { LatLon } from '../lib/coords';
import type { ViaPoint } from '../routing/constants';
import type {
  NavCameraMode,
  OffRouteEvent,
  RouteProgressEvent,
} from '../native/maplibreNav';
import type { AlertPush } from '../alerts/useAlertPill';
import {
  cyclewayLineJson,
  initialBearing,
  routeLineJson,
  trafficLineJson,
} from './navGeo';
import { flatIndexOf, flattenNavSteps, remainingViaIndices } from './navSteps';
import type { NavigationPayload } from './types';

const SIMULATE = (process.env.EXPO_PUBLIC_NAV_SIMULATE || '').trim() === '1';
/** Ignore fresh off-route reports right after a successful replan. */
const REROUTE_COOLDOWN_MS = 4_000;
const REROUTE_FAIL_COOLDOWN_MS = 8_000;
const REROUTE_BACKOFF_MS = [0, 1_500, 3_000];
/** Force-clear if a fetch hangs so later deviations are not ignored forever. */
const REROUTE_STUCK_MS = 25_000;
const REROUTE_WATCHDOG_MS = 2_500;
/** Match native ENTER_M — keep replanning while the rider stays off the line. */
const WATCHDOG_OFF_ROUTE_M = 22;
/**
 * Inside this distance of the destination a deviation is the last few metres to a
 * door, not a wrong turn, so replanning would only fight the rider.
 */
const NO_REROUTE_NEAR_END_M = 60;
/** Matches MAX_AVOID_POINTS in app.py — the server rejects a longer list. */
const MAX_AVOID_POINTS = 5;

type Progress = {
  legIndex: number;
  stepIndex: number;
  /** Step whose maneuver is coming up — the one the banner and voice announce. */
  upcomingLegIndex: number;
  upcomingStepIndex: number;
  stepDistanceRemaining: number;
  distanceRemaining: number;
  durationRemaining: number;
  distanceFromRoute: number;
  latitude?: number;
  longitude?: number;
};

type Session = {
  directionsJson: string;
  navigation: NavigationPayload;
  routeGeoJson: string;
  trafficGeoJson: string;
  cyclewayGeoJson: string;
  origin: LatLon;
  bearing: number;
};

type Args = {
  start: LatLon | null;
  end: LatLon | null;
  vias: ViaPoint[];
  profileId: string | null;
  bikeType: string;
  userLocation: LatLon | null;
  /** Spoken units follow the same preference as the on-screen figures. */
  units?: 'metric' | 'imperial';
  pushAlert: (alert: AlertPush) => void;
  dismissAlert: (types?: string | string[]) => void;
};

/** Seed state before the engine reports, so the banner has the first turn to show. */
function initialProgress(navigation: NavigationPayload): Progress {
  const firstStep = navigation.legs?.[0]?.steps?.[0];
  return {
    legIndex: 0,
    stepIndex: 0,
    upcomingLegIndex: 0,
    upcomingStepIndex: (navigation.legs?.[0]?.steps?.length || 0) > 1 ? 1 : 0,
    stepDistanceRemaining: firstStep?.distance || 0,
    distanceRemaining: navigation.distance || 0,
    durationRemaining: navigation.duration || 0,
    distanceFromRoute: 0,
  };
}

function buildSession(
  navigation: NavigationPayload,
  directions: Record<string, unknown>,
  variant: RouteVariant | null,
): Session | null {
  const path = navigation.geometry_latlon || variant?.path || null;
  if (!path || path.length < 2) return null;
  const routes = (directions as { routes?: unknown[] }).routes;
  if (!Array.isArray(routes) || routes.length === 0) return null;
  return {
    directionsJson: JSON.stringify(directions),
    navigation,
    routeGeoJson: routeLineJson(path),
    trafficGeoJson: trafficLineJson(variant as Record<string, unknown> | null),
    cyclewayGeoJson: cyclewayLineJson(variant as Record<string, unknown> | null),
    origin: [path[0][0], path[0][1]],
    bearing: initialBearing(path),
  };
}

/**
 * Owns a turn-by-turn session: fetches the navigable route, mirrors engine
 * progress into React state, and replans through Flask when the rider drifts.
 */
export function useNavSession({
  start,
  end,
  vias,
  profileId,
  bikeType,
  userLocation,
  units = 'metric',
  pushAlert,
  dismissAlert,
}: Args) {
  const [session, setSession] = useState<Session | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [rerouting, setRerouting] = useState(false);
  const [tracking, setTracking] = useState(true);
  const [muted, setMuted] = useState(false);
  const [cyclewaysVisible, setCyclewaysVisible] = useState(true);
  const [cameraMode, setCameraMode] = useState<NavCameraMode>('follow');
  const [cameraNonce, setCameraNonce] = useState(0);
  const [bannerExpanded, setBannerExpanded] = useState(false);
  const [fallback, setFallback] = useState<NavigationPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  const progressRef = useRef<Progress | null>(null);
  /**
   * Whole native event, not the UI subset. A ride report needs the fix quality
   * and step indices that `Progress` deliberately drops.
   */
  const lastProgressRef = useRef<RouteProgressEvent | null>(null);
  /** Survives reroutes — "how long into this ride" is what a report wants. */
  const sessionStartedAtRef = useRef<number | null>(null);
  const reroutingRef = useRef(false);
  const cooldownUntilRef = useRef(0);
  const activeRef = useRef(false);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastFixRef = useRef<LatLon | null>(null);
  /** Places reported impassable this session; sent with every later reroute. */
  const avoidPointsRef = useRef<LatLon[]>([]);
  const userLocationRef = useRef(userLocation);
  const legRef = useRef({ end, vias, profileId, bikeType, units });

  legRef.current = { end, vias, profileId, bikeType, units };
  progressRef.current = progress;
  activeRef.current = Boolean(session);
  userLocationRef.current = userLocation;

  const steps = useMemo(() => flattenNavSteps(session?.navigation), [session]);
  /**
   * The maneuver being ridden towards. The engine's own step index points at the step
   * in progress, whose maneuver is already behind the rider, so pairing that with
   * `stepDistanceRemaining` would count down to one turn while naming the previous one.
   */
  const upcomingIndex = progress
    ? flatIndexOf(steps, progress.upcomingLegIndex, progress.upcomingStepIndex)
    : Math.min(1, Math.max(0, steps.length - 1));

  const clearRetry = useCallback(() => {
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    retryTimerRef.current = null;
  }, []);

  useEffect(() => clearRetry, [clearRetry]);

  const stop = useCallback(() => {
    clearRetry();
    reroutingRef.current = false;
    activeRef.current = false;
    lastFixRef.current = null;
    lastProgressRef.current = null;
    sessionStartedAtRef.current = null;
    avoidPointsRef.current = [];
    setSession(null);
    setProgress(null);
    setRerouting(false);
    setTracking(true);
    setBannerExpanded(false);
    setCameraMode('follow');
    setError(null);
  }, [clearRetry]);

  const startSession = useCallback(async () => {
    const origin = start || userLocation;
    const target = legRef.current.end;
    if (!origin || !target) return;
    setBusy(true);
    setError(null);
    dismissAlert();
    try {
      const result = await fetchRoute({
        start: origin,
        end: target,
        vias: legRef.current.vias.map((v) => v.coord),
        profileId: legRef.current.profileId,
        bikeType: legRef.current.bikeType,
        navigate: true,
        voiceUnits: legRef.current.units,
        purpose: 'commit',
      });
      if (!result.ok) {
        setError(result.error);
        pushAlert({ type: 'error', message: result.error });
        return;
      }
      const navigation = result.data.navigation || null;
      const directions = result.data.directions || null;
      if (!navigation || navigation.error || !directions) {
        const message = navigation?.error || 'Could not build turn-by-turn for this route';
        setError(message);
        setFallback(navigation);
        pushAlert({ type: 'warning', message });
        return;
      }
      const next = buildSession(navigation, directions, result.data.safest || null);
      if (!next) {
        setError('Route has no navigable geometry');
        setFallback(navigation);
        return;
      }
      setProgress(initialProgress(navigation));
      setCameraMode('follow');
      setTracking(true);
      setBannerExpanded(false);
      sessionStartedAtRef.current = Date.now();
      setSession(next);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      pushAlert({ type: 'error', message });
    } finally {
      setBusy(false);
    }
  }, [start, userLocation, pushAlert, dismissAlert]);

  const runReroute = useCallback(async (from: LatLon, attempt: number) => {
    const {
      end: target,
      vias: viaList,
      profileId: pid,
      bikeType: bt,
      units: voiceUnits,
    } = legRef.current;
    if (!target || !activeRef.current) {
      reroutingRef.current = false;
      setRerouting(false);
      return;
    }
    const legIndex = progressRef.current?.legIndex ?? 0;
    const remaining = remainingViaIndices(legIndex, viaList.length)
      .map((i) => viaList[i]?.coord)
      .filter((c): c is LatLon => Array.isArray(c));

    try {
      const result = await fetchRoute({
        start: from,
        end: target,
        vias: remaining,
        profileId: pid,
        bikeType: bt,
        navigate: true,
        voiceUnits,
        purpose: 'commit',
        avoidPoints: avoidPointsRef.current.length ? avoidPointsRef.current : undefined,
      });
      if (!activeRef.current) {
        reroutingRef.current = false;
        setRerouting(false);
        return;
      }
      const navigation = result.ok ? result.data.navigation : null;
      const directions = result.ok ? result.data.directions : null;
      const next = navigation && directions && !navigation.error
        ? buildSession(navigation, directions, result.ok ? result.data.safest || null : null)
        : null;

      // The rider may have rejoined the old line while this was in flight.
      if (!reroutingRef.current) return;

      if (next) {
        setSession(next);
        setProgress(initialProgress(navigation!));
        reroutingRef.current = false;
        setRerouting(false);
        cooldownUntilRef.current = Date.now() + REROUTE_COOLDOWN_MS;
        dismissAlert('warning');
        pushAlert({ type: 'info', message: 'Route updated' });
        return;
      }

      if (attempt + 1 < REROUTE_BACKOFF_MS.length) {
        pushAlert({ type: 'warning', message: 'Still rerouting…' });
        clearRetry();
        retryTimerRef.current = setTimeout(
          () => { void runReroute(from, attempt + 1); },
          REROUTE_BACKOFF_MS[attempt + 1],
        );
        return;
      }
      reroutingRef.current = false;
      setRerouting(false);
      cooldownUntilRef.current = Date.now() + REROUTE_FAIL_COOLDOWN_MS;
      pushAlert({ type: 'warning', message: 'Could not reroute — keep to the original line' });
    } catch {
      if (!activeRef.current) {
        reroutingRef.current = false;
        setRerouting(false);
        return;
      }
      if (attempt + 1 < REROUTE_BACKOFF_MS.length) {
        clearRetry();
        retryTimerRef.current = setTimeout(
          () => { void runReroute(from, attempt + 1); },
          REROUTE_BACKOFF_MS[attempt + 1],
        );
        return;
      }
      reroutingRef.current = false;
      setRerouting(false);
      cooldownUntilRef.current = Date.now() + REROUTE_FAIL_COOLDOWN_MS;
      pushAlert({ type: 'warning', message: 'Could not reroute — keep to the original line' });
    }
  }, [pushAlert, dismissAlert, clearRetry]);

  const beginReroute = useCallback((from: LatLon) => {
    if (reroutingRef.current || !activeRef.current) return;
    if (Date.now() < cooldownUntilRef.current) return;
    const remaining = progressRef.current?.distanceRemaining;
    if (typeof remaining === 'number' && remaining <= NO_REROUTE_NEAR_END_M) return;
    reroutingRef.current = true;
    setRerouting(true);
    void runReroute(from, 0);
  }, [runReroute]);

  /**
   * Route around a place the rider just reported impassable.
   *
   * Reuses the off-route machinery, so the grey line and the existing
   * "Rerouting…" banner cover it. The point stays on the avoid list for the
   * rest of the session: a locked gate does not open because we asked twice.
   * On failure the original line simply stays; the report is already saved.
   */
  const replanAvoiding = useCallback((point: LatLon) => {
    if (!activeRef.current) return;
    if (avoidPointsRef.current.length >= MAX_AVOID_POINTS) {
      avoidPointsRef.current.shift();
    }
    avoidPointsRef.current = [...avoidPointsRef.current, point];
    // Bypass the cooldown: the rider is stopped at a barrier, not drifting.
    cooldownUntilRef.current = 0;
    const from = lastFixRef.current || userLocationRef.current || point;
    if (reroutingRef.current) return;
    reroutingRef.current = true;
    setRerouting(true);
    void runReroute(from, 0);
  }, [runReroute]);

  useEffect(() => {
    if (!rerouting) return;
    const t = setTimeout(() => {
      if (!reroutingRef.current) return;
      reroutingRef.current = false;
      setRerouting(false);
    }, REROUTE_STUCK_MS);
    return () => clearTimeout(t);
  }, [rerouting]);

  useEffect(() => {
    if (!session) return;
    const id = setInterval(() => {
      if (reroutingRef.current || !activeRef.current) return;
      if (Date.now() < cooldownUntilRef.current) return;
      const remaining = progressRef.current?.distanceRemaining;
      if (typeof remaining === 'number' && remaining <= NO_REROUTE_NEAR_END_M) return;
      const dist = progressRef.current?.distanceFromRoute ?? 0;
      if (dist < WATCHDOG_OFF_ROUTE_M) return;
      const from = lastFixRef.current || userLocationRef.current;
      if (!from) return;
      beginReroute(from);
    }, REROUTE_WATCHDOG_MS);
    return () => clearInterval(id);
  }, [session, beginReroute]);

  const onRouteProgress = useCallback((event: {
    nativeEvent: RouteProgressEvent;
  }) => {
    const e = event.nativeEvent;
    lastProgressRef.current = e;
    if (Number.isFinite(e.latitude) && Number.isFinite(e.longitude)) {
      lastFixRef.current = [e.latitude, e.longitude];
    }
    setProgress({
      legIndex: e.legIndex,
      stepIndex: e.stepIndex,
      upcomingLegIndex: e.upcomingLegIndex ?? e.legIndex,
      upcomingStepIndex: e.upcomingStepIndex ?? e.stepIndex,
      stepDistanceRemaining: e.stepDistanceRemaining,
      distanceRemaining: e.distanceRemaining,
      durationRemaining: e.durationRemaining,
      distanceFromRoute: e.distanceFromRoute || 0,
      latitude: e.latitude,
      longitude: e.longitude,
    });
  }, []);

  const onOffRoute = useCallback((event: {
    nativeEvent: OffRouteEvent;
  }) => {
    lastFixRef.current = [event.nativeEvent.latitude, event.nativeEvent.longitude];
    beginReroute([event.nativeEvent.latitude, event.nativeEvent.longitude]);
  }, [beginReroute]);

  /**
   * Back on the line before the replan landed. Competitors drop the recalculation
   * here rather than forcing a new route onto a rider who corrected themselves.
   */
  const onRouteRejoined = useCallback(() => {
    if (!reroutingRef.current) return;
    clearRetry();
    reroutingRef.current = false;
    setRerouting(false);
    cooldownUntilRef.current = Date.now() + REROUTE_COOLDOWN_MS;
    dismissAlert('warning');
  }, [clearRetry, dismissAlert]);

  const onArrival = useCallback(() => {
    dismissAlert();
    pushAlert({ type: 'info', message: 'You have arrived' });
    stop();
  }, [pushAlert, dismissAlert, stop]);

  const onTrackingChanged = useCallback((event: {
    nativeEvent: { tracking: boolean };
  }) => {
    setTracking(event.nativeEvent.tracking);
  }, []);

  const onNavError = useCallback((event: { nativeEvent: { message: string } }) => {
    pushAlert({ type: 'error', message: event.nativeEvent.message });
  }, [pushAlert]);

  const recenter = useCallback(() => {
    setCameraMode('follow');
    setCameraNonce((n) => n + 1);
  }, []);

  const toggleOverview = useCallback(() => {
    setCameraMode((prev) => (prev === 'overview' ? 'follow' : 'overview'));
    setCameraNonce((n) => n + 1);
  }, []);

  return {
    active: Boolean(session),
    busy,
    simulate: SIMULATE,
    session,
    /** Latest raw engine event, for ride reports. Reads a ref — do not render off it. */
    getLastProgress: useCallback(() => lastProgressRef.current, []),
    getStartedAtMs: useCallback(() => sessionStartedAtRef.current, []),
    steps,
    upcomingIndex,
    progress,
    rerouting,
    tracking,
    muted,
    cyclewaysVisible,
    cameraMode,
    cameraNonce,
    bannerExpanded,
    fallback,
    error,
    startSession,
    stop,
    replanAvoiding,
    recenter,
    toggleOverview,
    setBannerExpanded,
    toggleMute: useCallback(() => setMuted((m) => !m), []),
    toggleCycleways: useCallback(() => setCyclewaysVisible((v) => !v), []),
    clearFallback: useCallback(() => {
      setFallback(null);
      setError(null);
    }, []),
    handlers: {
      onRouteProgress,
      onOffRoute,
      onRouteRejoined,
      onArrival,
      onTrackingChanged,
      onNavError,
    },
  };
}

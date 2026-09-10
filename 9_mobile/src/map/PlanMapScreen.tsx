import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Keyboard, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import Mapbox, {
  Camera,
  LineLayer,
  LocationPuck,
  MapView,
  ShapeSource,
  StyleImport,
} from '@rnmapbox/maps';
import * as Location from 'expo-location';
import { useAlertPill } from '../alerts/useAlertPill';
import { apiFetch } from '../api/flaskClient';
import { fetchRoute, type RouteLeg, type RouteVariant } from '../api/route';
import { NavigatePreviewSheet } from '../navigation/NavigatePreviewSheet';
import { NavInstructionBanner } from '../navigation/NavInstructionBanner';
import { NavMapControls } from '../navigation/NavMapControls';
import { useNavSession } from '../navigation/useNavSession';
import {
  flushRideReports,
  installFlushTriggers,
} from '../feedback/rideReportQueue';
import { useRideReport, type RideReportContext } from '../feedback/useRideReport';
import { TunedMaplibreNavView } from '../native/maplibreNav';
import { useAuth } from '../auth/AuthProvider';
import { useOnboardingOptional } from '../onboarding/OnboardingContext';
import {
  LONDON_CENTER,
  MAP_FIT_PAD,
  boundsFromLatLonPoints,
  boundsFromPaths,
  isInGreaterLondon,
  latLonToLngLat,
  lngLatToLatLon,
  pathToLineGeoJSON,
  type LatLon,
} from '../lib/coords';
import {
  DEFAULT_OVERLAY_MODE,
  availableOverlayModes,
  formatOverlayLength,
  sumChunkLengthM,
  trafficChunks,
} from '../map/overlayModes';
import { LINE_EMISSIVE, MAP_STYLE, lightPresetForTheme } from '../map/styles';
import { HireStationsLayer, HireExpandedHitChrome } from '../map/HireStationsLayer';
import { MultiLegRouteLayers } from '../map/MultiLegRouteLayers';
import { PointMarkers } from '../map/PointMarkers';
import {
  RouteOverlayLayers,
  type OverlayTapInfo,
} from '../map/RouteOverlayLayers';
import type { RouteHover } from '../map/routeHover';
import { useSantanderHire } from '../map/useSantanderHire';
import {
  BLOCKED,
  bikeLabel,
  coerceBikeForSantander,
  MAX_VIAS,
  type BikeTypeId,
  type ProfileRow,
  type ViaPoint,
} from '../routing/constants';
import { brand, dark, motion, routeColors, space } from '../theme/tokens';
import {
  loadActiveProfileId,
  writeActiveProfileId,
} from '../lib/prefs';
import type { DepartMode } from '../ui/DepartAtControl';
import { AlertPill } from '../ui/AlertPill';
import { DynamicIsland } from '../ui/island/DynamicIsland';
import { profileWantsLight, resolveIslandSlots } from '../ui/island/resolveIslandSlots';
import { MapControls } from '../ui/MapControls';
import { MapShell } from '../ui/MapShell';
import { RoutingCore } from '../ui/RoutingCore';
import { ProfileSidebar } from '../ui/sidebar/ProfileSidebar';
import { useSidebar } from '../ui/sidebar/SidebarContext';
import type { PickTarget, WaypointChange } from '../ui/WaypointFields';
import type { HireStation } from '../api/santander';

/** Snap back to north/flat if released within this many degrees. */
const NORTH_SNAP_DEG = 28;
/** North button active epsilon (web MapApiBridge). */
const NORTH_EPS = 0.5;

function normalizeBearing(deg: number) {
  let x = deg % 360;
  if (x > 180) x -= 360;
  if (x < -180) x += 360;
  return x;
}

const MAPBOX_TOKEN = (process.env.EXPO_PUBLIC_MAPBOX_TOKEN || '').trim();
if (MAPBOX_TOKEN) {
  Mapbox.setAccessToken(MAPBOX_TOKEN);
}
// Maps SDK 11 collects usage telemetry by default. The privacy labels declare
// no tracking and the app ships no ATT prompt, so it stays off on both
// platforms — see 0_documentation/tasks/IOS_TESTFLIGHT_BETA1.md.
Mapbox.setTelemetryEnabled(false);

function labelForCoord(c: LatLon) {
  return `${c[0].toFixed(4)}, ${c[1].toFixed(4)}`;
}

export function PlanMapScreen() {
  const { user, isLoading: authLoading, signOut } = useAuth();
  const onboarding = useOnboardingOptional();
  const markMapReady = onboarding?.markMapReady;
  const markProfilesReady = onboarding?.markProfilesReady;
  const publishTutorialSignals = onboarding?.publishTutorialSignals;
  const onboardingPhase = onboarding?.phase;
  const tutorialMapPass = onboarding?.tutorialMapPass === true;
  const mapGesturesEnabled = onboardingPhase !== 'tutorial' || tutorialMapPass;
  const {
    open,
    toggleSidebar,
    openSidebar,
    closeSidebar,
    units,
    themeMode: sidebarThemeMode,
    isDarkOutside,
    favouriteOrder,
    setFavouriteOrder,
  } = useSidebar();
  const themeMode = (
    onboarding && onboarding.phase !== 'done'
  ) ? onboarding.onboardingTheme : sidebarThemeMode;
  const cameraRef = useRef<Camera>(null);
  const mapRef = useRef<MapView>(null);
  const mapHostRef = useRef<View>(null);
  const { alert, push: pushAlert, dismiss: dismissAlert } = useAlertPill();

  const [pickTarget, setPickTarget] = useState<PickTarget>(null);
  const [start, setStart] = useState<LatLon | null>(null);
  const [end, setEnd] = useState<LatLon | null>(null);
  const [startLabel, setStartLabel] = useState('');
  const [endLabel, setEndLabel] = useState('');
  const [vias, setVias] = useState<ViaPoint[]>([]);
  const [profiles, setProfiles] = useState<ProfileRow[]>([]);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [activeProfile, setActiveProfile] = useState<ProfileRow | null>(null);
  const [bikeType, setBikeType] = useState<BikeTypeId>('standard');
  const [departMode, setDepartMode] = useState<DepartMode>('now');
  const [departAtIso, setDepartAtIso] = useState<string | null>(null);
  const departModeRef = useRef(departMode);
  const departAtIsoRef = useRef(departAtIso);
  useEffect(() => { departModeRef.current = departMode; }, [departMode]);
  useEffect(() => { departAtIsoRef.current = departAtIso; }, [departAtIso]);
  const [departIsDark, setDepartIsDark] = useState<boolean | null>(null);
  const [safest, setSafest] = useState<RouteVariant | null>(null);
  const [routeLegs, setRouteLegs] = useState<RouteLeg[] | null>(null);
  const [activeLegIndex, setActiveLegIndex] = useState(0);
  const [routeRevealed, setRouteRevealed] = useState(false);
  const [islandExpanded, setIslandExpanded] = useState(false);
  const [islandPage, setIslandPage] = useState(1);
  const [overlayMode, setOverlayMode] = useState<string | null>(DEFAULT_OVERLAY_MODE);
  const [overlayPulse, setOverlayPulse] = useState(false);
  const [busy, setBusy] = useState(false);
  const [locateActive, setLocateActive] = useState(false);
  const [locatePending, setLocatePending] = useState(false);
  const [userLocation, setUserLocation] = useState<LatLon | null>(null);
  const locateWatchRef = useRef<Location.LocationSubscription | null>(null);
  const [northNeedsReset, setNorthNeedsReset] = useState(false);
  const [overlayTap, setOverlayTap] = useState<OverlayTapInfo | null>(null);
  const [routeHover, setRouteHover] = useState<RouteHover | null>(null);
  const [hireCameraEpoch, setHireCameraEpoch] = useState(0);
  const overlayTapAtRef = useRef(0);
  const gestureWasActiveRef = useRef(false);
  const hireCamRafRef = useRef(0);
  /** Ignore heading updates while north-reset animation runs (keeps N pink). */
  const northResetUntilRef = useRef(0);
  const expandedStationIdRef = useRef<string | null>(null);

  const pickTargetRef = useRef<PickTarget>(null);
  const suppressPickClearUntilRef = useRef(0);

  useEffect(() => {
    pickTargetRef.current = pickTarget;
  }, [pickTarget]);

  const onMapPickTargetChange = useCallback((next: PickTarget) => {
    // After placing start, we auto-advance to 'end'. Blur from the start
    // field must not wipe that — otherwise destination needs two map taps.
    if (next == null && Date.now() < suppressPickClearUntilRef.current) return;
    setPickTarget(next);
  }, []);

  const routeRevealedRef = useRef(false);
  useEffect(() => {
    routeRevealedRef.current = routeRevealed;
  }, [routeRevealed]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (!user?.id) {
          markProfilesReady?.();
          return;
        }
        const storedId = await loadActiveProfileId();
        const res = await apiFetch('/profiles');
        const data = await res.json().catch(() => ({}));
        if (cancelled) return;
        if (!res.ok) return;
        const list: ProfileRow[] = Array.isArray(data.profiles) ? data.profiles : [];
        setProfiles(list);
        const preferred =
          (storedId && list.find((p) => p.id === storedId))
          || list.find((p) => p.id === 'preset_safe')
          || list.find((p) => /safe/i.test(p.name || ''))
          || list.find((p) => p.is_system)
          || list[0];
        if (preferred?.id) {
          setProfileId(preferred.id);
          const bt = preferred.bike_type;
          if (bt === 'road' || bt === 'ebike' || bt === 'cargo' || bt === 'standard') {
            setBikeType(bt);
          }
        }
      } catch {
        /* non-fatal */
      } finally {
        if (!cancelled) markProfilesReady?.();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user?.id, markProfilesReady]);

  useEffect(() => {
    const t = setTimeout(() => markMapReady?.(), 800);
    return () => clearTimeout(t);
  }, [markMapReady]);

  const reloadProfiles = useCallback(async () => {
    try {
      const res = await apiFetch('/profiles');
      const data = await res.json().catch(() => ({}));
      if (!res.ok) return;
      const list: ProfileRow[] = Array.isArray(data.profiles) ? data.profiles : [];
      setProfiles(list);
    } catch {
      /* non-fatal */
    }
  }, []);

  useEffect(() => {
    if (!profileId) return;
    void writeActiveProfileId(profileId);
  }, [profileId]);

  const multiLeg = Boolean(routeLegs && routeLegs.length > 1);
  const activeSafest = (multiLeg
    ? (routeLegs![activeLegIndex]?.safest || safest)
    : safest) as RouteVariant | null;
  const legCount = multiLeg ? routeLegs!.length : 1;

  const safestGeo = useMemo(() => pathToLineGeoJSON(safest?.path, { kind: 'safe' }), [safest]);

  useEffect(() => {
    if (!profileId) {
      setActiveProfile(null);
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch(`/profiles/${profileId}`);
        const data = await res.json().catch(() => ({}));
        if (cancelled || !res.ok) return;
        setActiveProfile(data as ProfileRow);
        const bt = data.bike_type;
        if (bt === 'road' || bt === 'ebike' || bt === 'cargo' || bt === 'standard') {
          setBikeType(bt);
        }
      } catch {
        /* non-fatal — fall back to list row */
        const row = profiles.find((p) => p.id === profileId) || null;
        if (!cancelled) setActiveProfile(row);
      }
    })();
    return () => { cancelled = true; };
  }, [profileId, user?.id]);

  /** Outdoor dark for overlays/CAE — depart-at can override live sun. */
  const isDarkForRouting = departIsDark != null ? departIsDark : isDarkOutside;

  useEffect(() => {
    if (departMode !== 'depart_at' || !departAtIso) {
      setDepartIsDark(null);
      return undefined;
    }
    let cancelled = false;
    const t = setTimeout(() => {
      (async () => {
        try {
          const res = await apiFetch(`/night_status?at=${encodeURIComponent(departAtIso)}`);
          const data = await res.json().catch(() => ({}));
          if (cancelled || !res.ok) return;
          setDepartIsDark(Boolean(data.is_dark));
        } catch {
          if (!cancelled) setDepartIsDark(null);
        }
      })();
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [departMode, departAtIso]);

  const overlayTouchedRef = useRef(false);
  const islandFitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const islandSlots = useMemo(
    () => resolveIslandSlots({
      safest: activeSafest as Record<string, unknown> | null,
      overlayMode,
      bikeType,
      isDarkOutside: isDarkForRouting,
      profile: activeProfile,
      maxBarCharts: 2,
      barBudget: 5,
    }),
    [activeSafest, overlayMode, bikeType, isDarkForRouting, activeProfile],
  );

  // At night, riders who want lit roads land on the light overlay by default
  useEffect(() => {
    if (!routeRevealed || overlayTouchedRef.current) return;
    if (isDarkForRouting && profileWantsLight(activeProfile)) {
      setOverlayMode('light');
    }
  }, [routeRevealed, isDarkForRouting, activeProfile]);

  // Drop light overlay when daytime / not allowed
  useEffect(() => {
    const allowed = new Set(availableOverlayModes(isDarkForRouting).map((m) => m.id));
    if (overlayMode && !allowed.has(overlayMode)) {
      setOverlayMode(null);
    }
  }, [isDarkForRouting, overlayMode]);

  useEffect(() => {
    // Web DynamicIslandZone: clear map↔island hover when switching legs.
    setRouteHover(null);
    setOverlayTap(null);
  }, [activeLegIndex]);

  const flyTo = useCallback((coord: LatLon) => {
    const ll = latLonToLngLat(coord);
    if (!ll || !cameraRef.current) return;
    cameraRef.current.setCamera({
      centerCoordinate: ll,
      animationDuration: motion.cameraMs,
    });
  }, []);

  const fitRoute = useCallback((
    paths: (number[][] | null | undefined)[],
    island: 'collapsed' | 'expanded' = 'collapsed',
  ) => {
    const viaPaths = vias.filter((v) => v.coord).map((v) => [v.coord!]);
    const bounds = boundsFromPaths([
      ...paths,
      start ? [start] : null,
      end ? [end] : null,
      ...viaPaths,
    ]);
    if (!bounds || !cameraRef.current) return;
    // Match web mobile padding; extra right clears overlay/locate chrome.
    const top = 190;
    const bottom = island === 'expanded' ? 270 : 148;
    cameraRef.current.fitBounds(
      bounds.ne,
      bounds.sw,
      [top, MAP_FIT_PAD.right, bottom, MAP_FIT_PAD.left],
      motion.fitMs,
    );
  }, [start, end, vias]);

  const fitHireStations = useCallback((anchor: LatLon | null, stations: HireStation[]) => {
    const pts: { lat: number; lon: number }[] = [];
    if (anchor) pts.push({ lat: anchor[0], lon: anchor[1] });
    (stations || []).forEach((s) => {
      if (Number.isFinite(s.lat) && Number.isFinite(s.lon)) {
        pts.push({ lat: s.lat, lon: s.lon });
      }
    });
    if (!pts.length || !cameraRef.current) return;
    if (pts.length === 1) {
      flyTo([pts[0].lat, pts[0].lon]);
      cameraRef.current.setCamera({
        centerCoordinate: [pts[0].lon, pts[0].lat],
        zoomLevel: 14.2,
        animationDuration: motion.fitMs,
      });
      return;
    }
    const bounds = boundsFromLatLonPoints(pts);
    if (!bounds) return;
    cameraRef.current.fitBounds(
      bounds.ne,
      bounds.sw,
      [210, MAP_FIT_PAD.right, 96, MAP_FIT_PAD.left],
      motion.fitMs,
    );
  }, [flyTo]);

  const clearRouteVisuals = useCallback(() => {
    setSafest(null);
    setRouteLegs(null);
    setActiveLegIndex(0);
    setRouteRevealed(false);
    setIslandExpanded(false);
    setOverlayMode(DEFAULT_OVERLAY_MODE);
    overlayTouchedRef.current = false;
    setOverlayTap(null);
    setRouteHover(null);
  }, []);

  const profileBikeType: BikeTypeId = (() => {
    const bt = profiles.find((p) => p.id === profileId)?.bike_type;
    if (bt === 'road' || bt === 'ebike' || bt === 'cargo' || bt === 'standard') return bt;
    return 'standard';
  })();

  const maybeAlertFarSnap = useCallback((meta: Record<string, unknown> | undefined) => {
    const snap = meta?.snap as {
      start?: { far?: boolean; distance_m?: number };
      end?: { far?: boolean; distance_m?: number };
      vias?: { far?: boolean; distance_m?: number }[];
    } | undefined;
    if (!snap) return;
    const parts: string[] = [];
    if (snap.start?.far) {
      parts.push(`start is ${formatOverlayLength(snap.start.distance_m || 0, units)}`);
    }
    if (Array.isArray(snap.vias)) {
      snap.vias.forEach((v, i) => {
        if (v?.far) parts.push(`stop ${i + 1} is ${formatOverlayLength(v.distance_m || 0, units)}`);
      });
    }
    if (snap.end?.far) {
      parts.push(`end is ${formatOverlayLength(snap.end.distance_m || 0, units)}`);
    }
    if (!parts.length) return;
    const detail = parts.length === 1
      ? `Mapped ${parts[0]} from the original location`
      : `Mapped locations are far from the originals (${parts.join('; ')})`;
    pushAlert({
      type: 'warning',
      message: `${detail}. Check accuracy. You can still use this route.`,
    });
  }, [pushAlert, units]);

  const maybeAlertTraffic = useCallback((variant: RouteVariant | null) => {
    const total = sumChunkLengthM(trafficChunks(variant as Record<string, unknown>));
    if (total <= 0) return;
    pushAlert({
      type: 'warning',
      message: `Traffic on this route — ${formatOverlayLength(total, units)}`,
    });
  }, [pushAlert, units]);

  const fitHireRoute = useCallback((
    walkA: number[][] | null,
    bikePath: number[][] | undefined,
    walkB: number[][] | null,
  ) => {
    fitRoute([walkA, bikePath, walkB], 'collapsed');
  }, [fitRoute]);

  const hire = useSantanderHire({
    start,
    end,
    profileId,
    bikeType,
    setBikeType,
    profileBikeType,
    pushAlert,
    dismissAlert,
    clearRouteVisuals,
    setSafest,
    setRouteRevealed,
    setOverlayMode,
    defaultOverlayMode: DEFAULT_OVERLAY_MODE,
    maybeAlertTraffic,
    maybeAlertFarSnap,
    fitHireStations,
    fitHireRoute,
    flyTo,
    setBusy,
  });

  const {
    santanderMode,
    hireStep,
    hireStations,
    pickupStation,
    dropoffStation,
    expandedStationId,
    walkStartPath,
    walkEndPath,
    hireWalkStats,
    hireNeed,
    mapBusyHire,
    islandSantander,
    resetHireState,
    beginPickupStep,
    handleStationExpand,
    handleStationConfirm,
    handleAlertAction,
    handleSantanderChange,
    santanderModeRef,
  } = hire;

  expandedStationIdRef.current = expandedStationId;

  const walkStartGeo = useMemo(
    () => pathToLineGeoJSON(walkStartPath, { kind: 'walk-start' }),
    [walkStartPath],
  );
  const walkEndGeo = useMemo(
    () => pathToLineGeoJSON(walkEndPath, { kind: 'walk-end' }),
    [walkEndPath],
  );

  const expandedHireStation = useMemo(() => {
    if (expandedStationId == null) return null;
    const id = String(expandedStationId);
    return hireStations.find((s) => String(s.id) === id)
      || (pickupStation && String(pickupStation.id) === id ? pickupStation : null)
      || (dropoffStation && String(dropoffStation.id) === id ? dropoffStation : null)
      || null;
  }, [expandedStationId, hireStations, pickupStation, dropoffStation]);

  useEffect(() => {
    if (expandedStationId == null) return;
    setHireCameraEpoch((n) => n + 1);
  }, [expandedStationId]);

  const clearRouteData = useCallback(() => {
    clearRouteVisuals();
    resetHireState();
  }, [clearRouteVisuals, resetHireState]);

  /** Clear planning chrome so the tutorial always starts from a clean default map. */
  const resetPlanningForTutorial = useCallback(() => {
    setStart(null);
    setEnd(null);
    setStartLabel('');
    setEndLabel('');
    setVias([]);
    setPickTarget(null);
    setDepartMode('now');
    setDepartAtIso(null);
    setIslandPage(1);
    dismissAlert();
    clearRouteData();
    if (santanderModeRef.current) {
      handleSantanderChange(false, false);
    }
    const bike = (activeProfile?.bike_type as BikeTypeId) || 'standard';
    setBikeType(bike);
    cameraRef.current?.setCamera({
      centerCoordinate: LONDON_CENTER,
      zoomLevel: 11,
      heading: 0,
      pitch: 0,
      animationDuration: 850,
    });
  }, [
    clearRouteData, dismissAlert, activeProfile?.bike_type,
    handleSantanderChange, santanderModeRef,
  ]);

  const tutorialPhaseRef = useRef(onboardingPhase);
  useEffect(() => {
    const prev = tutorialPhaseRef.current;
    tutorialPhaseRef.current = onboardingPhase;
    if (onboardingPhase === 'tutorial' && prev !== 'tutorial') {
      resetPlanningForTutorial();
      closeSidebar();
    }
  }, [onboardingPhase, resetPlanningForTutorial, closeSidebar]);

  const projectToWindow = useCallback(async (lngLat: [number, number]) => {
    const map = mapRef.current as {
      getPointInView?: (c: number[]) => Promise<number[] | { x: number; y: number } | null>;
    } | null;
    if (!map?.getPointInView) return null;
    try {
      const point = await map.getPointInView(lngLat);
      if (!point) return null;
      let localX = 0;
      let localY = 0;
      if (Array.isArray(point) && point.length >= 2) {
        localX = Number(point[0]);
        localY = Number(point[1]);
      } else if (typeof point === 'object') {
        const obj = point as { x?: number; y?: number };
        localX = Number(obj.x);
        localY = Number(obj.y);
      }
      if (!Number.isFinite(localX) || !Number.isFinite(localY)) return null;

      return await new Promise<{ x: number; y: number } | null>((resolve) => {
        if (!mapHostRef.current) {
          resolve({ x: localX, y: localY });
          return;
        }
        mapHostRef.current.measureInWindow((x, y, w, h) => {
          // If host hasn't laid out yet, fall back to map-local coords.
          if (!(w > 0 && h > 0)) {
            resolve({ x: localX, y: localY });
            return;
          }
          resolve({ x: x + localX, y: y + localY });
        });
      });
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    if (!publishTutorialSignals) return;
    // Only push into onboarding context during tutorial — otherwise every
    // route/leg update re-renders the whole tree and makes leg switching lag.
    if (onboardingPhase !== 'tutorial') return;
    publishTutorialSignals({
      routeRevealed,
      overlayMode,
      islandExpanded,
      islandPage,
      start,
      end,
      activeProfileId: profileId,
      sessionBikeType: bikeType,
      sidebarOpen: open,
      safestPath: ((activeSafest as { path?: number[][] } | null)?.path) || null,
      projectToWindow,
    });
  }, [
    publishTutorialSignals, onboardingPhase, routeRevealed, overlayMode, islandExpanded, islandPage,
    start, end, profileId, bikeType, open, activeSafest, projectToWindow,
  ]);

  const runRoute = useCallback(async (s: LatLon, e: LatLon, viaList: ViaPoint[]) => {
    setBusy(true);
    dismissAlert();
    try {
      const result = await fetchRoute({
        start: s,
        end: e,
        vias: viaList.map((v) => v.coord),
        profileId,
        bikeType,
        departAtIso: departModeRef.current === 'depart_at' ? departAtIsoRef.current : null,
        purpose: 'commit',
      });
      if (!result.ok) {
        pushAlert({ type: 'error', message: result.error });
        clearRouteData();
        return;
      }
      const nextSafe = result.data.safest || null;
      const legs = Array.isArray(result.data.legs) && result.data.legs.length > 0
        ? result.data.legs
        : null;
      setSafest(nextSafe);
      setRouteLegs(legs);
      setActiveLegIndex(0);
      setRouteRevealed(Boolean(nextSafe));
      setIslandExpanded(false);
      setOverlayMode(DEFAULT_OVERLAY_MODE);
      maybeAlertFarSnap(result.data.meta as Record<string, unknown> | undefined);
      maybeAlertTraffic(nextSafe);
      if (departModeRef.current === 'depart_at' && departAtIsoRef.current) {
        const t = new Date(departAtIsoRef.current).getTime();
        if (Number.isFinite(t) && t - Date.now() > 30 * 60_000) {
          pushAlert({ type: 'warning', message: 'Live traffic not applied for future departures' });
        }
      }
      const legPaths = (legs || [])
        .map((leg) => leg?.safest?.path)
        .filter(Boolean) as number[][][];
      fitRoute(
        legPaths.length > 1
          ? legPaths
          : [nextSafe?.path],
        'collapsed',
      );
    } catch (err) {
      pushAlert({ type: 'error', message: err instanceof Error ? err.message : String(err) });
      clearRouteData();
    } finally {
      setBusy(false);
    }
  }, [
    profileId, bikeType, fitRoute, clearRouteData,
    pushAlert, dismissAlert, maybeAlertFarSnap, maybeAlertTraffic,
  ]);

  const onMapPress = useCallback((event: { geometry?: { coordinates?: number[] } }) => {
    // Tutorial: only allow map picks on the start/end step.
    if (onboardingPhase === 'tutorial' && !tutorialMapPass) return;
    // Ignore map press that immediately follows an overlay segment tap.
    if (Date.now() - overlayTapAtRef.current < 280) return;
    // Hire station selection owns the map — don't place waypoints.
    if (mapBusyHire) {
      pushAlert({ type: 'warning', message: BLOCKED.mapBusyHire });
      return;
    }

    const coords = event?.geometry?.coordinates;
    const latLon = lngLatToLatLon(coords || null);
    if (!latLon) return;

    // Clear overlay detail chip / island↔map hover on empty map tap.
    setOverlayTap(null);
    setRouteHover(null);

    // Web: map click only places a point while a field is focused.
    const target = pickTarget;
    if (!target) {
      Keyboard.dismiss();
      return;
    }

    clearRouteData();
    const label = labelForCoord(latLon);

    if (target === 'start') {
      setStart(latLon);
      setStartLabel(label);
      // Keep destination as the map-pick target; ignore blur-clear briefly.
      suppressPickClearUntilRef.current = Date.now() + 700;
      setPickTarget('end');
      flyTo(latLon);
      return;
    }
    if (target === 'end') {
      setEnd(latLon);
      setEndLabel(label);
      suppressPickClearUntilRef.current = 0;
      setPickTarget(null);
      Keyboard.dismiss();
      return;
    }
    if (typeof target === 'string' && target.startsWith('via:')) {
      const idx = Number(target.slice(4));
      if (!Number.isInteger(idx) || idx < 0) return;
      setVias((prev) =>
        prev.map((v, i) => (i === idx ? { ...v, coord: latLon, label } : v)),
      );
      suppressPickClearUntilRef.current = 0;
      setPickTarget(null);
      Keyboard.dismiss();
    }
  }, [pickTarget, clearRouteData, flyTo, mapBusyHire, onboardingPhase, tutorialMapPass, pushAlert]);

  const onOverlaySegmentTap = useCallback((info: OverlayTapInfo | null) => {
    if (onboardingPhase === 'tutorial' && !tutorialMapPass) return;
    overlayTapAtRef.current = Date.now();
    setOverlayTap(info);
    if (!info) {
      setRouteHover(null);
      return;
    }
    setRouteHover({
      source: 'map',
      modeId: info.kind === 'traffic' ? 'traffic' : (overlayMode || undefined),
      kind: info.kind,
      runId: info.runId || null,
    });
  }, [overlayMode, onboardingPhase, tutorialMapPass]);

  const onGetRoute = useCallback(async () => {
    // Match web: locate soft-fills start if the start field is empty.
    const effectiveStart =
      start || (locateActive && userLocation ? userLocation : null);
    if (!effectiveStart || !end) return;
    if (!start && locateActive && userLocation) {
      setStart(userLocation);
      setStartLabel('Current location');
    }
    setPickTarget(null);
    Keyboard.dismiss();
    if (santanderMode) {
      await beginPickupStep();
      return;
    }
    await runRoute(effectiveStart, end, vias);
  }, [
    start,
    end,
    vias,
    runRoute,
    santanderMode,
    beginPickupStep,
    locateActive,
    userLocation,
  ]);

  const stopLocate = useCallback(() => {
    locateWatchRef.current?.remove();
    locateWatchRef.current = null;
    setLocateActive(false);
    setUserLocation(null);
    setLocatePending(false);
  }, []);

  const applyLocatePosition = useCallback(
    (coords: { latitude: number; longitude: number }, opts?: { fly?: boolean }) => {
      const ll: LatLon = [coords.latitude, coords.longitude];
      if (!isInGreaterLondon(ll[0], ll[1])) {
        stopLocate();
        pushAlert({
          type: 'warning',
          message: 'Location is outside Greater London — routing here is not supported yet',
        });
        return false;
      }
      setUserLocation(ll);
      setLocateActive(true);
      if (opts?.fly) {
        flyTo(ll);
        cameraRef.current?.setCamera({
          centerCoordinate: latLonToLngLat(ll) || undefined,
          zoomLevel: 14,
          animationDuration: motion.cameraMs,
        });
      }
      return true;
    },
    [flyTo, pushAlert, stopLocate],
  );

  const watchLocation = useCallback(async () => {
    locateWatchRef.current?.remove();
    locateWatchRef.current = await Location.watchPositionAsync(
      {
        accuracy: Location.Accuracy.High,
        distanceInterval: 5,
        timeInterval: 2000,
      },
      (next) => {
        applyLocatePosition(next.coords);
      },
    );
  }, [applyLocatePosition]);

  const onLocateToggle = useCallback(async () => {
    if (locateActive) {
      stopLocate();
      return;
    }
    setLocatePending(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        pushAlert({ type: 'warning', message: 'Location permission denied' });
        stopLocate();
        return;
      }
      const pos = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.High,
      });
      const ok = applyLocatePosition(pos.coords, { fly: true });
      if (!ok) return;
      // Soft-fill start when empty so Get Route / markers work like web.
      if (!start) {
        const ll: LatLon = [pos.coords.latitude, pos.coords.longitude];
        setStart(ll);
        setStartLabel('Current location');
        if (!end) setPickTarget('end');
      }
      await watchLocation();
    } catch (err) {
      stopLocate();
      pushAlert({
        type: 'warning',
        message: err instanceof Error ? err.message : 'Could not get location',
      });
    } finally {
      setLocatePending(false);
    }
  }, [
    locateActive,
    stopLocate,
    pushAlert,
    applyLocatePosition,
    watchLocation,
    start,
    end,
  ]);

  useEffect(() => () => {
    locateWatchRef.current?.remove();
  }, []);

  /**
   * Cold start: if location was granted on a previous run we locate silently —
   * same deal as theme auto-detection. No permission prompt here.
   */
  const coldStartRef = useRef(false);
  useEffect(() => {
    if (coldStartRef.current) return undefined;
    if (onboardingPhase && onboardingPhase !== 'done') return undefined;
    coldStartRef.current = true;
    let cancelled = false;
    (async () => {
      try {
        const perm = await Location.getForegroundPermissionsAsync();
        if (cancelled || !perm.granted) return;
        const pos = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });
        if (cancelled) return;
        const ll: LatLon = [pos.coords.latitude, pos.coords.longitude];
        // Outside London stays on the London default — silently, no warning.
        if (!isInGreaterLondon(ll[0], ll[1])) return;
        setUserLocation(ll);
        setLocateActive(true);
        cameraRef.current?.setCamera({
          centerCoordinate: latLonToLngLat(ll) || undefined,
          zoomLevel: 14,
          animationDuration: motion.cameraMs,
        });
        setStart((prev) => prev || ll);
        setStartLabel((prev) => prev || 'Current location');
        await watchLocation();
      } catch {
        /* silent — planning still works from the London default */
      }
    })();
    return () => { cancelled = true; };
  }, [onboardingPhase, watchLocation]);

  const triggerOverlayPulse = useCallback(() => {
    setOverlayPulse(true);
    setTimeout(() => setOverlayPulse(false), 900);
  }, []);

  const fitCurrentRoute = useCallback((island: 'collapsed' | 'expanded') => {
    if (multiLeg && routeLegs) {
      const paths = routeLegs.flatMap((leg) => [
        leg?.safest?.path,
      ]);
      fitRoute(paths, island);
      return;
    }
    if (safest?.path) {
      fitRoute(
        [walkStartPath, safest.path, walkEndPath],
        island,
      );
    }
  }, [safest, fitRoute, walkStartPath, walkEndPath, multiLeg, routeLegs]);

  const onIslandExpandedChange = useCallback((expanded: boolean) => {
    setIslandExpanded(expanded);
    // Defer camera fit until after the island morph so JS layout + Mapbox
    // don't fight on the same frames (EXPAND_MS ≈ 380).
    if (islandFitTimerRef.current) clearTimeout(islandFitTimerRef.current);
    const delayMs = expanded ? 400 : 120;
    islandFitTimerRef.current = setTimeout(() => {
      islandFitTimerRef.current = null;
      fitCurrentRoute(expanded ? 'expanded' : 'collapsed');
    }, delayMs);
  }, [fitCurrentRoute]);

  const onChangeWaypoints = useCallback((next: WaypointChange) => {
    setStart(next.start);
    setEnd(next.end);
    setStartLabel(next.startLabel || '');
    setEndLabel(next.endLabel || '');
    setVias(next.vias || []);
    clearRouteData();
    if ((next.vias || []).length > 0 && santanderModeRef.current) {
      handleSantanderChange(false, false);
    }
  }, [clearRouteData, handleSantanderChange, santanderModeRef]);

  const onAddVia = useCallback(() => {
    if (vias.length >= MAX_VIAS) return;
    const nextIndex = vias.length;
    setVias((prev) => [...prev, { id: `via-${Date.now()}`, coord: null, label: '' }]);
    setPickTarget(`via:${nextIndex}`);
    clearRouteData();
  }, [vias.length, clearRouteData]);

  const onRemoveVia = useCallback((i: number) => {
    setVias((prev) => prev.filter((_, idx) => idx !== i));
    clearRouteData();
  }, [clearRouteData]);

  const onSelectProfile = useCallback((id: string) => {
    setProfileId(id);
    const p = profiles.find((row) => row.id === id);
    const bt = p?.bike_type;
    if (bt === 'road' || bt === 'ebike' || bt === 'cargo' || bt === 'standard') {
      const prev = bikeType;
      const next = santanderModeRef.current ? coerceBikeForSantander(bt) : bt;
      setBikeType(next);
      if (next !== prev) {
        pushAlert({
          type: 'bike_override',
          message: `Bike set to ${bikeLabel(next, Boolean(santanderModeRef.current))}`,
        });
      }
    }
    clearRouteData();
  }, [profiles, clearRouteData, bikeType, pushAlert]);

  const nav = useNavSession({
    start,
    end,
    vias,
    profileId,
    bikeType,
    userLocation,
    units,
    pushAlert,
    dismissAlert,
  });

  const navSession = nav.session;
  const navActive = Boolean(navSession);

  const rideReportContext = useCallback((): RideReportContext => {
    const progress = nav.getLastProgress();
    const step = nav.steps[nav.upcomingIndex];
    const path = (activeSafest as { path?: number[][] } | null)?.path || null;
    return {
      progress,
      fallbackLocation: userLocation,
      themeMode,
      nav: {
        rerouting: nav.rerouting,
        tracking: nav.tracking,
        overviewActive: nav.cameraMode === 'overview',
        muted: nav.muted,
        cyclewaysVisible: nav.cyclewaysVisible,
        maneuverType: step?.type ?? null,
        maneuverModifier: step?.modifier ?? null,
        maneuverInstruction: step?.instruction ?? null,
        stepName: step?.name ?? null,
        startedAtMs: nav.getStartedAtMs(),
      },
      route: {
        origin: start,
        destination: end,
        vias: vias.map((v) => v.coord),
        distance: (activeSafest as { distance?: number } | null)?.distance ?? null,
        duration: (activeSafest as { duration?: number } | null)?.duration ?? null,
        firstPoint: path?.[0] ? [path[0][1], path[0][0]] : null,
        lastPoint: path?.length
          ? [path[path.length - 1][1], path[path.length - 1][0]]
          : null,
        pointCount: path?.length ?? null,
      },
      profile: {
        profileId,
        preset: activeProfile?.id ?? null,
        bikeType,
        weights: (activeProfile?.weights as Record<string, number>) ?? null,
        userId: user?.id ?? null,
      },
      night: {
        isDark: isDarkForRouting,
        forcedMode: departIsDark != null ? 'depart_at' : null,
        departAtIso: departMode === 'depart_at' ? departAtIso : null,
      },
    };
  }, [
    nav, activeSafest, userLocation, themeMode, start, end, vias, profileId,
    activeProfile, bikeType, user?.id, isDarkForRouting, departIsDark,
    departMode, departAtIso,
  ]);

  const rideReport = useRideReport({
    isDark: isDarkForRouting,
    getContext: rideReportContext,
    pushAlert,
    replanAvoiding: nav.replanAvoiding,
  });

  // Ending nav mid-picker keeps the stub on disk and just drops the circles.
  const cancelPicker = rideReport.cancelPicker;
  useEffect(() => {
    if (!navActive) cancelPicker();
  }, [navActive, cancelPicker]);

  useEffect(() => installFlushTriggers(), []);
  useEffect(() => {
    if (!navActive) void flushRideReports('nav_end');
  }, [navActive]);
  useEffect(() => {
    if (user?.id) void flushRideReports('auth', { force: true });
  }, [user?.id]);

  // The planning map unmounts during navigation, so it comes back on its
  // default London camera — put the route back on screen when nav ends.
  const navWasActiveRef = useRef(false);
  useEffect(() => {
    const wasActive = navWasActiveRef.current;
    navWasActiveRef.current = navActive;
    if (!wasActive || navActive) return undefined;
    const id = setTimeout(() => fitCurrentRoute('collapsed'), 320);
    return () => clearTimeout(id);
  }, [navActive, fitCurrentRoute]);

  const onStartNavigate = useCallback(async () => {
    if (!routeRevealed || nav.busy) return;
    // Both platforms ask here. On iOS this is the When In Use prompt, raised in
    // the planner so beta 2 does not introduce a new permission moment.
    if (!nav.simulate) {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (!perm.granted) {
        pushAlert({
          type: 'warning',
          message: 'Location permission is required for navigation',
        });
        return;
      }
    }
    setIslandExpanded(false);
    setPickTarget(null);
    Keyboard.dismiss();
    await nav.startSession();
  }, [routeRevealed, nav, pushAlert]);

  const onDeleteProfile = useCallback(async (id: string) => {
    try {
      const res = await apiFetch(`/profiles/${id}`, { method: 'DELETE' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        pushAlert({ type: 'error', message: data.error || 'Could not delete profile.' });
        return;
      }
      setFavouriteOrder((prev) => prev.filter((x) => x !== id));
      await reloadProfiles();
      if (profileId === id) {
        const fallback = 'preset_safe';
        setProfileId(fallback);
        setBikeType('standard');
      }
      clearRouteData();
      pushAlert({ type: 'info', message: 'Profile deleted' });
    } catch {
      pushAlert({ type: 'error', message: 'Could not delete profile.' });
    }
  }, [profileId, pushAlert, reloadProfiles, setFavouriteOrder, clearRouteData]);

  const onProfileCreated = useCallback((profile: Record<string, unknown>) => {
    const id = String(profile.id || '');
    void reloadProfiles();
    if (id) {
      setProfileId(id);
      const bt = profile.bike_type;
      if (bt === 'road' || bt === 'ebike' || bt === 'cargo' || bt === 'standard') {
        setBikeType(bt);
      }
    }
    clearRouteData();
    pushAlert({ type: 'info', message: 'Profile created' });
  }, [reloadProfiles, clearRouteData, pushAlert]);

  useEffect(() => {
    const pending = onboarding?.pendingActivateProfile;
    if (!pending) return;
    onProfileCreated(pending);
    onboarding.consumePendingProfile();
  }, [onboarding?.pendingActivateProfile, onboarding, onProfileCreated]);

  const onProfileUpdated = useCallback((profile: Record<string, unknown>) => {
    const id = String(profile.id || '');
    void reloadProfiles();
    if (id) {
      setProfileId(id);
      const bt = profile.bike_type;
      if (bt === 'road' || bt === 'ebike' || bt === 'cargo' || bt === 'standard') {
        setBikeType(bt);
      }
    }
    clearRouteData();
    pushAlert({ type: 'info', message: 'Profile updated' });
  }, [reloadProfiles, clearRouteData, pushAlert]);

  const onBlocked = useCallback((msg: string) => {
    pushAlert({ type: 'warning', message: msg });
  }, [pushAlert]);

  const onSelectOverlayMode = useCallback((id: string | null) => {
    if (!routeRevealedRef.current) {
      pushAlert({ type: 'info', message: BLOCKED.overlayNeedsRoute });
      return;
    }
    overlayTouchedRef.current = true;
    setOverlayTap(null);
    setRouteHover(null);
    if (id == null) {
      setOverlayMode(null);
      return;
    }
    const chunks = (activeSafest as Record<string, unknown> | null)
      ? ((activeSafest as Record<string, unknown>)[
        id === 'hills' ? 'hill_typed'
          : id === 'cycle' ? 'cycle_typed'
            : id === 'green' ? 'green_typed'
              : id === 'surface' ? 'surface_typed'
                : id === 'light' ? 'light_typed'
                  : ''
      ] as unknown[])
      : [];
    if (Array.isArray(chunks) && chunks.length === 0 && id) {
      const emptyMsgs: Record<string, string> = {
        cycle: 'No cycleways found on this route',
        green: 'No attractions on this route',
        surface: 'No rough surfaces found',
        hills: 'No steep segments on this route',
        light: 'No lighting data on this route',
      };
      pushAlert({ type: 'info', message: emptyMsgs[id] || 'Nothing on this route' });
    }
    setOverlayMode(id);
  }, [activeSafest, pushAlert]);

  const onResetNorth = useCallback(() => {
    northResetUntilRef.current = Date.now() + 320;
    cameraRef.current?.setCamera({
      heading: 0,
      pitch: 0,
      animationDuration: 280,
    });
    setNorthNeedsReset(false);
  }, []);

  const onCameraChanged = useCallback((state: {
    properties?: { heading?: number; pitch?: number };
    gestures?: { isGestureActive?: boolean };
  }) => {
    // Invisible chrome hit targets only — confirm button itself is MarkerView-locked.
    if (expandedStationIdRef.current && !hireCamRafRef.current) {
      hireCamRafRef.current = requestAnimationFrame(() => {
        hireCamRafRef.current = 0;
        setHireCameraEpoch((n) => n + 1);
      });
    }

    const heading = normalizeBearing(state?.properties?.heading ?? 0);
    const pitch = state?.properties?.pitch ?? 0;

    // During programmatic north reset, keep N pink (don't flicker muted mid-tween).
    if (Date.now() < northResetUntilRef.current) {
      setNorthNeedsReset(false);
      return;
    }
    setNorthNeedsReset(Math.abs(heading) > NORTH_EPS || Math.abs(pitch) > NORTH_EPS);

    const active = Boolean(state?.gestures?.isGestureActive);
    if (active) {
      gestureWasActiveRef.current = true;
      return;
    }
    if (!gestureWasActiveRef.current) return;
    gestureWasActiveRef.current = false;

    // Near north/flat → snap back (requires a clearer twist to leave north-up).
    if (
      (Math.abs(heading) > 0 && Math.abs(heading) < NORTH_SNAP_DEG)
      || (Math.abs(pitch) > 0 && Math.abs(pitch) < NORTH_SNAP_DEG)
    ) {
      if (Math.abs(heading) < NORTH_SNAP_DEG && Math.abs(pitch) < NORTH_SNAP_DEG) {
        northResetUntilRef.current = Date.now() + 320;
        cameraRef.current?.setCamera({
          heading: 0,
          pitch: 0,
          animationDuration: 280,
        });
        setNorthNeedsReset(false);
      }
    }
  }, []);

  if (!MAPBOX_TOKEN) {
    return (
      <View style={styles.missingToken}>
        <Text style={styles.brand}>Tuned</Text>
        <Text style={styles.missingTitle}>Mapbox token missing</Text>
        <Text style={styles.missingBody}>
          Set EXPO_PUBLIC_MAPBOX_TOKEN in 9_mobile/.env, then rebuild with
          npx expo run:android
        </Text>
        <Pressable style={styles.signOut} onPress={() => signOut()}>
          <Text style={styles.signOutText}>Sign out</Text>
        </Pressable>
      </View>
    );
  }

  const map = (
    <View ref={mapHostRef} style={StyleSheet.absoluteFill} collapsable={false}>
      <MapView
        ref={mapRef}
        style={StyleSheet.absoluteFill}
        styleURL={MAP_STYLE}
        compassEnabled={false}
        logoEnabled={false}
        attributionEnabled
        scaleBarEnabled={false}
        scrollEnabled={mapGesturesEnabled}
        zoomEnabled={mapGesturesEnabled}
        pitchEnabled={mapGesturesEnabled}
        rotateEnabled={mapGesturesEnabled}
        onPress={onMapPress}
        onCameraChanged={onCameraChanged}
        onDidFinishLoadingMap={() => markMapReady?.()}
        onDidFailLoadingMap={() => markMapReady?.()}
      >
        <StyleImport
          id="basemap"
          existing
          config={{ lightPreset: lightPresetForTheme(themeMode) }}
        />
        <Camera
          ref={cameraRef}
          defaultSettings={{
            centerCoordinate: LONDON_CENTER,
            zoomLevel: 11,
          }}
          followUserLocation={locateActive}
          followZoomLevel={14}
        />

        {locateActive ? (
          <LocationPuck
            visible
            // Plan: blue dot only — no heading arrow. Nav Activity owns the chevron.
            puckBearingEnabled={false}
            androidRenderMode="normal"
            // Keep well under A/B badges (24px); previous 0.55 still read large on device.
            scale={0.32}
            pulsing={{ isEnabled: false }}
          />
        ) : null}
        {walkStartPath && walkStartPath.length > 1 && (
          <ShapeSource id="walk-start" shape={walkStartGeo}>
            <LineLayer
              id="walk-start-casing"
              style={{
                lineColor: '#ffffff',
                lineWidth: 13,
                lineOpacity: 1,
                lineCap: 'round',
                lineJoin: 'round',
                ...LINE_EMISSIVE,
              }}
            />
            <LineLayer
              id="walk-start-line"
              style={{
                lineColor: routeColors.profile,
                lineWidth: 5,
                lineOpacity: 1,
                lineCap: 'round',
                lineJoin: 'round',
                lineDasharray: [2.4, 2.4],
                ...LINE_EMISSIVE,
              }}
            />
          </ShapeSource>
        )}

        {walkEndPath && walkEndPath.length > 1 && (
          <ShapeSource id="walk-end" shape={walkEndGeo}>
            <LineLayer
              id="walk-end-casing"
              style={{
                lineColor: '#ffffff',
                lineWidth: 13,
                lineOpacity: 1,
                lineCap: 'round',
                lineJoin: 'round',
                ...LINE_EMISSIVE,
              }}
            />
            <LineLayer
              id="walk-end-line"
              style={{
                lineColor: routeColors.profile,
                lineWidth: 5,
                lineOpacity: 1,
                lineCap: 'round',
                lineJoin: 'round',
                lineDasharray: [1.8, 1.8],
                ...LINE_EMISSIVE,
              }}
            />
          </ShapeSource>
        )}

        {multiLeg && routeLegs ? (
          <MultiLegRouteLayers
            routeLegs={routeLegs}
            activeLegIndex={activeLegIndex}
            onSelectLeg={(i) => {
              overlayTapAtRef.current = Date.now();
              setActiveLegIndex(i);
            }}
          />
        ) : (
          <>
            {safest?.path && safest.path.length > 1 && (
              <ShapeSource id="safest" shape={safestGeo}>
                <LineLayer
                  id="safest-casing"
                  style={{
                    lineColor: '#ffffff',
                    lineWidth: 13,
                    lineOpacity: 1,
                    lineCap: 'round',
                    lineJoin: 'round',
                    ...LINE_EMISSIVE,
                  }}
                />
                <LineLayer
                  id="safest-line"
                  style={{
                    lineColor: routeColors.profile,
                    lineWidth: 5,
                    lineOpacity: 1,
                    lineCap: 'round',
                    lineJoin: 'round',
                    ...LINE_EMISSIVE,
                  }}
                />
              </ShapeSource>
            )}
          </>
        )}

        <RouteOverlayLayers
          safest={routeRevealed ? (activeSafest as Record<string, unknown> | null) : null}
          overlayMode={overlayMode}
          activeTap={overlayTap}
          onSegmentTap={onOverlaySegmentTap}
          externalHover={routeHover?.source === 'island' ? routeHover : null}
          aboveRouteLayerID={multiLeg ? `safe-${activeLegIndex}-line` : 'safest-line'}
        />

        <PointMarkers
          start={start}
          end={end}
          vias={vias}
          hideStart={locateActive && startLabel === 'Current location'}
        />

        <HireStationsLayer
          stations={hireStations}
          hireStep={hireStep}
          hireNeed={hireNeed}
          expandedId={expandedStationId}
          confirmLabel={hireStep === 'pickup' ? 'Pick up here' : 'Drop off here'}
          onConfirm={handleStationConfirm}
          pickupStation={pickupStation}
          dropoffStation={dropoffStation}
          onExpand={handleStationExpand}
        />
      </MapView>
    </View>
  );

  const islandVisible = Boolean(routeRevealed && activeSafest);
  // Location services on (or desk replay) + a revealed route = Navigate is live.
  const canNavigate = Boolean(
    routeRevealed && activeSafest && (locateActive || nav.simulate),
  );

  // useNavSession never opens a session without a guidance engine, so this is
  // belt and braces: an empty ExpoView must never replace the planning map.
  const navMap = navSession && Platform.OS === 'android' ? (
    <TunedMaplibreNavView
      style={StyleSheet.absoluteFill}
      directionsJson={navSession.directionsJson}
      routeGeoJson={navSession.routeGeoJson}
      trafficGeoJson={navSession.trafficGeoJson}
      cyclewayGeoJson={navSession.cyclewayGeoJson}
      themeMode={themeMode === 'light' ? 'light' : 'dark'}
      simulate={nav.simulate}
      muted={nav.muted}
      rerouting={nav.rerouting}
      cyclewaysVisible={nav.cyclewaysVisible}
      cameraMode={nav.cameraMode}
      cameraNonce={nav.cameraNonce}
      initialLatitude={navSession.origin[0]}
      initialLongitude={navSession.origin[1]}
      initialBearing={navSession.bearing}
      onRouteProgress={nav.handlers.onRouteProgress}
      onOffRoute={nav.handlers.onOffRoute}
      onRouteRejoined={nav.handlers.onRouteRejoined}
      onArrival={nav.handlers.onArrival}
      onTrackingChanged={nav.handlers.onTrackingChanged}
      onNavError={nav.handlers.onNavError}
    />
  ) : null;

  return (
    <>
    <MapShell
      map={navMap || map}
      islandExpanded={islandExpanded}
      themeMode={themeMode}
      mapOverlay={(
        (hireStep === 'pickup' || hireStep === 'dropoff') && expandedHireStation
          ? (
            <HireExpandedHitChrome
              mapRef={mapRef}
              station={expandedHireStation}
              cameraEpoch={hireCameraEpoch}
              confirmLabel={hireStep === 'pickup' ? 'Pick up here' : 'Drop off here'}
              onCollapse={() => handleStationExpand(expandedHireStation)}
              onConfirm={() => handleStationConfirm(expandedHireStation)}
            />
          )
          : null
      )}
      top={navActive ? (
        <NavInstructionBanner
          steps={nav.steps}
          upcomingIndex={nav.upcomingIndex}
          stepDistanceRemaining={nav.progress?.stepDistanceRemaining || 0}
          units={units}
          rerouting={nav.rerouting}
          expanded={nav.bannerExpanded}
          onExpandedChange={nav.setBannerExpanded}
        />
      ) : (
        <RoutingCore
          user={user}
          authLoading={authLoading}
          onAvatarPress={() => toggleSidebar()}
          onSignOut={() => signOut()}
          profiles={profiles}
          activeProfileId={profileId}
          onSelectProfile={onSelectProfile}
          favouriteOrder={favouriteOrder}
          onEditFavourites={() => openSidebar({ focus: 'profiles' })}
          bikeType={bikeType}
          onSelectBike={(id) => {
            setBikeType(id);
            clearRouteData();
          }}
          santanderMode={santanderMode}
          onSantanderChange={(on) => handleSantanderChange(on, vias.length > 0)}
          start={start}
          end={end}
          startLabel={startLabel}
          endLabel={endLabel}
          vias={vias}
          onChangeWaypoints={onChangeWaypoints}
          onAddVia={onAddVia}
          onRemoveVia={onRemoveVia}
          onFlyTo={flyTo}
          onMapPickTargetChange={onMapPickTargetChange}
          departMode={departMode}
          departAtIso={departAtIso}
          onDepartChange={({ mode, departAtIso: iso }) => {
            if (santanderMode && mode === 'depart_at') {
              pushAlert({ type: 'warning', message: BLOCKED.departNeedsNoSantander });
              return;
            }
            const modeChanged = mode !== departMode;
            setDepartMode(mode);
            setDepartAtIso(iso);
            departModeRef.current = mode;
            departAtIsoRef.current = iso;
            if (modeChanged) clearRouteData();
          }}
          onGetRoute={onGetRoute}
          isCalculating={busy || hireStep === 'routing'}
          onBlocked={onBlocked}
        />
      )}
      alert={<AlertPill alert={alert} onAction={(id) => handleAlertAction(id)} />}
      mapControls={navActive ? (
        <NavMapControls
          tracking={nav.tracking}
          onRecenter={nav.recenter}
          muted={nav.muted}
          onToggleMute={nav.toggleMute}
          cyclewaysVisible={nav.cyclewaysVisible}
          onToggleCycleways={nav.toggleCycleways}
          overviewActive={nav.cameraMode === 'overview'}
          onToggleOverview={nav.toggleOverview}
        />
      ) : (
        <View style={styles.mapControlsCol}>
          <MapControls
            locateActive={locateActive}
            locatePending={locatePending}
            onLocateToggle={onLocateToggle}
            northNeedsReset={northNeedsReset}
            onResetNorth={onResetNorth}
            routeRevealed={routeRevealed}
            overlayMode={overlayMode}
            isDark={isDarkForRouting}
            onSelectOverlayMode={onSelectOverlayMode}
            overlayPulse={overlayPulse}
            islandExpanded={islandExpanded}
          />
        </View>
      )}
      island={islandVisible ? (
        <DynamicIsland
          safest={activeSafest as Record<string, unknown>}
          slots={islandSlots}
          expanded={islandExpanded}
          onExpandedChange={onIslandExpandedChange}
          onOverlayHintClick={triggerOverlayPulse}
          overlayMode={overlayMode}
          routeHover={routeHover}
          onIslandHover={setRouteHover}
          santander={islandSantander}
          pickupStation={pickupStation}
          dropoffStation={dropoffStation}
          walkStats={hireWalkStats}
          legCount={legCount}
          activeLegIndex={activeLegIndex}
          onChangeLeg={setActiveLegIndex}
          units={units}
          onPageChange={setIslandPage}
          canNavigate={canNavigate}
          navBusy={nav.busy}
          onNavigate={() => { void onStartNavigate(); }}
          nav={navActive ? {
            distanceRemaining: nav.progress?.distanceRemaining || 0,
            durationRemaining: nav.progress?.durationRemaining || 0,
            rerouting: nav.rerouting,
            onEnd: nav.stop,
            onReport: rideReport.onTrigger,
            reportDisabled: rideReport.reportDisabled,
          } : null}
          report={navActive && rideReport.pickerOpen ? {
            isDark: isDarkForRouting,
            onPick: rideReport.onPick,
            onHoldChange: rideReport.onHoldChange,
          } : null}
        />
      ) : null}
      sidebar={(
        <ProfileSidebar
          profiles={profiles}
          activeProfileId={profileId}
          onSelectProfile={onSelectProfile}
          onDeleteProfile={onDeleteProfile}
          onProfileCreated={onProfileCreated}
          onProfileUpdated={onProfileUpdated}
        />
      )}
    />
    <NavigatePreviewSheet
      visible={Boolean(nav.fallback)}
      navigation={nav.fallback}
      busy={nav.busy}
      error={nav.error}
      onClose={nav.clearFallback}
    />
    </>
  );
}

const styles = StyleSheet.create({
  missingToken: {
    flex: 1,
    backgroundColor: dark.mapFallback,
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  brand: {
    color: brand.fuchsia,
    fontSize: 36,
    fontWeight: '700',
    textAlign: 'center',
  },
  missingTitle: {
    color: dark.text,
    fontSize: 18,
    fontWeight: '700',
    textAlign: 'center',
    marginTop: 16,
  },
  missingBody: {
    color: dark.textSub,
    textAlign: 'center',
    marginTop: 12,
    lineHeight: 20,
  },
  signOut: {
    marginTop: 28,
    alignSelf: 'center',
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: dark.line,
  },
  signOutText: { color: dark.text, fontWeight: '600' },
  mapControlsCol: {
    alignItems: 'flex-end',
    gap: 8,
  },
});

void space;

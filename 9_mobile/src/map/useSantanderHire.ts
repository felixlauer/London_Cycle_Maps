import { useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchHireCandidates,
  fetchWalkLeg,
  type HireNeed,
  type HireStation,
} from '../api/santander';
import { fetchRoute, type RouteVariant } from '../api/route';
import { formatOverlayLength } from '../map/overlayModes';
import type { LatLon } from '../lib/coords';
import {
  bikeLabel,
  coerceBikeForSantander,
  type BikeTypeId,
} from '../routing/constants';
import type { AlertPush } from '../alerts/useAlertPill';

export type HireStep = 'idle' | 'pickup' | 'dropoff' | 'routing' | 'done';

export type HireWalkStats = {
  duration_min: number | null;
  distance_m: number | null;
};

type PushAlert = (a: AlertPush) => void;
type DismissAlert = (types?: string | string[]) => void;

type Opts = {
  start: LatLon | null;
  end: LatLon | null;
  profileId: string | null;
  bikeType: BikeTypeId;
  setBikeType: (t: BikeTypeId) => void;
  profileBikeType: BikeTypeId;
  pushAlert: PushAlert;
  dismissAlert: DismissAlert;
  clearRouteVisuals: () => void;
  setSafest: (v: RouteVariant | null) => void;
  setRouteRevealed: (v: boolean) => void;
  setOverlayMode: (id: string | null) => void;
  defaultOverlayMode: string;
  maybeAlertTraffic: (v: RouteVariant | null) => void;
  maybeAlertFarSnap: (meta: Record<string, unknown> | undefined) => void;
  fitHireStations: (anchor: LatLon | null, stations: HireStation[]) => void;
  fitHireRoute: (
    walkA: number[][] | null,
    bikePath: number[][] | undefined,
    walkB: number[][] | null,
  ) => void;
  flyTo: (c: LatLon) => void;
  setBusy: (v: boolean) => void;
};

/**
 * Santander hire wizard — mirrors web App.jsx hire block.
 */
export function useSantanderHire(opts: Opts) {
  const {
    start, end, profileId, bikeType, setBikeType, profileBikeType,
    pushAlert, dismissAlert, clearRouteVisuals,
    setSafest, setRouteRevealed, setOverlayMode, defaultOverlayMode,
    maybeAlertTraffic, maybeAlertFarSnap,
    fitHireStations, fitHireRoute, flyTo, setBusy,
  } = opts;

  const [santanderMode, setSantanderMode] = useState(false);
  const [hireStep, setHireStep] = useState<HireStep>('idle');
  const [hireStations, setHireStations] = useState<HireStation[]>([]);
  const [pickupStation, setPickupStation] = useState<HireStation | null>(null);
  const [dropoffStation, setDropoffStation] = useState<HireStation | null>(null);
  const [expandedStationId, setExpandedStationId] = useState<string | null>(null);
  const [walkStartPath, setWalkStartPath] = useState<number[][] | null>(null);
  const [walkEndPath, setWalkEndPath] = useState<number[][] | null>(null);
  const [hireWalkStats, setHireWalkStats] = useState<HireWalkStats | null>(null);
  const pendingUnsuitableRef = useRef<{ station: HireStation; step: HireStep } | null>(null);
  const lastConfirmAtRef = useRef(0);
  const santanderModeRef = useRef(false);
  const bikeTypeRef = useRef(bikeType);
  const pickupRef = useRef(pickupStation);

  useEffect(() => { santanderModeRef.current = santanderMode; }, [santanderMode]);
  useEffect(() => { bikeTypeRef.current = bikeType; }, [bikeType]);
  useEffect(() => { pickupRef.current = pickupStation; }, [pickupStation]);

  const resetHireState = useCallback(() => {
    setHireStep('idle');
    setHireStations([]);
    setPickupStation(null);
    setDropoffStation(null);
    setExpandedStationId(null);
    setWalkStartPath(null);
    setWalkEndPath(null);
    setHireWalkStats(null);
    pendingUnsuitableRef.current = null;
  }, []);

  const applyCandidateResponse = useCallback((data: {
    shown?: HireStation[];
    stations?: HireStation[];
    suitable_count?: number;
    total_in_radius?: number;
  }, need: HireNeed) => {
    const shown = data.shown || data.stations || [];
    const suitable = Number(data.suitable_count) || 0;
    const total = Number(data.total_in_radius) || 0;
    if (total === 0) {
      setHireStations([]);
      pushAlert({
        type: 'warning',
        message: `No Santander stations within ${formatOverlayLength(1500)}`,
      });
      return shown;
    }
    if (suitable === 0) {
      setHireStations([]);
      const kind = need === 'docks' ? 'empty docks' : 'bikes';
      pushAlert({
        type: 'warning',
        message: `No Santander station with ${kind} within ${formatOverlayLength(1500)}`,
      });
      return shown;
    }
    setHireStations(shown);
    if (suitable < 3) {
      const kind = need === 'docks' ? 'empty docks' : 'bikes';
      pushAlert({
        type: 'warning',
        message: `Only ${suitable} station${suitable === 1 ? '' : 's'} with ${kind} nearby`,
      });
    }
    return shown;
  }, [pushAlert]);

  const beginPickupStep = useCallback(async () => {
    if (!start || !end) return;
    setBusy(true);
    clearRouteVisuals();
    setWalkStartPath(null);
    setWalkEndPath(null);
    setPickupStation(null);
    setDropoffStation(null);
    setExpandedStationId(null);
    setHireWalkStats(null);
    setHireStep('pickup');
    pushAlert({ type: 'santander_guide', message: 'Select a pick-up station' });
    flyTo(start);
    try {
      const data = await fetchHireCandidates(start[0], start[1], 'bikes');
      const shown = applyCandidateResponse(data, 'bikes');
      fitHireStations(start, shown);
    } catch (e) {
      pushAlert({
        type: 'error',
        message: e instanceof Error ? e.message : 'Could not load stations',
      });
      setHireStations([]);
    } finally {
      setBusy(false);
    }
  }, [
    start, end, setBusy, clearRouteVisuals, pushAlert, flyTo,
    applyCandidateResponse, fitHireStations,
  ]);

  const commitPickup = useCallback(async (station: HireStation) => {
    if (!end) return;
    dismissAlert(['santander_guide']);
    const noEbikes = bikeTypeRef.current === 'ebike' && !(Number(station.nb_ebikes) > 0);
    if (noEbikes) {
      pushAlert({
        type: 'no_ebike',
        message: 'No e-bikes here. You can continue',
      });
    } else {
      pushAlert({ type: 'santander_guide', message: 'Select a drop-off station' });
    }
    setExpandedStationId(null);
    setPickupStation(station);
    setHireStep('dropoff');
    setBusy(true);
    flyTo(end);
    try {
      const data = await fetchHireCandidates(end[0], end[1], 'docks');
      const shown = applyCandidateResponse(data, 'docks');
      fitHireStations(end, shown);
    } catch (e) {
      pushAlert({
        type: 'error',
        message: e instanceof Error ? e.message : 'Could not load stations',
      });
      setHireStations([]);
    } finally {
      setBusy(false);
    }
  }, [end, dismissAlert, pushAlert, flyTo, applyCandidateResponse, fitHireStations, setBusy]);

  const commitDropoff = useCallback(async (station: HireStation) => {
    const pickup = pickupRef.current;
    if (!start || !end || !pickup) return;
    dismissAlert(['santander_guide', 'no_ebike']);
    setExpandedStationId(null);
    setDropoffStation(station);
    setHireStep('routing');
    setHireStations([]);
    setBusy(true);

    try {
      const [routeResult, walkA, walkB] = await Promise.all([
        fetchRoute({
          start: [pickup.lat, pickup.lon],
          end: [station.lat, station.lon],
          profileId,
          bikeType: bikeTypeRef.current,
          purpose: 'commit',
        }),
        fetchWalkLeg(start, [pickup.lat, pickup.lon]),
        fetchWalkLeg([station.lat, station.lon], end),
      ]);

      if (!routeResult.ok) {
        pushAlert({ type: 'error', message: routeResult.error || 'Route failed' });
        setHireStep('dropoff');
        return;
      }

      const nextSafe = routeResult.data.safest || null;
      const walkAPath = walkA?.path || [start, [pickup.lat, pickup.lon]];
      const walkBPath = walkB?.path || [[station.lat, station.lon], end];
      setSafest(nextSafe);
      setWalkStartPath(walkAPath);
      setWalkEndPath(walkBPath);

      const pickupWalkMin = Number(walkA?.duration_min) || 0;
      const dropoffWalkMin = Number(walkB?.duration_min) || 0;
      const walkDur = pickupWalkMin + dropoffWalkMin;
      const walkDistM = (Number(walkA?.distance_m) || 0) + (Number(walkB?.distance_m) || 0);

      setPickupStation((prev) => (prev ? {
        ...prev,
        walk_duration_min: pickupWalkMin > 0 ? pickupWalkMin : null,
        walk_distance_m: Number(walkA?.distance_m) || null,
      } : prev));
      setDropoffStation({
        ...station,
        walk_duration_min: dropoffWalkMin > 0 ? dropoffWalkMin : null,
        walk_distance_m: Number(walkB?.distance_m) || null,
      });
      setHireWalkStats({
        duration_min: walkDur > 0 ? walkDur : null,
        distance_m: walkDistM > 0 ? walkDistM : null,
      });
      setRouteRevealed(true);
      setOverlayMode(defaultOverlayMode);
      maybeAlertTraffic(nextSafe);
      maybeAlertFarSnap(routeResult.data.meta as Record<string, unknown> | undefined);
      setHireStep('done');
      fitHireRoute(walkAPath, nextSafe?.path, walkBPath);
    } catch {
      pushAlert({ type: 'error', message: 'Backend error' });
      setHireStep('dropoff');
    } finally {
      setBusy(false);
    }
  }, [
    start, end, profileId, dismissAlert, pushAlert, setBusy,
    setSafest, setRouteRevealed, setOverlayMode, defaultOverlayMode,
    maybeAlertTraffic, maybeAlertFarSnap, fitHireRoute,
  ]);

  const handleStationExpand = useCallback((station: HireStation) => {
    if (hireStep !== 'pickup' && hireStep !== 'dropoff') return;
    dismissAlert('confirm');
    pendingUnsuitableRef.current = null;
    // No camera move on expand — Mapbox Android MarkerView hit regions desync
    // while the camera animates (intermittent missed taps).
    setExpandedStationId((prev) => (prev === station.id ? null : station.id));
  }, [hireStep, dismissAlert]);

  const handleStationConfirm = useCallback((station: HireStation) => {
    if (hireStep !== 'pickup' && hireStep !== 'dropoff') return;
    const now = Date.now();
    // MarkerView Pressable + chrome hit can both fire once on Android.
    if (now - lastConfirmAtRef.current < 450) return;
    lastConfirmAtRef.current = now;
    const unsuitable = hireStep === 'pickup'
      ? !(Number(station.nb_bikes) > 0)
      : !(Number(station.nb_empty) > 0);
    if (unsuitable) {
      pendingUnsuitableRef.current = { station, step: hireStep };
      pushAlert({
        type: 'confirm',
        sticky: true,
        message: hireStep === 'pickup'
          ? 'No bikes here. Proceed anyway?'
          : 'No empty docks. Proceed anyway?',
        actions: [
          { id: 'cancel', label: 'Cancel' },
          { id: 'proceed', label: 'Proceed', primary: true },
        ],
      });
      return;
    }
    if (hireStep === 'pickup') commitPickup(station);
    else commitDropoff(station);
  }, [hireStep, pushAlert, commitPickup, commitDropoff]);

  const handleAlertAction = useCallback((actionId: string) => {
    const pending = pendingUnsuitableRef.current;
    dismissAlert('confirm');
    pendingUnsuitableRef.current = null;
    if (actionId !== 'proceed' || !pending) return;
    if (pending.step === 'pickup') commitPickup(pending.station);
    else if (pending.step === 'dropoff') commitDropoff(pending.station);
  }, [dismissAlert, commitPickup, commitDropoff]);

  const handleSantanderChange = useCallback((on: boolean, hasVias: boolean) => {
    if (on && hasVias) {
      pushAlert({ type: 'warning', message: 'Remove stops to use Santander' });
      return;
    }
    if (on) {
      const next = coerceBikeForSantander(bikeTypeRef.current);
      if (next !== bikeTypeRef.current || bikeTypeRef.current === 'road' || bikeTypeRef.current === 'cargo') {
        setBikeType(next);
        pushAlert({
          type: 'bike_override',
          message: `Bike set to ${bikeLabel(next, true)}`,
        });
      } else {
        pushAlert({
          type: 'bike_override',
          message: `Using ${bikeLabel(bikeTypeRef.current, true)}`,
        });
      }
      setSantanderMode(true);
    } else {
      setSantanderMode(false);
      resetHireState();
      dismissAlert(['santander_guide', 'bike_override', 'no_ebike', 'confirm']);
      setBikeType(profileBikeType);
      pushAlert({ type: 'info', message: 'Bike restored to profile default' });
    }
    clearRouteVisuals();
  }, [
    pushAlert, setBikeType, profileBikeType, resetHireState, dismissAlert, clearRouteVisuals,
  ]);

  /** Guide once start+end ready in Santander idle. */
  useEffect(() => {
    if (santanderMode && start && end && hireStep === 'idle') {
      pushAlert({
        type: 'santander_guide',
        message: 'Ready. Press Get Route',
      });
    }
  }, [santanderMode, start, end, hireStep, pushAlert]);

  const hireNeed: HireNeed = hireStep === 'dropoff' ? 'docks' : 'bikes';
  const mapBusyHire = hireStep === 'pickup' || hireStep === 'dropoff' || hireStep === 'routing';
  const islandSantander = Boolean(santanderMode && hireStep === 'done');

  return {
    santanderMode,
    setSantanderMode,
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
  };
}

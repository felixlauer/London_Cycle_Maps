/**
 * v2 root — routing core + alert pill + map + profile sidebar.
 * Checklist: 0_documentation/design/FUNCTIONALITY_CHECKLIST.md
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AuthProvider, useAuth } from '../auth/AuthProvider';
import { apiFetch } from '../api/flaskClient';
import PasswordRecoveryModal from '../auth/PasswordRecoveryModal';
import MapShell from './shell/MapShell';
import { SidebarProvider, useSidebar } from './shell/SidebarContext';
import { themeForMode } from './map/theme';
import { useAlertPill } from './alerts/useAlertPill';
import { bikeLabel, coerceBikeForSantander, MAX_VIAS, BLOCKED } from './routing/constants';
import { isFutureDepartAt } from './routing/DepartAtControl';
import { useGeolocation } from './map/useGeolocation';
import { formatDistance } from './units';
import {
  DEFAULT_OVERLAY_MODE,
  OVERLAY_MODE_META,
  availableOverlayModes,
  chunksForMode,
  sumChunkLengthM,
  formatOverlayLength,
  trafficChunks,
} from './map/overlayModes';
import { profileWantsLight } from './island/resolveIslandSlots';
import { pickInactiveLegIndex } from '../map/RouteLayers';
import './tailwind.css';
import './alerts/alertPill.css';
import './shell/shell.css';

function AppV2Inner({ mapApiRef, isDarkOutside }) {
  const { user, isLoading: authLoading, passwordRecoveryPending } = useAuth();
  const {
    themeMode,
    units,
    favouriteOrder,
    setFavouriteOrder,
    openSidebar,
  } = useSidebar();
  const theme = useMemo(() => themeForMode(themeMode), [themeMode]);
  const { alert, push: pushAlert, dismiss: dismissAlert } = useAlertPill();
  const lastFlownLocationKey = useRef(null);

  const geo = useGeolocation({
    onError: (message) => pushAlert({ type: 'warning', message }),
  });
  const [northNeedsReset, setNorthNeedsReset] = useState(false);
  const handleNorthUpChange = useCallback((needsReset) => {
    setNorthNeedsReset(Boolean(needsReset));
  }, []);

  // Fly to the user once we get a first fix (or a meaningful move).
  useEffect(() => {
    if (!geo.location) {
      lastFlownLocationKey.current = null;
      return;
    }
    const key = `${geo.location.lat.toFixed(5)},${geo.location.lon.toFixed(5)}`;
    if (lastFlownLocationKey.current === key) return;
    // Only auto-fly on first fix after enabling locate (not every watch tick).
    if (lastFlownLocationKey.current != null) return;
    lastFlownLocationKey.current = key;
    setFlyTarget({
      center: [geo.location.lat, geo.location.lon],
      zoom: 16,
      duration: 1.05,
    });
  }, [geo.location]);

  const [start, setStart] = useState(null);
  const [end, setEnd] = useState(null);
  const [startLabel, setStartLabel] = useState('');
  const [endLabel, setEndLabel] = useState('');
  const [vias, setVias] = useState([]);
  const [flyTarget, setFlyTarget] = useState(null);

  const [profiles, setProfiles] = useState([]);
  const [activeProfileId, setActiveProfileId] = useState(
    () => localStorage.getItem('activeProfileId') || 'preset_safe',
  );
  const [activeProfile, setActiveProfile] = useState(null);
  const [sessionBikeType, setSessionBikeType] = useState('standard');
  const [bikePulse, setBikePulse] = useState(false);
  const sessionBikeTypeRef = useRef(sessionBikeType);
  useEffect(() => { sessionBikeTypeRef.current = sessionBikeType; }, [sessionBikeType]);
  /** User profile switch — alert only when load applies a different bike. */
  const pendingProfileBikeAlertRef = useRef(false);

  const [santanderMode, setSantanderMode] = useState(false);
  const [hireStep, setHireStep] = useState('idle');
  const [hireStations, setHireStations] = useState([]);
  const [pickupStation, setPickupStation] = useState(null);
  const [dropoffStation, setDropoffStation] = useState(null);
  const [walkStartPath, setWalkStartPath] = useState(null);
  const [walkEndPath, setWalkEndPath] = useState(null);
  /** Aggregated exact walk for island: { duration_min, distance_m }. */
  const [hireWalkStats, setHireWalkStats] = useState(null);
  const [expandedStationId, setExpandedStationId] = useState(null);
  const pendingUnsuitableRef = useRef(null);
  const santanderModeRef = useRef(false);
  useEffect(() => { santanderModeRef.current = santanderMode; }, [santanderMode]);

  const [departMode, setDepartMode] = useState('now');
  const [departAtIso, setDepartAtIso] = useState(null);

  const [routeRevealed, setRouteRevealed] = useState(false);
  /** True only while a user-initiated Get Route (or hire start) is in flight. */
  const [commitPending, setCommitPending] = useState(false);
  const [fastestData, setFastestData] = useState(null);
  const [safestData, setSafestData] = useState(null);
  const [routeLegs, setRouteLegs] = useState(null);
  const [activeLegIndex, setActiveLegIndex] = useState(0);
  const [overlayMode, setOverlayMode] = useState(DEFAULT_OVERLAY_MODE);
  const overlayTouchedRef = useRef(false);
  const jamAlertKeyRef = useRef(null);

  /* —— Dynamic Island —— */
  const [islandExpanded, setIslandExpanded] = useState(false);
  /** Shared map↔island hover: { source, modeId, kind, runId(s), point }. */
  const [routeHover, setRouteHover] = useState(null);

  useEffect(() => {
    if (!routeRevealed) {
      setIslandExpanded(false);
      setRouteHover(null);
    }
  }, [routeRevealed]);

  const routeRequestIdRef = useRef(0);
  const abortRef = useRef(null);
  const routeRevealedRef = useRef(false);
  useEffect(() => { routeRevealedRef.current = routeRevealed; }, [routeRevealed]);

  const bumpRouteRequest = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    routeRequestIdRef.current += 1;
    return routeRequestIdRef.current;
  }, []);

  useEffect(() => {
    if (overlayMode == null) return;
    const allowed = availableOverlayModes(isDarkOutside).map((m) => m.id);
    if (!allowed.includes(overlayMode)) setOverlayMode(null);
  }, [isDarkOutside, overlayMode]);

  const activeSafest = useMemo(() => {
    if (routeLegs && routeLegs.length > 1) {
      return routeLegs[activeLegIndex]?.safest || safestData;
    }
    return safestData;
  }, [routeLegs, activeLegIndex, safestData]);

  const activeFastest = useMemo(() => {
    if (routeLegs && routeLegs.length > 1) {
      return routeLegs[activeLegIndex]?.fastest || fastestData;
    }
    return fastestData;
  }, [routeLegs, activeLegIndex, fastestData]);

  const legCount = routeLegs?.length > 1 ? routeLegs.length : 1;
  const viaCount = vias.filter((v) => v.coord).length;

  const maybeAlertTraffic = useCallback((safest) => {
    const chunks = trafficChunks(safest);
    const total = sumChunkLengthM(chunks);
    if (total <= 0) return;
    const key = `${chunks.length}:${Math.round(total)}`;
    if (jamAlertKeyRef.current === key) return;
    jamAlertKeyRef.current = key;
    pushAlert({
      type: 'warning',
      message: `Traffic on this route — ${formatOverlayLength(total, units)}`,
    });
  }, [pushAlert, units]);

  /** Soft-fail when backend snapped start/end/via far from the chosen pin (> ~50 m). */
  const maybeAlertFarSnap = useCallback((meta) => {
    const snap = meta?.snap;
    if (!snap) return;
    const parts = [];
    if (snap.start?.far) {
      parts.push(`start is ${formatDistance(snap.start.distance_m, units)}`);
    }
    if (Array.isArray(snap.vias)) {
      snap.vias.forEach((v, i) => {
        if (v?.far) {
          parts.push(`stop ${i + 1} is ${formatDistance(v.distance_m, units)}`);
        }
      });
    }
    if (snap.end?.far) {
      parts.push(`end is ${formatDistance(snap.end.distance_m, units)}`);
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

  const handleSelectOverlayMode = useCallback((id) => {
    if (!routeRevealedRef.current) {
      pushAlert({ type: 'info', message: BLOCKED.overlayNeedsRoute });
      return;
    }
    overlayTouchedRef.current = true;
    // null = clear active mode (toggle off); mode layers hide, traffic stays
    if (id == null) {
      setOverlayMode(null);
      return;
    }
    setOverlayMode(id);
    if (!activeSafest) return;
    const chunks = chunksForMode(activeSafest, id);
    if (chunks.length) return;
    const msg = OVERLAY_MODE_META[id]?.emptyMessage
      || `No ${OVERLAY_MODE_META[id]?.label?.toLowerCase() || 'overlay'} on this route`;
    pushAlert({ type: 'info', message: msg });
  }, [activeSafest, pushAlert]);

  const clearRouteData = useCallback(() => {
    setFastestData(null);
    setSafestData(null);
    setRouteLegs(null);
    setWalkStartPath(null);
    setWalkEndPath(null);
    setHireWalkStats(null);
    setIslandExpanded(false);
    setRouteHover(null);
    jamAlertKeyRef.current = null;
  }, []);

  // At night, riders who want lit roads land on the light overlay by default
  // (until they pick a mode themselves) — the island then leads with it too.
  useEffect(() => {
    if (!routeRevealed || overlayTouchedRef.current) return;
    if (isDarkOutside && profileWantsLight(activeProfile)) {
      setOverlayMode('light');
    }
  }, [routeRevealed, isDarkOutside, activeProfile]);

  const resetHireState = useCallback(() => {
    dismissAlert(['santander_guide', 'confirm']);
    pendingUnsuitableRef.current = null;
    setHireStep('idle');
    setHireStations([]);
    setPickupStation(null);
    setDropoffStation(null);
    setWalkStartPath(null);
    setWalkEndPath(null);
    setHireWalkStats(null);
    setExpandedStationId(null);
  }, [dismissAlert]);

  const triggerBikePulse = useCallback(() => {
    setBikePulse(true);
    window.setTimeout(() => setBikePulse(false), 600);
  }, []);

  /* —— Profiles —— */
  const authReady = !authLoading;

  const loadProfileList = useCallback(async () => {
    try {
      const res = await apiFetch('/profiles', { testMode: false });
      const data = await res.json();
      setProfiles(data.profiles || []);
    } catch {
      pushAlert({ type: 'error', message: 'Could not load profiles' });
    }
  }, [pushAlert]);

  const loadActiveProfile = useCallback(async (profileId) => {
    try {
      const res = await apiFetch(`/profiles/${profileId}`, { testMode: false });
      if (!res.ok) {
        pendingProfileBikeAlertRef.current = false;
        if (profileId !== 'preset_safe') setActiveProfileId('preset_safe');
        return;
      }
      const data = await res.json();
      setActiveProfile(data);
      const bt = data.bike_type || 'standard';
      const santanderOn = santanderModeRef.current;
      const next = santanderOn ? coerceBikeForSantander(bt) : bt;
      const prev = sessionBikeTypeRef.current;
      setSessionBikeType(next);
      if (pendingProfileBikeAlertRef.current) {
        pendingProfileBikeAlertRef.current = false;
        if (next !== prev) {
          triggerBikePulse();
          pushAlert({
            type: 'bike_override',
            message: `Bike set to ${bikeLabel(next, santanderOn)}`,
          });
        }
      }
    } catch {
      pendingProfileBikeAlertRef.current = false;
    }
  }, [triggerBikePulse, pushAlert]);

  useEffect(() => {
    if (!authReady) return;
    loadProfileList();
  }, [authReady, loadProfileList, user?.id]);

  useEffect(() => {
    if (!authReady || !activeProfileId) return;
    localStorage.setItem('activeProfileId', activeProfileId);
    loadActiveProfile(activeProfileId);
  }, [authReady, activeProfileId, loadActiveProfile, user?.id]);

  const handleSelectProfile = useCallback((id) => {
    pendingProfileBikeAlertRef.current = true;
    setActiveProfileId(id);
    setRouteRevealed(false);
  }, []);

  const handleProfileCreated = useCallback((profile) => {
    if (profile?.id) {
      setActiveProfileId(profile.id);
    }
    loadProfileList();
    pushAlert({ type: 'info', message: 'Profile created' });
  }, [loadProfileList, pushAlert]);

  const handleProfileUpdated = useCallback((profile) => {
    if (profile?.id) {
      setActiveProfileId(profile.id);
      loadActiveProfile(profile.id);
    }
    loadProfileList();
    pushAlert({ type: 'info', message: 'Profile updated' });
  }, [loadActiveProfile, loadProfileList, pushAlert]);

  const handleDeleteProfile = useCallback(async (profileId) => {
    try {
      const res = await apiFetch(`/profiles/${profileId}`, {
        method: 'DELETE',
        testMode: false,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        pushAlert({ type: 'error', message: data.error || 'Could not delete profile' });
        return;
      }
      setProfiles((prev) => (prev || []).filter((p) => p.id !== profileId));
      setFavouriteOrder((prev) => (prev || []).filter((id) => id !== profileId));
      if (activeProfileId === profileId) {
        setActiveProfileId('preset_safe');
      }
      pushAlert({ type: 'info', message: 'Profile deleted' });
    } catch {
      pushAlert({ type: 'error', message: 'Could not delete profile' });
    }
  }, [activeProfileId, pushAlert, setFavouriteOrder]);

  const handleSelectBike = useCallback((id) => {
    setSessionBikeType(id);
    setRouteRevealed(false);
  }, []);

  const handleSantanderChange = useCallback((on) => {
    if (on && vias.length > 0) {
      pushAlert({ type: 'warning', message: 'Remove stops to use Santander' });
      return;
    }
    bumpRouteRequest();
    if (on) {
      const next = coerceBikeForSantander(sessionBikeType);
      if (next !== sessionBikeType || sessionBikeType === 'road' || sessionBikeType === 'cargo') {
        setSessionBikeType(next);
        triggerBikePulse();
        pushAlert({
          type: 'bike_override',
          message: next === 'ebike'
            ? 'Bike set to E-bike (Sant.)'
            : 'Bike set to Reg (Sant.)',
        });
      } else {
        triggerBikePulse();
        pushAlert({
          type: 'bike_override',
          message: sessionBikeType === 'ebike'
            ? 'Using E-bike (Sant.)'
            : 'Using Reg (Sant.)',
        });
      }
      if (departMode === 'depart_at') {
        setDepartMode('now');
        setDepartAtIso(null);
      }
      setSantanderMode(true);
    } else {
      setSantanderMode(false);
      resetHireState();
      dismissAlert(['santander_guide', 'bike_override', 'no_ebike']);
      const profileBike = activeProfile?.bike_type || 'standard';
      setSessionBikeType(profileBike);
      triggerBikePulse();
      pushAlert({ type: 'info', message: 'Santander off — bike restored to profile default' });
    }
    setRouteRevealed(false);
    clearRouteData();
  }, [
    vias.length, sessionBikeType, departMode, activeProfile, pushAlert, dismissAlert,
    triggerBikePulse, resetHireState, clearRouteData, bumpRouteRequest,
  ]);

  /* —— Waypoints —— */
  const handleChangeWaypoints = useCallback((next) => {
    bumpRouteRequest();
    setStart(next.start);
    setStartLabel(next.startLabel || '');
    setEnd(next.end);
    setEndLabel(next.endLabel || '');
    setVias(next.vias || []);
    setRouteRevealed(false);
    clearRouteData();
    resetHireState();
    if ((next.vias || []).length > 0 && santanderModeRef.current) {
      setSantanderMode(false);
      const profileBike = activeProfile?.bike_type || 'standard';
      setSessionBikeType(profileBike);
    }
  }, [bumpRouteRequest, clearRouteData, resetHireState, activeProfile]);

  const handleAddVia = useCallback(() => {
    if (vias.length >= MAX_VIAS) {
      pushAlert({ type: 'warning', message: `You can add up to ${MAX_VIAS} stops` });
      return;
    }
    if (santanderMode) {
      pushAlert({ type: 'warning', message: 'Turn off Santander to add stops' });
      return;
    }
    bumpRouteRequest();
    setVias((prev) => [...prev, { id: `via-${Date.now()}`, coord: null, label: '' }]);
    setRouteRevealed(false);
    clearRouteData();
  }, [vias.length, santanderMode, bumpRouteRequest, clearRouteData, pushAlert]);

  const handleBlocked = useCallback((message) => {
    if (!message) return;
    pushAlert({ type: 'warning', message });
  }, [pushAlert]);

  const handleRemoveVia = useCallback((viaIndex) => {
    bumpRouteRequest();
    setVias((prev) => prev.filter((_, i) => i !== viaIndex));
    setRouteRevealed(false);
    clearRouteData();
  }, [bumpRouteRequest, clearRouteData]);

  const applyMapPoint = useCallback((lat, lon) => {
    bumpRouteRequest();
    setRouteRevealed(false);
    clearRouteData();
    resetHireState();
    if (!start) {
      setStart([lat, lon]);
      setStartLabel(`${lat.toFixed(4)}, ${lon.toFixed(4)}`);
      return;
    }
    const emptyVia = vias.findIndex((v) => !v.coord);
    if (emptyVia >= 0) {
      setVias((prev) => prev.map((v, i) => (
        i === emptyVia
          ? { ...v, coord: [lat, lon], label: `${lat.toFixed(4)}, ${lon.toFixed(4)}` }
          : v
      )));
      return;
    }
    if (!end) {
      setEnd([lat, lon]);
      setEndLabel(`${lat.toFixed(4)}, ${lon.toFixed(4)}`);
      return;
    }
    setStart([lat, lon]);
    setStartLabel(`${lat.toFixed(4)}, ${lon.toFixed(4)}`);
    setEnd(null);
    setEndLabel('');
    setVias([]);
  }, [start, end, vias, bumpRouteRequest, clearRouteData, resetHireState]);

  const handleMapClick = useCallback((e) => {
    if (hireStep === 'pickup' || hireStep === 'dropoff') {
      pushAlert({ type: 'warning', message: 'Select a Santander station on the map' });
      return;
    }
    if (routeRevealed && routeLegs?.length > 1) {
      const legIdx = pickInactiveLegIndex(e.target, e.point, routeLegs, activeLegIndex);
      if (legIdx != null) {
        setActiveLegIndex(legIdx);
        return;
      }
    }
    const { lng, lat } = e.lngLat;
    applyMapPoint(lat, lng);
  }, [
    hireStep, applyMapPoint, pushAlert,
    routeRevealed, routeLegs, activeLegIndex,
  ]);

  /* —— Route fetch —— */
  const encodeViasParam = useCallback((viaList) => {
    const filled = (viaList || []).filter((v) => v.coord && v.coord.length === 2);
    if (!filled.length) return '';
    return filled.map((v) => `${v.coord[0]},${v.coord[1]}`).join(';');
  }, []);

  const fetchRoutes = useCallback(async (s, e, viaList, purpose = 'prefetch') => {
    const startCoord = s || start;
    const endCoord = e || end;
    const viasArg = viaList !== undefined ? viaList : vias;
    if (!startCoord || !endCoord) return;
    if ((viasArg || []).some((v) => !v.coord)) return;

    const reqId = bumpRouteRequest();
    const controller = new AbortController();
    abortRef.current = controller;

    const params = new URLSearchParams({
      start_lat: startCoord[0],
      start_lon: startCoord[1],
      end_lat: endCoord[0],
      end_lon: endCoord[1],
      purpose,
    });
    const viasStr = encodeViasParam(viasArg);
    if (viasStr) params.set('vias', viasStr);
    if (activeProfileId) params.set('profile_id', activeProfileId);
    if (sessionBikeType) params.set('bike_type', sessionBikeType);
    if (departMode === 'depart_at' && departAtIso) params.set('depart_at', departAtIso);

    try {
      const response = await apiFetch(`/route?${params}`, { testMode: false, signal: controller.signal });
      if (reqId !== routeRequestIdRef.current) return;
      const data = await response.json();
      if (reqId !== routeRequestIdRef.current) return;
      if (response.status === 429) {
        pushAlert({ type: 'error', message: data.error || 'Too many route requests' });
        return;
      }
      if (data.status === 'success') {
        setFastestData(data.fastest);
        setSafestData(data.safest);
        const legs = Array.isArray(data.legs) && data.legs.length ? data.legs : null;
        setRouteLegs(legs);
        setActiveLegIndex(0);
        if (purpose === 'commit') {
          setRouteRevealed(true);
          setOverlayMode(DEFAULT_OVERLAY_MODE);
          maybeAlertTraffic(data.safest);
          maybeAlertFarSnap(data.meta);
          if (departMode === 'depart_at' && isFutureDepartAt(departAtIso)) {
            pushAlert({ type: 'warning', message: 'Live traffic not applied for future departures' });
          }
        }
      } else {
        pushAlert({ type: 'error', message: data.error || 'Route failed' });
      }
    } catch (err) {
      if (err?.name === 'AbortError') return;
      if (reqId !== routeRequestIdRef.current) return;
      pushAlert({ type: 'error', message: 'Backend error' });
    }
  }, [
    start, end, vias, activeProfileId, sessionBikeType, departMode, departAtIso,
    bumpRouteRequest, encodeViasParam, pushAlert, maybeAlertTraffic, maybeAlertFarSnap,
  ]);

  useEffect(() => {
    if (!start || !end || santanderMode) {
      if (santanderMode) {
        setRouteRevealed(false);
        clearRouteData();
      }
      return;
    }
    if (vias.some((v) => !v.coord)) return;
    setRouteRevealed(false);
    fetchRoutes(start, end, vias, 'prefetch');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [start, end, vias, activeProfileId, sessionBikeType, santanderMode, departMode, departAtIso]);

  /* Guide the hire flow: once start + end are set in Santander mode, tell
     the user Get Route is the next step (legacy had a status line for this). */
  useEffect(() => {
    if (santanderMode && start && end && hireStep === 'idle') {
      pushAlert({ type: 'santander_guide', message: 'Ready — press Get Route to choose stations' });
    }
  }, [santanderMode, start, end, hireStep, pushAlert]);

  /* —— Santander hire —— */
  const applyCandidateResponse = useCallback((data, need) => {
    // Backend key is `shown` (not `stations`) — see /santander/candidates.
    const shown = data.shown || data.stations || [];
    const suitable = Number(data.suitable_count) || 0;
    const total = Number(data.total_in_radius) || 0;
    if (total === 0) {
      setHireStations([]);
      pushAlert({ type: 'warning', message: `No Santander stations within ${formatDistance(1500, units)}` });
      return;
    }
    if (suitable === 0) {
      setHireStations([]);
      const kind = need === 'docks' ? 'empty docks' : 'bikes';
      pushAlert({ type: 'warning', message: `No Santander station with ${kind} within ${formatDistance(1500, units)}` });
      return;
    }
    setHireStations(shown);
    if (suitable < 3) {
      const kind = need === 'docks' ? 'empty docks' : 'bikes';
      pushAlert({ type: 'warning', message: `Only ${suitable} station${suitable === 1 ? '' : 's'} with ${kind} nearby` });
    }
  }, [pushAlert, units]);

  const fetchHireCandidates = useCallback(async (lat, lon, need) => {
    const params = new URLSearchParams({
      lat: String(lat), lon: String(lon), need, radius_m: '1500',
    });
    const res = await apiFetch(`/santander/candidates?${params}`, { testMode: false });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    applyCandidateResponse(data, need);
    return data;
  }, [applyCandidateResponse]);

  const beginPickupStep = useCallback(async (startOverride = null) => {
    const startCoord = startOverride || start;
    if (!startCoord || !end) return;
    setRouteRevealed(false);
    clearRouteData();
    setWalkStartPath(null);
    setWalkEndPath(null);
    setPickupStation(null);
    setDropoffStation(null);
    setExpandedStationId(null);
    setHireStep('pickup');
    pushAlert({ type: 'santander_guide', message: 'Select a pick-up station' });
    setFlyTarget({ center: startCoord, zoom: 16, duration: 0.9 });
    try {
      await fetchHireCandidates(startCoord[0], startCoord[1], 'bikes');
    } catch (e) {
      pushAlert({ type: 'error', message: e.message || 'Could not load stations' });
      setHireStations([]);
    }
  }, [start, end, clearRouteData, fetchHireCandidates, pushAlert]);

  const fetchWalkLeg = useCallback(async (from, to) => {
    try {
      const res = await apiFetch('/santander/walk', {
        method: 'POST',
        testMode: false,
        body: { from, to },
      });
      const data = await res.json();
      if (!res.ok || data.error) return null;
      return data;
    } catch {
      return null;
    }
  }, []);

  const commitPickup = useCallback(async (station) => {
    dismissAlert(['santander_guide']);
    const noEbikes = sessionBikeType === 'ebike' && !(station.nb_ebikes > 0);
    if (noEbikes) {
      // Priority would let the guide replace this instantly, so show the
      // warning alone; the map context already implies the next step.
      pushAlert({
        type: 'no_ebike',
        message: 'No e-bikes at this station — you can still continue',
      });
    } else {
      pushAlert({ type: 'santander_guide', message: 'Select a drop-off station' });
    }
    setExpandedStationId(null);
    setPickupStation(station);
    setHireStep('dropoff');
    setFlyTarget({ center: end, zoom: 16, duration: 0.9 });
    try {
      await fetchHireCandidates(end[0], end[1], 'docks');
    } catch (e) {
      pushAlert({ type: 'error', message: e.message || 'Could not load stations' });
      setHireStations([]);
    }
  }, [sessionBikeType, end, fetchHireCandidates, pushAlert, dismissAlert]);

  const commitDropoff = useCallback(async (station) => {
    if (!start || !end || !pickupStation) return;
    dismissAlert(['santander_guide', 'no_ebike']);
    setExpandedStationId(null);
    setDropoffStation(station);
    setHireStep('routing');
    setHireStations([]);

    const bikeParams = new URLSearchParams({
      start_lat: String(pickupStation.lat),
      start_lon: String(pickupStation.lon),
      end_lat: String(station.lat),
      end_lon: String(station.lon),
      purpose: 'commit',
    });
    if (activeProfileId) bikeParams.set('profile_id', activeProfileId);
    if (sessionBikeType) bikeParams.set('bike_type', sessionBikeType);

    try {
      const [routeRes, walkA, walkB] = await Promise.all([
        apiFetch(`/route?${bikeParams}`, { testMode: false }),
        fetchWalkLeg(start, [pickupStation.lat, pickupStation.lon]),
        fetchWalkLeg([station.lat, station.lon], end),
      ]);
      const data = await routeRes.json();
      if (data.status === 'success') {
        setFastestData(data.fastest);
        setSafestData(data.safest);
        setWalkStartPath(walkA?.path || [start, [pickupStation.lat, pickupStation.lon]]);
        setWalkEndPath(walkB?.path || [[station.lat, station.lon], end]);
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
        setOverlayMode(DEFAULT_OVERLAY_MODE);
        maybeAlertTraffic(data.safest);
        maybeAlertFarSnap(data.meta);
        setHireStep('done');
        setFlyTarget({
          center: [
            (pickupStation.lat + station.lat) / 2,
            (pickupStation.lon + station.lon) / 2,
          ],
          zoom: 13,
          duration: 1.0,
        });
      } else {
        pushAlert({ type: 'error', message: data.error || 'Route failed' });
        setHireStep('dropoff');
      }
    } catch {
      pushAlert({ type: 'error', message: 'Backend error' });
      setHireStep('dropoff');
    }
  }, [start, end, pickupStation, activeProfileId, sessionBikeType, fetchWalkLeg, pushAlert, dismissAlert, maybeAlertTraffic, maybeAlertFarSnap]);

  const handleStationExpand = useCallback((station) => {
    if (hireStep !== 'pickup' && hireStep !== 'dropoff') return;
    // Switching stations clears the unsuitable sticky confirm.
    dismissAlert('confirm');
    pendingUnsuitableRef.current = null;
    setExpandedStationId((prev) => (prev === station.id ? null : station.id));
  }, [hireStep, dismissAlert]);

  const handleStationConfirm = useCallback((station) => {
    if (hireStep !== 'pickup' && hireStep !== 'dropoff') return;
    const unsuitable = hireStep === 'pickup'
      ? !(station.nb_bikes > 0)
      : !(station.nb_empty > 0);
    if (unsuitable) {
      pendingUnsuitableRef.current = { station, step: hireStep };
      pushAlert({
        type: 'confirm',
        sticky: true,
        message: hireStep === 'pickup'
          ? 'No bikes here — proceed anyway?'
          : 'No empty docks — proceed anyway?',
        actions: [
          { id: 'cancel', label: 'Cancel' },
          { id: 'proceed', label: 'Proceed', primary: true },
        ],
      });
      return;
    }
    if (hireStep === 'pickup') commitPickup(station);
    else commitDropoff(station);
  }, [hireStep, commitPickup, commitDropoff, pushAlert]);

  const handleAlertAction = useCallback((actionId) => {
    if (actionId === 'cancel') {
      pendingUnsuitableRef.current = null;
      dismissAlert('confirm');
      return;
    }
    if (actionId === 'proceed') {
      const pending = pendingUnsuitableRef.current;
      pendingUnsuitableRef.current = null;
      dismissAlert('confirm');
      if (!pending?.station) return;
      if (pending.step === 'pickup') commitPickup(pending.station);
      else if (pending.step === 'dropoff') commitDropoff(pending.station);
    }
  }, [dismissAlert, commitPickup, commitDropoff]);

  const handleGetRoute = useCallback(async () => {
    const effectiveStart = start || (geo.active && geo.location
      ? [geo.location.lat, geo.location.lon]
      : null);
    if (!effectiveStart || !end) return;
    if (vias.some((v) => !v.coord)) {
      pushAlert({ type: 'warning', message: 'Fill all stops before getting a route' });
      return;
    }
    // Soft-apply location as start so markers / prefetch stay consistent.
    if (!start && geo.active && geo.location) {
      setStart([geo.location.lat, geo.location.lon]);
      setStartLabel(geo.location.label || 'Current location');
    }
    if (santanderMode) {
      setCommitPending(true);
      try {
        await beginPickupStep(effectiveStart);
      } finally {
        setCommitPending(false);
      }
      return;
    }
    // Always show Get Route busy state (incl. long-route copy / dots), even when
    // a prefetch response is already cached.
    setCommitPending(true);
    try {
      await fetchRoutes(effectiveStart, end, vias, 'commit');
    } finally {
      setCommitPending(false);
    }
  }, [
    start, end, vias, santanderMode, beginPickupStep, fetchRoutes, pushAlert,
    geo.active, geo.location,
  ]);

  const canGetRoute = Boolean(
    (start || (geo.active && geo.location))
    && end
    && !vias.some((v) => !v.coord),
  );
  const routeStart = start || (geo.active && geo.location
    ? [geo.location.lat, geo.location.lon]
    : null);
  const showCalculating = commitPending || hireStep === 'routing';
  const startPlaceholder = (geo.active && geo.location && !start)
    ? (geo.location.label || 'Current location')
    : 'Search start';

  const hireNeed = hireStep === 'dropoff' ? 'docks' : 'bikes';

  return (
    <>
      <MapShell
        themeMode={themeMode}
        alert={alert}
        onAlertAction={handleAlertAction}
        sidebarProfiles={profiles}
        activeProfileId={activeProfileId}
        onDeleteProfile={handleDeleteProfile}
        onProfileCreated={handleProfileCreated}
        onProfileUpdated={handleProfileUpdated}
        routingProps={{
          theme,
          profiles,
          favouriteOrder,
          activeProfileId,
          onSelectProfile: handleSelectProfile,
          sessionBikeType,
          onSelectBike: handleSelectBike,
          santanderMode,
          onSantanderChange: handleSantanderChange,
          bikePulse,
          start,
          end,
          startLabel,
          endLabel,
          vias,
          onChangeWaypoints: handleChangeWaypoints,
          onAddVia: handleAddVia,
          onRemoveVia: handleRemoveVia,
          onFlyTo: (coord) => setFlyTarget(coord),
          departMode,
          departAtIso,
          onDepartChange: ({ mode, departAtIso: iso }) => {
            setDepartMode(mode);
            setDepartAtIso(iso);
            setRouteRevealed(false);
          },
          onGetRoute: handleGetRoute,
          isCalculating: showCalculating,
          canGetRoute,
          onBlocked: handleBlocked,
          onEditFavourites: () => openSidebar({ focus: 'profiles' }),
          startPlaceholder,
          locationAsStart: Boolean(!start && geo.active && geo.location),
          routeStart,
        }}
        mapProps={{
          themeMode,
          flyTarget,
          start,
          end,
          vias,
          onClick: handleMapClick,
          routeRevealed,
          routeLegs,
          activeLegIndex,
          fastestPath: fastestData?.path || null,
          safestPath: safestData?.path || null,
          safestData,
          walkStartPath,
          walkEndPath,
          hireStations,
          hireStep,
          hireNeed,
          pickupStation,
          dropoffStation,
          expandedStationId,
          onStationExpand: handleStationExpand,
          onStationConfirm: handleStationConfirm,
          mapApiRef,
          onNorthUpChange: handleNorthUpChange,
          userLocation: geo.active ? geo.location : null,
          overlayMode,
          units,
          routeHover,
          onRouteHoverChange: setRouteHover,
        }}
        islandProps={{
          visible: Boolean(routeRevealed && safestData),
          safest: activeSafest || safestData,
          fastest: activeFastest || fastestData,
          overlayMode,
          bikeType: sessionBikeType,
          isDarkOutside,
          profile: activeProfile,
          units,
          expanded: islandExpanded,
          onExpandedChange: setIslandExpanded,
          routeHover,
          onIslandHover: setRouteHover,
          santander: Boolean(santanderMode && hireStep === 'done'),
          pickupStation,
          dropoffStation,
          walkStats: hireWalkStats,
          legCount,
          activeLegIndex,
          onChangeLeg: setActiveLegIndex,
          viaCount,
          startCoord: start || null,
          departAtIso: departMode === 'depart_at' ? departAtIso : null,
        }}
        mapControlsProps={{
          onZoomIn: () => mapApiRef.current?.zoomIn?.(),
          onZoomOut: () => mapApiRef.current?.zoomOut?.(),
          locateActive: geo.active,
          locatePending: geo.pending,
          onLocateToggle: geo.toggle,
          northNeedsReset,
          onResetNorth: () => mapApiRef.current?.resetNorth?.(),
          routeRevealed,
          overlayMode,
          isDark: isDarkOutside,
          onSelectOverlayMode: handleSelectOverlayMode,
        }}
        weatherControlProps={{
          visible: Boolean(routeRevealed && safestData),
          startCoord: start || null,
          departAtIso: departMode === 'depart_at' ? departAtIso : null,
          santander: Boolean(santanderMode),
          onExtremeDetected: (warning) => {
            pushAlert({
              type: 'warning',
              message: `Extreme weather detected: ${warning.title}`,
            });
          },
        }}
      />
      {passwordRecoveryPending && <PasswordRecoveryModal themeMode={themeMode} />}
    </>
  );
}

function AppV2Root() {
  const mapApiRef = useRef({});
  const [isDarkOutside, setIsDarkOutside] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const loadNight = async () => {
      try {
        const res = await apiFetch('/night_status', { testMode: false });
        const data = await res.json();
        if (!cancelled && res.ok) setIsDarkOutside(Boolean(data.is_dark));
      } catch {
        if (!cancelled) {
          const forced = process.env.REACT_APP_FORCE_MODE;
          setIsDarkOutside(forced === 'night');
        }
      }
    };
    loadNight();
    const t = setInterval(loadNight, 5 * 60 * 1000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  return (
    <SidebarProvider isDarkOutside={isDarkOutside}>
      <AppV2Inner mapApiRef={mapApiRef} isDarkOutside={isDarkOutside} />
    </SidebarProvider>
  );
}

export default function AppV2() {
  return (
    <AuthProvider>
      <AppV2Root />
    </AuthProvider>
  );
}

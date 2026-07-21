/**
 * Main app: profile-driven cycling route planner (Tuned Cycling).
 * Backend: 4_backend_engine/app.py (port 5000).
 * When changing features or architecture, update 0_documentation/APP_MAIN.md
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import './ui.css';

import CycleMap from './map/CycleMap';
import RouteOverlayPicker from './RouteOverlayPicker';
import PresetWizard from './wizard/PresetWizard';
import { emptyOverlayVisibility, defaultOverlayVisibility } from './routeOverlayCatalog';
import { AuthProvider, useAuth } from './auth/AuthProvider';
import AuthModal from './auth/AuthModal';
import PasswordRecoveryModal from './auth/PasswordRecoveryModal';
import AccountSettingsModal from './components/AccountSettingsModal';
import TopBar from './components/TopBar';
import TestModePanel from './components/TestModePanel';
import RouteLoadingBike, {
  straightLineKm,
  ROUTE_LOADING_MIN_KM,
} from './components/RouteLoadingBike';
import SantanderGuidePill from './components/santander/SantanderGuidePill';
import SantanderSoftBanner from './components/santander/SantanderSoftBanner';
import SantanderUnsuitableModal from './components/santander/SantanderUnsuitableModal';
import SantanderStationsLayer from './components/santander/SantanderStationsLayer';
import './components/santander/santander.css';
import DepartAtControl, {
  formatDepartStatusHint,
  isFutureDepartAt,
} from './components/DepartAtControl';
import RoutePointsPanel, { MAX_VIAS } from './components/RoutePointsPanel';
import LegAnalysisPager from './components/LegAnalysisPager';
import { apiFetch, API_BASE } from './api/flaskClient';
import { pickInactiveLegIndex } from './map/RouteLayers';


const R_MIN = 0.1;

// Schema v2 routing keys (width removed, quietway merged into cycleway,
// vehicular_free added) - must match backend user_profiles.ROUTING_WEIGHT_KEYS.
const ALL_WEIGHT_KEYS = [
  'risk_weight', 'light_weight', 'surface_weight', 'hill_weight',
  'tfl_cycleway_weight', 'vehicular_free_weight', 'speed_weight',
  'green_weight', 'barrier_weight', 'calming_weight', 'junction_weight',
  'signal_weight', 'tfl_live_weight',
];

const METRIC_ROWS = [
  { label: 'Accidents', key: 'accidents', unit: '', invertDiff: false, integer: true },
  { label: 'Lit', key: 'illumination_pct', unit: '%', invertDiff: true },
  { label: 'Rough Surf.', key: 'rough_pct', unit: '%', invertDiff: false },
  { label: 'Elevation', key: 'elevation_gain', unit: 'm', invertDiff: false, integer: true },
  { label: 'Steep Seg.', key: 'steep_count', unit: '', invertDiff: false, integer: true },
  { label: 'TfL network', key: 'tfl_network_pct', unit: '%', invertDiff: true },
  { label: 'Segregated', key: 'vehicular_free_pct', unit: '%', invertDiff: true },
  { label: 'Speed stress', key: 'speed_stress_pct', unit: '%', invertDiff: false },
  { label: 'Green', key: 'green_pct', unit: '%', invertDiff: true },
  { label: 'Barriers', key: 'barrier_count', unit: '', invertDiff: false, integer: true },
  { label: 'Calming', key: 'calming_count', unit: '', invertDiff: false, integer: true },
  { label: 'Signals', key: 'signal_count', unit: '', invertDiff: false, integer: true },
  { label: 'Junctions', key: 'junction_count', unit: '', invertDiff: false, integer: true },
  { label: 'Disruptions', key: 'disruption_count', unit: '', invertDiff: false, integer: true },
];

const emptyWeights = () => Object.fromEntries(ALL_WEIGHT_KEYS.map((k) => [k, 0]));

const togglesToWeights = (t) => ({
  risk_weight: t.useSafetyRouting ? 1 : 0,
  light_weight: t.useLighting ? 1 : 0,
  surface_weight: t.useRoadBike ? 1 : 0,
  hill_weight: t.useHillRouting ? 1 : 0,
  tfl_cycleway_weight: t.useTflCycleway ? 1 : 0,
  vehicular_free_weight: t.useVehicularFree ? 1.5 : 0,
  speed_weight: t.useSpeedStress ? 1 : 0,
  green_weight: t.useGreen ? 1 : 0,
  barrier_weight: t.useBarriers ? 1 : 0,
  calming_weight: t.useCalming ? 1 : 0,
  junction_weight: t.useJunctionDanger ? 1 : 0,
  signal_weight: t.useSignals ? 1 : 0,
  tfl_live_weight: (t.useTflLive || t.useTomtomLive) ? 1 : 0,
});

// Mirrors routing_heuristic.py reward lerps (saturation floors at each cap).
const computeMinWeightPerM = (weights) => {
  let r = 1.0;
  const wTfl = weights.tfl_cycleway_weight || 0;
  if (wTfl > 0) r *= 1.0 - 0.45 * Math.min(wTfl, 1.0);
  const wGreen = weights.green_weight || 0;
  if (wGreen > 0) r *= 1.0 - 0.4 * Math.min(wGreen, 1.0);
  const wVf = weights.vehicular_free_weight || 0;
  if (wVf > 0) r *= 1.0 - 0.15 * Math.min(wVf, 3.0);
  return Math.max(R_MIN, r);
};

const formatRouteStatus = (minWeight, timingMs, profileName) => {
  const timeLabel = timingMs >= 1000
    ? `${(timingMs / 1000).toFixed(1)}s`
    : `${Math.round(timingMs)} ms`;
  const profileBit = profileName ? ` | ${profileName}` : '';
  return `Route calculated in ${timeLabel} | min weight/m: ${minWeight.toFixed(3)}${profileBit}`;
};

// --- STYLES & COMPONENTS ---

const RouteHeroCard = ({ label, fastest, optimized, unit, theme, walkValue, cycleMode }) => {
  const f = parseFloat(fastest);
  const o = parseFloat(optimized);
  const diff = o - f;
  const fmt = (n) => n.toFixed(1);
  const displayDiff = (diff > 0 ? '+' : '') + fmt(diff);
  const diffColor = diff > 0 ? '#f44336' : diff < 0 ? '#4CAF50' : theme.textSub;
  const hasWalk = walkValue != null && Number.isFinite(Number(walkValue));
  return (
    <div className="ui-hero-card">
      <div className="ui-hero-card__label">{label}</div>
      <div className="ui-hero-card__values">
        {hasWalk && (
          <div className="ui-hero-card__walk">
            + {fmt(Number(walkValue))} {unit} (walk)
          </div>
        )}
        <div className="ui-hero-card__main">
          <span className="ui-hero-card__value">{fmt(o)}</span>
          <span className="ui-hero-card__unit">
            {unit}{cycleMode ? ' (cycle)' : ''}
          </span>
        </div>
      </div>
      <div className="ui-hero-card__foot">
        <span className="ui-hero-card__baseline">vs fastest: {fmt(f)} {unit}</span>
        <span className="ui-hero-card__delta" style={{ color: diffColor }}>
          {displayDiff} {unit}
        </span>
      </div>
    </div>
  );
};

const resolveMetricValue = (stats, key) => {
  if (!stats) return NaN;
  if (key === 'tfl_network_pct') {
    const direct = parseFloat(stats.tfl_network_pct);
    if (Number.isFinite(direct)) return direct;
    const cw = parseFloat(stats.tfl_cycleway_pct);
    const qw = parseFloat(stats.tfl_quietway_pct);
    if (Number.isFinite(cw) || Number.isFinite(qw)) {
      return (Number.isFinite(cw) ? cw : 0) + (Number.isFinite(qw) ? qw : 0);
    }
    return NaN;
  }
  return parseFloat(stats[key]);
};

const CondensedStatRow = ({ label, statKey, statsFastest, statsOptimized, unit, invertDiff, integer, theme }) => {
  const f = resolveMetricValue(statsFastest, statKey);
  const o = resolveMetricValue(statsOptimized, statKey);
  const diff = o - f;
  const fmt = integer ? (n) => Math.round(n) : (n) => n.toFixed(1);
  const fmtVal = (n) => (Number.isFinite(n) ? fmt(n) : '—');
  const displayDiff = Number.isFinite(diff)
    ? `${diff > 0 ? '+' : ''}${fmt(diff)}`
    : '—';
  let diffColor = theme.textSub;
  if (Number.isFinite(diff)) {
    if (!invertDiff) {
      if (diff < 0) diffColor = '#4CAF50';
      if (diff > 0) diffColor = '#f44336';
    } else {
      if (diff > 0) diffColor = '#4CAF50';
      if (diff < 0) diffColor = '#f44336';
    }
  }
  return (
    <div className="ui-stats-row">
      <span>{label}</span>
      <span>{fmtVal(o)}{unit ? ` ${unit}` : ''}</span>
      <span style={{ color: diffColor }}>{displayDiff}{unit && Number.isFinite(diff) ? ` ${unit}` : ''}</span>
    </div>
  );
};

// --- TfL / TomTom DISRUPTION DETAIL WINDOWS ---
const formatDisruptionValue = (v) => {
  if (v === undefined || v === null) return '—';
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v);
  return JSON.stringify(v, null, 2);
};

const TflDisruptionDetailWindow = ({ disruptions, position, onClose, theme }) => {
  if (!disruptions?.length || !position) return null;
  const maxPanelHeight = Math.min(480, 75 * window.innerHeight / 100);
  const panelWidth = Math.min(420, 90 * window.innerWidth / 100);
  return (
    <div style={{
      position: 'absolute',
      left: Math.min(position.x + 16, window.innerWidth - panelWidth - 16),
      top: Math.min(position.y - 24, window.innerHeight - maxPanelHeight - 16),
      background: theme.bg, color: theme.textMain, padding: '12px', borderRadius: '8px',
      boxShadow: '0 4px 15px rgba(0,0,0,0.5)', zIndex: 2000, width: panelWidth,
      maxWidth: '92vw', maxHeight: maxPanelHeight, overflow: 'hidden',
      display: 'flex', flexDirection: 'column', fontSize: '11px', border: `1px solid ${theme.border}`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', borderBottom: `1px solid ${theme.border}`, flexShrink: 0 }}>
        <strong style={{ fontSize: '13px' }}>TfL disruption data</strong>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: theme.textSub, cursor: 'pointer', padding: '0 4px' }}>✕</button>
      </div>
      <div style={{ overflowY: 'auto', flex: 1, minHeight: 0 }}>
        {disruptions.map((d, idx) => {
          const id = d.id ?? d.disruptionId ?? `#${idx + 1}`;
          return (
            <div key={id} style={{ marginBottom: idx < disruptions.length - 1 ? '16px' : 0 }}>
              {disruptions.length > 1 && (
                <div style={{ fontWeight: 'bold', color: theme.textSub, marginBottom: '6px', fontSize: '10px' }}>Disruption {idx + 1}: {id}</div>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                {Object.keys(d).sort().map((k) => (
                  <div key={k} style={{ lineHeight: 1.4, borderBottom: `1px solid ${theme.border}`, paddingBottom: '4px', marginBottom: '4px' }}>
                    <span style={{ color: theme.textSub, fontWeight: '600', fontSize: '10px' }}>{k}:</span>
                    <div style={{ wordBreak: 'break-word', fontSize: '11px', marginTop: '2px' }}>{formatDisruptionValue(d[k])}</div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const TomtomDisruptionDetailWindow = ({ disruptions, position, onClose, theme }) => {
  if (!disruptions?.length || !position) return null;
  const maxPanelHeight = Math.min(480, 75 * window.innerHeight / 100);
  const panelWidth = Math.min(420, 90 * window.innerWidth / 100);
  return (
    <div style={{
      position: 'absolute',
      left: Math.min(position.x + 16, window.innerWidth - panelWidth - 16),
      top: Math.min(position.y - 24, window.innerHeight - maxPanelHeight - 16),
      background: theme.bg, color: theme.textMain, padding: '12px', borderRadius: '8px',
      boxShadow: '0 4px 15px rgba(0,0,0,0.5)', zIndex: 2000, width: panelWidth,
      maxWidth: '92vw', maxHeight: maxPanelHeight, overflow: 'hidden',
      display: 'flex', flexDirection: 'column', fontSize: '11px', border: `1px solid ${theme.border}`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', borderBottom: `1px solid ${theme.border}`, flexShrink: 0 }}>
        <strong style={{ fontSize: '13px' }}>TomTom disruption data</strong>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: theme.textSub, cursor: 'pointer', padding: '0 4px' }}>✕</button>
      </div>
      <div style={{ overflowY: 'auto', flex: 1, minHeight: 0 }}>
        {disruptions.map((d, idx) => {
          const id = (d.properties && d.properties.id) ?? d.id ?? `#${idx + 1}`;
          return (
            <div key={String(id)} style={{ marginBottom: idx < disruptions.length - 1 ? '16px' : 0 }}>
              {disruptions.length > 1 && (
                <div style={{ fontWeight: 'bold', color: theme.textSub, marginBottom: '6px', fontSize: '10px' }}>Incident {idx + 1}: {id}</div>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                {Object.keys(d).sort().map((k) => (
                  <div key={k} style={{ lineHeight: 1.4, borderBottom: `1px solid ${theme.border}`, paddingBottom: '4px', marginBottom: '4px' }}>
                    <span style={{ color: theme.textSub, fontWeight: '600', fontSize: '10px' }}>{k}:</span>
                    <div style={{ wordBreak: 'break-word', fontSize: '11px', marginTop: '2px' }}>{formatDisruptionValue(d[k])}</div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const InspectorWindow = ({ data, position, onClose, theme }) => {
    const [expanded, setExpanded] = useState(false);
    const coreKeys = ['name', 'surface', 'maxspeed', 'grade', 'length', 'elevation_start', 'elevation_end', 'barrier', 'barrier_lat', 'barrier_lon', 'give_way', 'give_way_lat', 'give_way_lon', 'stop_sign', 'stop_sign_lat', 'stop_sign_lon', 'tfl_live_category', 'tfl_live_severity', 'tfl_live_description'];
    const content = expanded ? data : Object.keys(data)
        .filter(key => coreKeys.includes(key))
        .reduce((obj, key) => { obj[key] = data[key]; return obj; }, {});

    return (
        <div style={{
            position: 'absolute', left: position.x + 20, top: position.y - 40,
            background: theme.bg, color: theme.textMain, padding: '15px', borderRadius: '8px',
            boxShadow: '0 4px 15px rgba(0,0,0,0.5)', zIndex: 2000, maxWidth: '250px', fontSize: '12px'
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', borderBottom: `1px solid ${theme.border}` }}>
                <strong style={{ fontSize: '14px' }}>Segment Inspector</strong>
                <button onClick={onClose} style={{ background: 'none', border: 'none', color: theme.textSub, cursor: 'pointer' }}>✕</button>
            </div>
            {Object.entries(content).map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span style={{ color: theme.textSub }}>{k}:</span>
                    <span style={{ fontWeight: 'bold' }}>{v}</span>
                </div>
            ))}
            <button onClick={() => setExpanded(!expanded)} style={{
                marginTop: '10px', width: '100%', padding: '5px',
                background: theme.toggleInactive, color: theme.textMain,
                border: 'none', borderRadius: '4px', cursor: 'pointer'
            }}>
                {expanded ? "Show Less" : "Show All Tags"}
            </button>
        </div>
    );
};

// --- MAIN APP ---

function AppInner() {
  const { user, isLoading: authLoading, authNotice, passwordRecoveryPending } = useAuth();
  const [start, setStart] = useState(null);
  const [end, setEnd] = useState(null);
  const [startLabel, setStartLabel] = useState('');
  const [endLabel, setEndLabel] = useState('');
  /** @type {[{id:string, coord:[number,number]|null, label:string}]} */
  const [vias, setVias] = useState([]);
  const [routeLegs, setRouteLegs] = useState(null); // array from /route legs, or null
  const [activeLegIndex, setActiveLegIndex] = useState(0);
  const routeRequestIdRef = useRef(0);
  const abortRef = useRef(null);
  const [flyTarget, setFlyTarget] = useState(null);
  const [status, setStatus] = useState("Loading profiles...");

  const [profiles, setProfiles] = useState([]);
  const [activeProfileId, setActiveProfileId] = useState(
    () => localStorage.getItem('activeProfileId') || 'preset_safe'
  );
  const [activeProfile, setActiveProfile] = useState(null);
  const [testMode, setTestMode] = useState(false);
  const [manualWeightsMode, setManualWeightsMode] = useState(false);
  const [showWizard, setShowWizard] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [showAccountSettings, setShowAccountSettings] = useState(false);
  const [routeRevealed, setRouteRevealed] = useState(false);
  const [isCalculating, setIsCalculating] = useState(false);
  const [showLongRouteLoading, setShowLongRouteLoading] = useState(false);
  const [longRouteLoadingKey, setLongRouteLoadingKey] = useState(0);
  const [lastRouteMeta, setLastRouteMeta] = useState(null);
  const routeRevealedRef = useRef(false);
  useEffect(() => { routeRevealedRef.current = routeRevealed; }, [routeRevealed]);

  const [fastestData, setFastestData] = useState(null);
  const [safestData, setSafestData] = useState(null);
  const [litSegments, setLitSegments] = useState([]);
  const [steepSegments, setSteepSegments] = useState([]);
  const [tflCyclewayChunks, setTflCyclewayChunks] = useState([]);
  const [greenChunks, setGreenChunks] = useState([]);
  const [vehicularFreeChunks, setVehicularFreeChunks] = useState([]);
  const [disruptionChunks, setDisruptionChunks] = useState([]);
  const [nodeHighlights, setNodeHighlights] = useState([]);
  const [overlayVisibility, setOverlayVisibility] = useState(emptyOverlayVisibility);

  const [useSafetyRouting, setUseSafetyRouting] = useState(true);
  const [useLighting, setUseLighting] = useState(false);
  const [useTflCycleway, setUseTflCycleway] = useState(false);
  const [useVehicularFree, setUseVehicularFree] = useState(false);
  const [useSpeedStress, setUseSpeedStress] = useState(false);
  const [useSignals, setUseSignals] = useState(false);
  const [useBarriers, setUseBarriers] = useState(false);
  const [useJunctionDanger, setUseJunctionDanger] = useState(false);
  const [useTflLive, setUseTflLive] = useState(false);
  const [useTomtomLive, setUseTomtomLive] = useState(false);
  const [tflDisruptionStatus, setTflDisruptionStatus] = useState('');
  const [tomtomDisruptionStatus, setTomtomDisruptionStatus] = useState('');
  const [tflDisruptionDetail, setTflDisruptionDetail] = useState(null);
  const [tomtomDisruptionDetail, setTomtomDisruptionDetail] = useState(null);
  const [useRoadBike, setUseRoadBike] = useState(false);
  const [useHillRouting, setUseHillRouting] = useState(false);
  const [useCalming, setUseCalming] = useState(false);
  const [useGreen, setUseGreen] = useState(false);

  const [inspectorData, setInspectorData] = useState(null);
  const [inspectorPos, setInspectorPos] = useState(null);
  const [inspectorGeo, setInspectorGeo] = useState(null);

  // Santander Cycles hire mode (independent of riding profile)
  const [santanderMode, setSantanderMode] = useState(false);
  const [hireStep, setHireStep] = useState('idle'); // idle | pickup | dropoff | routing | done
  const [hireStations, setHireStations] = useState([]);
  const [pickupStation, setPickupStation] = useState(null);
  const [dropoffStation, setDropoffStation] = useState(null);
  const [hireBanner, setHireBanner] = useState('');
  const [hireGuide, setHireGuide] = useState('');
  const [unsuitableModal, setUnsuitableModal] = useState(null);
  const [walkStartPath, setWalkStartPath] = useState(null);
  const [walkEndPath, setWalkEndPath] = useState(null);
  const [hireWalkStats, setHireWalkStats] = useState(null); // { duration_min, distance_m }
  const [expandedStationId, setExpandedStationId] = useState(null);
  const santanderModeRef = useRef(false);
  useEffect(() => { santanderModeRef.current = santanderMode; }, [santanderMode]);

  // Leave now / Depart at (Europe/London ISO or null)
  const [departMode, setDepartMode] = useState('now'); // now | depart_at
  const [departAtIso, setDepartAtIso] = useState(null);

  const theme = useLighting ? {
      mode: 'dark', bg: '#1a1a1a',
      textMain: '#e0e0e0', textSub: '#a0a0a0', border: '#333', toggleInactive: '#444',
      routeGrey: '#ffffff', routeOptimized: '#40E0D0', litColor: '#FFFF00', steepColor: '#00FF00',
      tflCyclewayColor: '#2196F3', greenColor: '#009688', vehicularFreeColor: '#7B1FA2',
      nodeBarrier: '#5D4037', nodeSignal: '#F57C00', nodeJunction: '#795548', nodeCalming: '#00838F',
      disruptionColor: '#FF0000',
  } : {
      mode: 'light', bg: 'white',
      textMain: '#333', textSub: '#666', border: '#f0f0f0', toggleInactive: '#ccc',
      routeGrey: '#555', routeOptimized: '#d32f2f', litColor: '#FFD700', steepColor: '#00cc00',
      tflCyclewayColor: '#1976D2', greenColor: '#00796B', vehicularFreeColor: '#7B1FA2',
      nodeBarrier: '#5D4037', nodeSignal: '#F57C00', nodeJunction: '#795548', nodeCalming: '#00838F',
      disruptionColor: '#FFD700',
  };

  const toggleState = {
    useSafetyRouting, useLighting, useRoadBike, useHillRouting,
    useTflCycleway, useGreen, useSpeedStress, useVehicularFree,
    useBarriers, useCalming, useJunctionDanger, useSignals, useTflLive, useTomtomLive,
  };

  // Manual weight overrides only apply inside Test Mode (nested sub-toggle).
  const manualWeightsActive = testMode && manualWeightsMode;

  const effectiveWeights = manualWeightsActive
    ? togglesToWeights(toggleState)
    : (activeProfile?.weights || emptyWeights());

  // Leaving Test Mode also leaves manual-weights mode.
  useEffect(() => {
    if (!testMode) setManualWeightsMode(false);
  }, [testMode]);

  const loadProfileList = useCallback(async () => {
    try {
      const res = await apiFetch('/profiles', { testMode });
      const data = await res.json();
      setProfiles(data.profiles || []);
    } catch {
      setStatus('Could not load profiles');
    }
  }, [testMode]);

  const loadActiveProfile = useCallback(async (profileId) => {
    try {
      const res = await apiFetch(`/profiles/${profileId}`, { testMode });
      if (!res.ok) {
        // Stored id no longer accessible (signed out / other store) - fall back.
        if (profileId !== 'preset_safe') setActiveProfileId('preset_safe');
        return;
      }
      const data = await res.json();
      setActiveProfile(data);
    } catch { /* ignore */ }
  }, [testMode]);

  // Defer all profile fetching until the Supabase session check has resolved
  // (no guest-state fetch that would be redone as logged-in a moment later).
  const authReady = testMode || !authLoading;

  useEffect(() => {
    if (!authReady) return;
    loadProfileList();
  }, [authReady, loadProfileList, user?.id]);

  useEffect(() => {
    if (!authReady || !activeProfileId) return;
    localStorage.setItem('activeProfileId', activeProfileId);
    loadActiveProfile(activeProfileId);
  }, [authReady, activeProfileId, loadActiveProfile, user?.id]);

  useEffect(() => {
    if (authNotice) setStatus(authNotice);
  }, [authNotice]);

  useEffect(() => {
    // Dev override via `npm start -- --day|--night` (see 5_frontend/start.js).
    const forcedMode = (process.env.REACT_APP_FORCE_MODE || '').toLowerCase();
    if (forcedMode === 'day' || forcedMode === 'night') {
        setUseLighting(forcedMode === 'night');
        setStatus(`Forced ${forcedMode} mode (dev). Tuned Cycling — click map to start.`);
        return;
    }
    const checkDaylight = async () => {
        try {
            const response = await fetch("https://api.sunrise-sunset.org/json?lat=51.5&lng=-0.1&formatted=0");
            const data = await response.json();
            if (data.status === "OK") {
                const now = new Date();
                const sunrise = new Date(data.results.sunrise);
                const sunset = new Date(data.results.sunset);
                const isDark = now < sunrise || now > sunset;
                if (isDark) {
                    setUseLighting(true);
                    setStatus("Night detected. Dark Mode ON.");
                } else if (!testMode) {
                    setStatus("Tuned Cycling — click map to start.");
                }
            }
        } catch {
            setStatus("Tuned Cycling — click map to start.");
        }
    };
    checkDaylight();
  }, [testMode]);

  const clearRouteData = useCallback(() => {
    setFastestData(null);
    setSafestData(null);
    setLitSegments([]);
    setSteepSegments([]);
    setTflCyclewayChunks([]);
    setGreenChunks([]);
    setVehicularFreeChunks([]);
    setDisruptionChunks([]);
    setNodeHighlights([]);
    setLastRouteMeta(null);
    setRouteLegs(null);
    setActiveLegIndex(0);
  }, []);

  const bumpRouteRequest = useCallback(() => {
    routeRequestIdRef.current += 1;
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch (_) { /* ignore */ }
      abortRef.current = null;
    }
    return routeRequestIdRef.current;
  }, []);

  const resetHireState = useCallback(() => {
    setHireStep('idle');
    setHireStations([]);
    setPickupStation(null);
    setDropoffStation(null);
    setHireBanner('');
    setHireGuide('');
    setUnsuitableModal(null);
    setWalkStartPath(null);
    setWalkEndPath(null);
    setHireWalkStats(null);
    setExpandedStationId(null);
  }, []);

  const applyCandidateResponse = useCallback((data, need) => {
    const suitable = data.suitable_count ?? 0;
    const total = data.total_in_radius ?? 0;
    const shown = data.shown || [];
    if (total === 0) {
      setHireStations([]);
      setHireBanner('No Santander stations within 1.5 km');
      return;
    }
    if (suitable === 0) {
      setHireStations([]);
      const kind = need === 'docks' ? 'empty docks' : 'bikes';
      setHireBanner(`No suitable Santander station with ${kind} within 1.5 km`);
      return;
    }
    setHireStations(shown);
    if (suitable < 3) {
      const kind = need === 'docks' ? 'empty docks' : 'bikes';
      setHireBanner(`Only ${suitable} station${suitable === 1 ? '' : 's'} with ${kind} nearby`);
    } else {
      setHireBanner('');
    }
  }, []);

  const fetchHireCandidates = useCallback(async (lat, lon, need) => {
    const params = new URLSearchParams({
      lat: String(lat),
      lon: String(lon),
      need,
      radius_m: '1500',
    });
    const res = await apiFetch(`/santander/candidates?${params}`, { testMode });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    applyCandidateResponse(data, need);
    return data;
  }, [applyCandidateResponse, testMode]);

  const setStartPoint = useCallback((lat, lon, label) => {
    bumpRouteRequest();
    setStart([lat, lon]);
    setStartLabel(label ?? `${lat.toFixed(4)}, ${lon.toFixed(4)}`);
    setRouteRevealed(false);
    resetHireState();
    if (santanderModeRef.current) {
      setStatus(end ? 'Ready — click Get Route to pick Santander stations' : 'Set Destination.');
    } else {
      setStatus(end ? 'Calculating route in background...' : 'Set Destination.');
    }
  }, [end, resetHireState, bumpRouteRequest]);

  const setEndPoint = useCallback((lat, lon, label) => {
    bumpRouteRequest();
    setEnd([lat, lon]);
    setEndLabel(label ?? `${lat.toFixed(4)}, ${lon.toFixed(4)}`);
    setRouteRevealed(false);
    resetHireState();
    if (santanderModeRef.current) {
      setStatus('Ready — click Get Route to pick Santander stations');
    } else {
      setStatus('Calculating route in background...');
    }
  }, [resetHireState, bumpRouteRequest]);

  const handleStartSearchSelect = useCallback(({ lat, lon, label }) => {
    setStartPoint(lat, lon, label);
    setFlyTarget([lat, lon]);
  }, [setStartPoint]);

  const handleEndSearchSelect = useCallback(({ lat, lon, label }) => {
    setEndPoint(lat, lon, label);
    setFlyTarget([lat, lon]);
  }, [setEndPoint]);

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
    }
    if (next.start && next.end && !(next.vias || []).some((v) => !v.coord)) {
      setStatus('Calculating route in background...');
    }
  }, [bumpRouteRequest, resetHireState, clearRouteData]);

  const handleAddVia = useCallback(() => {
    if (vias.length >= MAX_VIAS) return;
    bumpRouteRequest();
    // TODO(later): allow vias on Santander station→station bike leg instead of mutual exclusion.
    if (santanderMode) {
      setSantanderMode(false);
      resetHireState();
    }
    setVias((prev) => [
      ...prev,
      { id: `via-${Date.now()}`, coord: null, label: '' },
    ]);
    setRouteRevealed(false);
    clearRouteData();
    setStatus('Set the new stop, then Get Route');
  }, [vias.length, santanderMode, bumpRouteRequest, resetHireState, clearRouteData]);

  const handleRemoveVia = useCallback((viaIndex) => {
    bumpRouteRequest();
    setVias((prev) => prev.filter((_, i) => i !== viaIndex));
    setRouteRevealed(false);
    clearRouteData();
  }, [bumpRouteRequest, clearRouteData]);

  const handleSwapStartEnd = useCallback(() => {
    if (vias.length > 0 || !start || !end) return;
    bumpRouteRequest();
    setStart(end);
    setEnd(start);
    setStartLabel(endLabel);
    setEndLabel(startLabel);
    setRouteRevealed(false);
    clearRouteData();
    setStatus('Calculating route in background...');
  }, [vias.length, start, end, startLabel, endLabel, bumpRouteRequest, clearRouteData]);

  const minWeightPreview = computeMinWeightPerM(effectiveWeights);

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
    // Incomplete vias (empty slots) — wait until filled.
    if ((viasArg || []).some((v) => !v.coord)) {
      setStatus('Fill all stops to calculate a route');
      return;
    }

    const reqId = bumpRouteRequest();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsCalculating(true);
    if (routeRevealedRef.current) {
      setStatus(`Calculating... | min weight/m: ${minWeightPreview.toFixed(3)}`);
    } else {
      setStatus(purpose === 'commit' ? 'Calculating route...' : 'Calculating route in background...');
    }
    const params = new URLSearchParams({
      start_lat: startCoord[0], start_lon: startCoord[1],
      end_lat: endCoord[0], end_lon: endCoord[1],
      purpose,
    });
    const viasStr = encodeViasParam(viasArg);
    if (viasStr) params.set('vias', viasStr);
    if (manualWeightsActive) {
      const w = togglesToWeights(toggleState);
      ALL_WEIGHT_KEYS.forEach((k) => params.set(k, w[k]));
    } else if (activeProfileId) {
      params.set('profile_id', activeProfileId);
    }
    if (departMode === 'depart_at' && departAtIso) {
      params.set('depart_at', departAtIso);
    }
    try {
      const response = await apiFetch(`/route?${params}`, { testMode, signal: controller.signal });
      if (reqId !== routeRequestIdRef.current) return;
      const data = await response.json();
      if (reqId !== routeRequestIdRef.current) return;
      if (response.status === 429) {
        setStatus(data.error || 'Too many route requests — try again shortly');
        return;
      }
      if (data.status === "success") {
        setFastestData(data.fastest);
        setSafestData(data.safest);
        setLitSegments(data.safest.lit_chunks || []);
        setSteepSegments(data.safest.steep_chunks || []);
        setTflCyclewayChunks(data.safest.tfl_cycleway_chunks || []);
        setGreenChunks(data.safest.green_chunks || []);
        setVehicularFreeChunks(data.safest.vehicular_free_chunks || []);
        setDisruptionChunks(data.safest.disruption_chunks || []);
        setNodeHighlights(data.safest.node_highlights || []);
        const legs = Array.isArray(data.legs) && data.legs.length ? data.legs : null;
        setRouteLegs(legs);
        setActiveLegIndex(0);
        const meta = data.meta || {};
        const minWeight = meta.cost_per_m_lower_bound ?? minWeightPreview;
        const timingMs = meta.timing_ms?.total ?? 0;
        const profileName = manualWeightsActive ? 'Manual weights' : (activeProfile?.name || '');
        const metaBundle = {
          minWeight, timingMs, profileName,
          bikeType: meta.bike_type, preset: meta.preset,
          clamps: meta.translation_clamps || [],
          lightGatedOff: !!meta.light_gated_off,
          lightingActive: (meta.weights?.light_weight ?? 0) > 0,
          liveApplied: meta.live_applied !== false,
          departMode: meta.depart_mode || 'now',
          legCount: meta.leg_count || (legs ? legs.length : 1),
        };
        setLastRouteMeta(metaBundle);
        const departHint = formatDepartStatusHint(departMode, departAtIso);
        setStatus(routeRevealedRef.current
          ? (departHint
            ? `${formatRouteStatus(minWeight, timingMs, profileName)} · ${departHint}`
            : formatRouteStatus(minWeight, timingMs, profileName))
          : 'Route ready — click Get Route');
      } else {
        setStatus("Error: " + data.error);
      }
    } catch (err) {
      if (err?.name === 'AbortError') return;
      if (reqId !== routeRequestIdRef.current) return;
      setStatus("Backend Error.");
    } finally {
      if (reqId === routeRequestIdRef.current) {
        setIsCalculating(false);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    start, end, vias, testMode, manualWeightsActive, activeProfileId, activeProfile, minWeightPreview,
    useSafetyRouting, useLighting, useRoadBike, useHillRouting,
    useTflCycleway, useGreen, useSpeedStress, useVehicularFree,
    useBarriers, useCalming, useJunctionDanger, useSignals, useTflLive, useTomtomLive,
    departMode, departAtIso, bumpRouteRequest, encodeViasParam,
  ]);

  useEffect(() => {
    if (!start || !end) return;
    if (santanderMode) {
      setRouteRevealed(false);
      clearRouteData();
      return;
    }
    if (vias.some((v) => !v.coord)) return;
    setRouteRevealed(false);
    fetchRoutes(start, end, vias, 'prefetch');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    start, end, vias, activeProfileId, testMode, manualWeightsActive, santanderMode,
    useSafetyRouting, useLighting, useRoadBike, useHillRouting,
    useTflCycleway, useGreen, useSpeedStress, useVehicularFree,
    useBarriers, useCalming, useJunctionDanger, useSignals, useTflLive, useTomtomLive,
    departMode, departAtIso,
  ]);

  useEffect(() => {
    if (routeRevealed && !isCalculating && lastRouteMeta) {
      const base = formatRouteStatus(lastRouteMeta.minWeight, lastRouteMeta.timingMs, lastRouteMeta.profileName);
      const departHint = formatDepartStatusHint(departMode, departAtIso);
      setStatus(departHint ? `${base} · ${departHint}` : base);
    }
  }, [routeRevealed, isCalculating, lastRouteMeta, departMode, departAtIso]);

  const beginPickupStep = useCallback(async () => {
    if (!start || !end) return;
    setOverlayVisibility(defaultOverlayVisibility());
    setRouteRevealed(false);
    clearRouteData();
    setWalkStartPath(null);
    setWalkEndPath(null);
    setHireWalkStats(null);
    setPickupStation(null);
    setDropoffStation(null);
    setExpandedStationId(null);
    setHireStep('pickup');
    setHireGuide('Please select a pick-up station');
    setHireBanner('');
    setFlyTarget({ center: start, zoom: 16, duration: 0.9 });
    setStatus('Select a Santander pick-up station');
    setIsCalculating(true);
    try {
      await fetchHireCandidates(start[0], start[1], 'bikes');
    } catch (e) {
      setHireBanner(e.message || 'Could not load Santander stations');
      setHireStations([]);
    } finally {
      setIsCalculating(false);
    }
  }, [start, end, clearRouteData, fetchHireCandidates]);

  const commitPickup = useCallback(async (station) => {
    setExpandedStationId(null);
    setPickupStation(station);
    setHireStep('dropoff');
    setHireGuide('Please select a drop-off station');
    setHireBanner('');
    setFlyTarget({ center: end, zoom: 16, duration: 0.9 });
    setStatus('Select a Santander drop-off station');
    setIsCalculating(true);
    try {
      await fetchHireCandidates(end[0], end[1], 'docks');
    } catch (e) {
      setHireBanner(e.message || 'Could not load Santander stations');
      setHireStations([]);
    } finally {
      setIsCalculating(false);
    }
  }, [end, fetchHireCandidates]);

  const fetchWalkLeg = useCallback(async (from, to) => {
    try {
      const res = await apiFetch('/santander/walk', {
        method: 'POST',
        testMode,
        body: { from, to },
      });
      const data = await res.json();
      if (!res.ok || data.error) return null;
      return data;
    } catch {
      return null;
    }
  }, [testMode]);

  const commitDropoff = useCallback(async (station) => {
    if (!start || !end || !pickupStation) return;
    setExpandedStationId(null);
    setDropoffStation(station);
    setHireStep('routing');
    setHireGuide('');
    setHireBanner('');
    setHireStations([]);
    setIsCalculating(true);
    setStatus('Calculating Santander route...');
    setOverlayVisibility(defaultOverlayVisibility());

    const bikeParams = new URLSearchParams({
      start_lat: String(pickupStation.lat),
      start_lon: String(pickupStation.lon),
      end_lat: String(station.lat),
      end_lon: String(station.lon),
    });
    if (manualWeightsActive) {
      const w = togglesToWeights(toggleState);
      ALL_WEIGHT_KEYS.forEach((k) => bikeParams.set(k, w[k]));
    } else if (activeProfileId) {
      bikeParams.set('profile_id', activeProfileId);
    }
    if (departMode === 'depart_at' && departAtIso) {
      bikeParams.set('depart_at', departAtIso);
    }

    try {
      const [routeRes, walkA, walkB] = await Promise.all([
        apiFetch(`/route?${bikeParams}`, { testMode }),
        fetchWalkLeg(start, [pickupStation.lat, pickupStation.lon]),
        fetchWalkLeg([station.lat, station.lon], end),
      ]);
      const data = await routeRes.json();
      if (data.status === 'success') {
        setFastestData(data.fastest);
        setSafestData(data.safest);
        setLitSegments(data.safest.lit_chunks || []);
        setSteepSegments(data.safest.steep_chunks || []);
        setTflCyclewayChunks(data.safest.tfl_cycleway_chunks || []);
        setGreenChunks(data.safest.green_chunks || []);
        setVehicularFreeChunks(data.safest.vehicular_free_chunks || []);
        setDisruptionChunks(data.safest.disruption_chunks || []);
        setNodeHighlights(data.safest.node_highlights || []);
        const meta = data.meta || {};
        const minWeight = meta.cost_per_m_lower_bound ?? minWeightPreview;
        const timingMs = meta.timing_ms?.total ?? 0;
        const profileName = manualWeightsActive ? 'Manual weights' : (activeProfile?.name || '');
        setLastRouteMeta({
          minWeight, timingMs, profileName,
          bikeType: meta.bike_type, preset: meta.preset,
          clamps: meta.translation_clamps || [],
          lightGatedOff: !!meta.light_gated_off,
          lightingActive: (meta.weights?.light_weight ?? 0) > 0,
          santander: true,
          liveApplied: meta.live_applied !== false,
          departMode: meta.depart_mode || 'now',
        });
        setWalkStartPath(walkA?.path || [start, [pickupStation.lat, pickupStation.lon]]);
        setWalkEndPath(walkB?.path || [[station.lat, station.lon], end]);
        const walkDur = (Number(walkA?.duration_min) || 0) + (Number(walkB?.duration_min) || 0);
        const walkDistM = (Number(walkA?.distance_m) || 0) + (Number(walkB?.distance_m) || 0);
        const fallbackDur = (Number(pickupStation.walk_estimate_min) || 0)
          + (Number(station.walk_estimate_min) || 0);
        setHireWalkStats({
          duration_min: walkDur > 0 ? walkDur : (fallbackDur || null),
          distance_m: walkDistM > 0 ? walkDistM : null,
        });
        if (walkA?.duration_min != null) {
          setPickupStation((prev) => prev ? { ...prev, walk_duration_min: walkA.duration_min } : prev);
        }
        if (walkB?.duration_min != null) {
          setDropoffStation({ ...station, walk_duration_min: walkB.duration_min });
        } else {
          setDropoffStation(station);
        }
        setRouteRevealed(true);
        setHireStep('done');
        const departHint = formatDepartStatusHint(departMode, departAtIso);
        setStatus(departHint
          ? `${formatRouteStatus(minWeight, timingMs, profileName)} · ${departHint}`
          : formatRouteStatus(minWeight, timingMs, profileName));
        setFlyTarget({
          center: [
            (pickupStation.lat + station.lat) / 2,
            (pickupStation.lon + station.lon) / 2,
          ],
          zoom: 13,
          duration: 1.0,
        });
      } else {
        setStatus(`Error: ${data.error}`);
        setHireStep('dropoff');
        setHireGuide('Please select a drop-off station');
      }
    } catch {
      setStatus('Backend Error.');
      setHireStep('dropoff');
      setHireGuide('Please select a drop-off station');
    } finally {
      setIsCalculating(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    start, end, pickupStation, testMode, manualWeightsActive, activeProfileId, activeProfile,
    minWeightPreview, fetchWalkLeg, departMode, departAtIso,
  ]);

  const handleStationExpand = useCallback((station) => {
    if (hireStep !== 'pickup' && hireStep !== 'dropoff') return;
    setExpandedStationId((prev) => (prev === station.id ? null : station.id));
  }, [hireStep]);

  const handleStationConfirm = useCallback((station) => {
    if (hireStep !== 'pickup' && hireStep !== 'dropoff') return;
    const unsuitable = hireStep === 'pickup'
      ? !(station.nb_bikes > 0)
      : !(station.nb_empty > 0);
    if (unsuitable) {
      setUnsuitableModal({
        station,
        title: hireStep === 'pickup' ? 'No bikes available' : 'No empty docks',
        message: hireStep === 'pickup'
          ? 'This station currently has no bikes. Proceed anyway?'
          : 'This station currently has no empty docks for drop-off. Proceed anyway?',
      });
      return;
    }
    if (hireStep === 'pickup') commitPickup(station);
    else commitDropoff(station);
  }, [hireStep, commitPickup, commitDropoff]);

  const handleGetRoute = () => {
    if (!start || !end) return;
    if (vias.some((v) => !v.coord)) {
      setStatus('Fill all stops before getting a route');
      return;
    }

    if (santanderMode) {
      beginPickupStep();
      return;
    }

    setOverlayVisibility(defaultOverlayVisibility());

    // Always commit-fetch so the Get Route press counts toward the IP rate limit
    // (prefetch is intentionally free and not counted).
    const longHop = straightLineKm(start, end) > ROUTE_LOADING_MIN_KM;
    if (longHop) {
      setRouteRevealed(false);
      setLongRouteLoadingKey((k) => k + 1);
      setShowLongRouteLoading(true);
      setStatus(`Calculating... | min weight/m: ${minWeightPreview.toFixed(3)}`);
      fetchRoutes(start, end, vias, 'commit');
      return;
    }

    setShowLongRouteLoading(false);
    setRouteRevealed(true);
    setStatus(`Calculating... | min weight/m: ${minWeightPreview.toFixed(3)}`);
    fetchRoutes(start, end, vias, 'commit');
  };

  const handleLongRouteLoadingDismiss = useCallback(() => {
    setShowLongRouteLoading(false);
    if (fastestData && safestData) {
      setRouteRevealed(true);
    }
  }, [fastestData, safestData]);

  const handleProfileCreated = async (profile) => {
    setShowWizard(false);
    await loadProfileList();
    setActiveProfileId(profile.id);
    setActiveProfile(profile);
  };

  const handleRefreshTfl = () => {
    setTflDisruptionStatus("Fetching...");
    fetch(`${API_BASE}/admin/update_tfl`, { method: "POST" })
      .then(r => r.json())
      .then(d => setTflDisruptionStatus(d.ok ? `${d.count} disruptions matched` : (d.message || "Error")))
      .catch(() => setTflDisruptionStatus("Connection error"));
  };

  const handleRefreshTomtom = () => {
    setTomtomDisruptionStatus("Fetching...");
    fetch(`${API_BASE}/admin/update_tomtom`, { method: "POST" })
      .then(r => r.json())
      .then(d => setTomtomDisruptionStatus(d.ok ? `${d.count} incidents matched` : (d.message || "Error")))
      .catch(() => setTomtomDisruptionStatus("Connection error"));
  };

  useEffect(() => {
    if (!lastRouteMeta?.lightingActive) {
      setOverlayVisibility((prev) => (prev.lit ? { ...prev, lit: false } : prev));
    }
  }, [lastRouteMeta?.lightingActive]);

  useEffect(() => {
    if (overlayVisibility.disruptions && routeRevealed && !tflDisruptionStatus) {
      fetch(`${API_BASE}/admin/tfl_status`)
        .then(r => r.json())
        .then(st => { if (st.edge_count !== undefined) setTflDisruptionStatus(`${st.edge_count} edges`); })
        .catch(() => {});
    }
  }, [overlayVisibility.disruptions, routeRevealed, tflDisruptionStatus]);

  useEffect(() => {
    if (overlayVisibility.disruptions && routeRevealed && !tomtomDisruptionStatus) {
      fetch(`${API_BASE}/admin/tomtom_status`)
        .then(r => r.json())
        .then(st => { if (st.edge_count !== undefined) setTomtomDisruptionStatus(`${st.edge_count} edges`); })
        .catch(() => {});
    }
  }, [overlayVisibility.disruptions, routeRevealed, tomtomDisruptionStatus]);

  const handleRefreshDisruptions = () => {
    handleRefreshTfl();
    handleRefreshTomtom();
  };

  const disruptionStatusLabel = [tflDisruptionStatus, tomtomDisruptionStatus].filter(Boolean).join(' · ');

  const disruptionActive = routeRevealed && overlayVisibility.disruptions;

  const applyMapPoint = useCallback((lat, lon) => {
    const mapLabel = 'Map location';
    if (!start) {
      setStartPoint(lat, lon, mapLabel);
      return;
    }
    const emptyViaIdx = vias.findIndex((v) => !v.coord);
    if (emptyViaIdx >= 0) {
      bumpRouteRequest();
      setVias((prev) => prev.map((v, i) => (
        i === emptyViaIdx ? { ...v, coord: [lat, lon], label: mapLabel } : v
      )));
      setRouteRevealed(false);
      clearRouteData();
      setStatus('Calculating route in background...');
      return;
    }
    if (!end) {
      setEndPoint(lat, lon, mapLabel);
      return;
    }
    bumpRouteRequest();
    setStartPoint(lat, lon, mapLabel);
    setEnd(null);
    setEndLabel('');
    setVias([]);
    clearRouteData();
    setRouteRevealed(false);
    setStatus('New Start.');
  }, [start, end, vias]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleMapClick = useCallback((e) => {
    if (inspectorData) {
      setInspectorData(null);
      setInspectorGeo(null);
      return;
    }
    if (routeRevealed && routeLegs?.length > 1) {
      const legIdx = pickInactiveLegIndex(e.target, e.point, routeLegs, activeLegIndex);
      if (legIdx != null) {
        setActiveLegIndex(legIdx);
        return;
      }
    }
    const lat = e.lngLat.lat;
    const lon = e.lngLat.lng;
    const pos = {
      x: e.originalEvent?.clientX ?? e.point?.x,
      y: e.originalEvent?.clientY ?? e.point?.y,
    };

    if (disruptionActive) {
      const checkTfl = fetch(`${API_BASE}/tfl_disruption_at?lat=${lat}&lon=${lon}&tolerance=0.00025`).then((r) => r.json());
      const checkTomtom = fetch(`${API_BASE}/tomtom_disruption_at?lat=${lat}&lon=${lon}&tolerance=0.00025`).then((r) => r.json());
      Promise.all([checkTfl, checkTomtom]).then(([tflData, tomtomData]) => {
        const tflHit = tflData?.disruptions?.length > 0;
        const tomtomHit = tomtomData?.disruptions?.length > 0;
        if (tflHit) setTflDisruptionDetail({ disruptions: tflData.disruptions, position: pos });
        else setTflDisruptionDetail(null);
        if (tomtomHit) setTomtomDisruptionDetail({ disruptions: tomtomData.disruptions, position: pos });
        else setTomtomDisruptionDetail(null);
        if (tflHit || tomtomHit) return;
        applyMapPoint(lat, lon);
      });
      return;
    }
    applyMapPoint(lat, lon);
  }, [inspectorData, disruptionActive, applyMapPoint, routeRevealed, routeLegs, activeLegIndex]);

  const handleMapContextMenu = useCallback((e) => {
    if (e.originalEvent?.preventDefault) e.originalEvent.preventDefault();
    setTflDisruptionDetail(null);
    setTomtomDisruptionDetail(null);
    const lat = e.lngLat.lat;
    const lon = e.lngLat.lng;
    fetch(`${API_BASE}/inspect?lat=${lat}&lon=${lon}`)
      .then((res) => res.json())
      .then((data) => {
        if (!data.error) {
          setInspectorData(data.tags);
          setInspectorGeo(data.geometry);
          setInspectorPos({
            x: e.originalEvent?.clientX ?? e.point?.x,
            y: e.originalEvent?.clientY ?? e.point?.y,
          });
        }
      });
  }, []);

  return (
    <div className="app-root" data-theme={theme.mode} style={{ height: "100vh", position: "relative", fontFamily: "Segoe UI, Arial, sans-serif" }}>

      <TopBar
        status={status}
        testMode={testMode}
        setTestMode={setTestMode}
        profiles={profiles}
        activeProfileId={activeProfileId}
        onSelectProfile={setActiveProfileId}
        onCreateProfile={() => setShowWizard(true)}
        onOpenAuth={() => setShowAuthModal(true)}
        onOpenSettings={() => setShowAccountSettings(true)}
      />

      {showLongRouteLoading && (
        <RouteLoadingBike
          key={longRouteLoadingKey}
          busy={isCalculating}
          themeMode={theme.mode}
          onDismiss={handleLongRouteLoadingDismiss}
        />
      )}

      {/* ROUTE POINTS (profile selection lives in the top-bar ProfileMenu) */}
      <div className="ui-panel" style={{
        position: "absolute", top: "60px", left: "20px", width: "300px", padding: "12px",
        zIndex: 1000,
      }}>
        <div className="ui-panel-title">Route points</div>
        <RoutePointsPanel
          theme={theme}
          start={start}
          end={end}
          startLabel={startLabel}
          endLabel={endLabel}
          vias={vias}
          onChangeWaypoints={handleChangeWaypoints}
          onAddVia={handleAddVia}
          onRemoveVia={handleRemoveVia}
          onSwapStartEnd={handleSwapStartEnd}
          santanderMode={santanderMode}
          santanderDisabled={departMode === 'depart_at'}
          departMode={departMode}
          onSantanderChange={(on) => {
            if (on && departMode === 'depart_at') return;
            // TODO(later): vias on Santander bike leg — for now mutual exclusion.
            if (on && vias.length > 0) {
              setVias([]);
            }
            bumpRouteRequest();
            setSantanderMode(on);
            resetHireState();
            setRouteRevealed(false);
            clearRouteData();
            if (on) {
              setStatus(start && end
                ? 'Ready — click Get Route to pick Santander stations'
                : 'Set start and end, then Get Route');
            } else if (start && end) {
              setStatus('Calculating route in background...');
            }
          }}
        />
        <button
          type="button"
          className="ui-btn primary"
          onClick={handleGetRoute}
          disabled={!start || !end || hireStep === 'routing' || vias.some((v) => !v.coord)}
        >
          {hireStep === 'routing'
            ? 'Working...'
            : (isCalculating && routeRevealed && !santanderMode)
              ? 'Calculating...'
              : 'Get Route'}
        </button>
        <DepartAtControl
          mode={departMode}
          departAtIso={departAtIso}
          onChange={({ mode, departAtIso: iso }) => {
            setDepartMode(mode);
            setDepartAtIso(iso);
            if (mode === 'depart_at' && santanderMode) {
              bumpRouteRequest();
              setSantanderMode(false);
              resetHireState();
              setRouteRevealed(false);
              clearRouteData();
              if (start && end) {
                setStatus('Calculating route in background...');
              }
            }
          }}
        />
        {(isFutureDepartAt(departAtIso) || (lastRouteMeta && lastRouteMeta.liveApplied === false)) && (
          <div className="depart-at-banner">
            Live traffic not applied for future departures.
          </div>
        )}
      </div>

      <SantanderGuidePill text={hireGuide} />
      <SantanderSoftBanner text={hireBanner} />
      <SantanderUnsuitableModal
        open={!!unsuitableModal}
        title={unsuitableModal?.title}
        message={unsuitableModal?.message}
        onCancel={() => setUnsuitableModal(null)}
        onProceed={() => {
          const st = unsuitableModal?.station;
          setUnsuitableModal(null);
          if (!st) return;
          if (hireStep === 'pickup') commitPickup(st);
          else if (hireStep === 'dropoff') commitDropoff(st);
        }}
      />

      {showWizard && (
        <PresetWizard
          themeMode={theme.mode}
          testMode={testMode}
          onClose={() => setShowWizard(false)}
          onCreated={handleProfileCreated}
        />
      )}

      {showAuthModal && (
        <AuthModal themeMode={theme.mode} onClose={() => setShowAuthModal(false)} />
      )}

      {passwordRecoveryPending && (
        <PasswordRecoveryModal themeMode={theme.mode} />
      )}

      {showAccountSettings && (
        <AccountSettingsModal
          themeMode={theme.mode}
          onClose={() => setShowAccountSettings(false)}
        />
      )}

      {inspectorData && inspectorPos && (
          <InspectorWindow data={inspectorData} position={inspectorPos}
            onClose={() => { setInspectorData(null); setInspectorGeo(null); }} theme={theme} />
      )}
      {tflDisruptionDetail && (
        <TflDisruptionDetailWindow disruptions={tflDisruptionDetail.disruptions}
          position={tflDisruptionDetail.position} onClose={() => setTflDisruptionDetail(null)} theme={theme} />
      )}
      {tomtomDisruptionDetail && (
        <TomtomDisruptionDetailWindow disruptions={tomtomDisruptionDetail.disruptions}
          position={tomtomDisruptionDetail.position} onClose={() => setTomtomDisruptionDetail(null)} theme={theme} />
      )}

      <CycleMap
        theme={theme}
        flyTarget={flyTarget}
        start={start}
        end={end}
        vias={vias}
        onClick={handleMapClick}
        onContextMenu={handleMapContextMenu}
        routeRevealed={routeRevealed}
        routeLegs={routeLegs}
        activeLegIndex={activeLegIndex}
        overlayVisibility={overlayVisibility}
        lightingActive={!!lastRouteMeta?.lightingActive}
        fastestPath={fastestData?.path}
        safestPath={safestData?.path}
        litSegments={litSegments}
        steepSegments={steepSegments}
        tflCyclewayChunks={tflCyclewayChunks}
        greenChunks={greenChunks}
        vehicularFreeChunks={vehicularFreeChunks}
        disruptionChunks={disruptionChunks}
        nodeHighlights={nodeHighlights}
        walkStartPath={walkStartPath}
        walkEndPath={walkEndPath}
        inspectorGeo={inspectorGeo}
      >
        {hireStep === 'dropoff' && pickupStation && (
          <SantanderStationsLayer
            stations={[pickupStation]}
            expandedId={null}
            showConfirm={false}
          />
        )}
        {(hireStep === 'pickup' || hireStep === 'dropoff') && hireStations.length > 0 && (
          <SantanderStationsLayer
            stations={hireStations}
            expandedId={expandedStationId}
            confirmLabel={hireStep === 'pickup' ? 'Start' : 'End'}
            showConfirm
            onExpand={handleStationExpand}
            onConfirm={handleStationConfirm}
          />
        )}
        {hireStep === 'done' && (pickupStation || dropoffStation) && (
          <SantanderStationsLayer
            stations={[pickupStation, dropoffStation].filter(Boolean)}
            expandedId={expandedStationId}
            showConfirm={false}
            onExpand={(st) => setExpandedStationId((prev) => (prev === st.id ? null : st.id))}
          />
        )}
      </CycleMap>

      {/* TEST MODE PANEL — level 1: Supabase bypass; level 2 (nested): manual weights */}
      {testMode && (
        <TestModePanel
          theme={theme}
          manualWeightsMode={manualWeightsMode}
          setManualWeightsMode={setManualWeightsMode}
          toggles={toggleState}
          setters={{
            setUseSafetyRouting, setUseLighting, setUseTflCycleway, setUseVehicularFree,
            setUseSpeedStress, setUseSignals, setUseBarriers, setUseJunctionDanger,
            setUseTflLive, setUseTomtomLive, setUseRoadBike, setUseHillRouting,
            setUseCalming, setUseGreen,
          }}
          onRefreshTfl={handleRefreshTfl}
          onRefreshTomtom={handleRefreshTomtom}
          tflDisruptionStatus={tflDisruptionStatus}
          tomtomDisruptionStatus={tomtomDisruptionStatus}
        />
      )}

      <RouteOverlayPicker
        theme={theme}
        visibility={overlayVisibility}
        setVisibility={setOverlayVisibility}
        routeRevealed={routeRevealed}
        lightingActive={!!lastRouteMeta?.lightingActive}
        onRefreshDisruptions={handleRefreshDisruptions}
        disruptionStatus={disruptionStatusLabel}
        apiBase={API_BASE}
      />

      {/* STATS PANEL */}
      {routeRevealed && fastestData && safestData && (() => {
        const multiLeg = Array.isArray(routeLegs) && routeLegs.length > 1;
        const leg = multiLeg ? routeLegs[activeLegIndex] : null;
        const displayFastest = leg?.fastest || fastestData;
        const displaySafest = leg?.safest || safestData;
        const pointNames = [
          'Start',
          ...vias.map((_, i) => `Via ${i + 1}`),
          'End',
        ];
        const legLabel = multiLeg
          ? `Leg ${activeLegIndex + 1}/${routeLegs.length} · ${pointNames[activeLegIndex]} → ${pointNames[activeLegIndex + 1]}`
          : '';
        return (
      <div className="ui-panel ui-stats-panel" style={{ position: "absolute", bottom: "30px", left: "20px", zIndex: 1000 }}>
          <h4 className="ui-stats-title">Route Analysis</h4>
          {lastRouteMeta?.bikeType && (
            <div className="ui-stats-meta">
              {lastRouteMeta.bikeType}{lastRouteMeta.preset ? ` · ${lastRouteMeta.preset} preset` : ''}
              {lastRouteMeta.lightGatedOff ? ' · lighting off (daylight)' : ''}
              {lastRouteMeta.clamps?.length > 0 && (
                <div className="ui-stats-meta-clamps">
                  {lastRouteMeta.clamps.length} conflict clamp{lastRouteMeta.clamps.length > 1 ? 's' : ''} applied
                  ({lastRouteMeta.clamps.map((c) => c.clamped_weight.replace('_weight', '')).join(', ')})
                </div>
              )}
            </div>
          )}
          <LegAnalysisPager
            legCount={multiLeg ? routeLegs.length : 1}
            activeLegIndex={activeLegIndex}
            onChangeLeg={setActiveLegIndex}
            legLabel={legLabel}
          >
          <div className="ui-stats-layout">
            <div className="ui-stats-hero">
              <RouteHeroCard
                label="Time"
                fastest={displayFastest.stats.duration_min}
                optimized={displaySafest.stats.duration_min}
                unit="min"
                theme={theme}
                walkValue={!multiLeg && lastRouteMeta?.santander ? hireWalkStats?.duration_min : null}
                cycleMode={!multiLeg && !!lastRouteMeta?.santander}
              />
              <RouteHeroCard
                label="Distance"
                fastest={(displayFastest.stats.length_m / 1000).toFixed(1)}
                optimized={(displaySafest.stats.length_m / 1000).toFixed(1)}
                unit="km"
                theme={theme}
                walkValue={!multiLeg && lastRouteMeta?.santander && hireWalkStats?.distance_m != null
                  ? hireWalkStats.distance_m / 1000
                  : null}
                cycleMode={!multiLeg && !!lastRouteMeta?.santander}
              />
            </div>
            <div className="ui-stats-detail">
              <div className="ui-stats-detail-head">
                <span>METRIC</span>
                <span>VALUE</span>
                <span>DELTA</span>
              </div>
              {METRIC_ROWS.filter((row) => (
                row.key !== 'illumination_pct' || lastRouteMeta?.lightingActive
              )).map((row) => (
                <CondensedStatRow
                  key={row.key}
                  label={row.label}
                  statKey={row.key}
                  statsFastest={displayFastest.stats}
                  statsOptimized={displaySafest.stats}
                  unit={row.unit}
                  invertDiff={row.invertDiff}
                  integer={row.integer}
                  theme={theme}
                />
              ))}
            </div>
          </div>
          </LegAnalysisPager>
      </div>
        );
      })()}
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  );
}

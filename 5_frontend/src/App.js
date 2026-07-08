/**
 * Main app: profile-driven cycling route planner (Tuned Cycling).
 * Backend: 4_backend_engine/app.py (port 5000).
 * When changing features or architecture, update 0_documentation/APP_MAIN.md
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Polyline, CircleMarker, Popup, useMapEvents, useMap, ZoomControl } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import './ui.css';

import LocationSearchInput from './LocationSearchInput';
import MapFlyTo from './MapFlyTo';
import RouteOverlayPicker from './RouteOverlayPicker';
import PresetWizard from './wizard/PresetWizard';
import { emptyOverlayVisibility, defaultOverlayVisibility } from './routeOverlayCatalog';
import { getMapboxToken } from './mapboxGeocoding';
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

let DefaultIcon = L.icon({
    iconUrl: icon, shadowUrl: iconShadow,
    iconSize: [25, 41], iconAnchor: [12, 41]
});
L.Marker.prototype.options.icon = DefaultIcon;

const API_BASE = 'http://127.0.0.1:5000';
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

const toggleStyle = {
    container: { display: "flex", justifyContent: "space-between", marginBottom: "12px", cursor: "pointer" },
    switch: { position: "relative", width: "36px", height: "18px", marginLeft: "10px" },
    slider: (isOn, activeColor, bgColor) => ({
        position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: isOn ? activeColor : bgColor, transition: ".3s", borderRadius: "18px"
    }),
    knob: (isOn) => ({
        position: "absolute", height: "14px", width: "14px", left: "2px", bottom: "2px",
        backgroundColor: "white", transition: ".3s", borderRadius: "50%",
        transform: isOn ? "translateX(18px)" : "translateX(0)"
    })
};

const Toggle = ({ label, isOn, setIsOn, activeColor, theme, compact = false }) => (
    <div style={{ ...toggleStyle.container, marginBottom: compact ? 0 : "12px" }} onClick={() => setIsOn(!isOn)}>
        <span style={{ fontSize: compact ? "12px" : "13px", fontWeight: "bold", color: theme.textMain }}>{label}</span>
        <div style={toggleStyle.switch}>
            <div style={toggleStyle.slider(isOn, activeColor, theme.toggleInactive)}>
                <div style={toggleStyle.knob(isOn)}></div>
            </div>
        </div>
    </div>
);

const HeaderBarToggle = ({ label, isOn, setIsOn }) => (
    <div
      onClick={() => setIsOn(!isOn)}
      style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', userSelect: 'none' }}
    >
      <span style={{ fontSize: '12px', color: isOn ? '#ce93d8' : '#888', fontWeight: 600 }}>{label}</span>
      <div style={{ position: 'relative', width: '34px', height: '18px' }}>
        <div style={{
          position: 'absolute', inset: 0, borderRadius: '18px', transition: '.25s',
          backgroundColor: isOn ? '#7b1fa2' : '#3a3a3a',
        }} />
        <div style={{
          position: 'absolute', height: '14px', width: '14px', left: '2px', bottom: '2px',
          backgroundColor: 'white', borderRadius: '50%', transition: '.25s',
          transform: isOn ? 'translateX(16px)' : 'translateX(0)',
        }} />
      </div>
    </div>
);

const RouteHeroCard = ({ label, fastest, optimized, unit, theme }) => {
  const f = parseFloat(fastest);
  const o = parseFloat(optimized);
  const diff = o - f;
  const fmt = (n) => n.toFixed(1);
  const displayDiff = (diff > 0 ? '+' : '') + fmt(diff);
  const diffColor = diff > 0 ? '#f44336' : diff < 0 ? '#4CAF50' : theme.textSub;
  return (
    <div className="ui-hero-card">
      <div className="ui-hero-card__label">{label}</div>
      <div className="ui-hero-card__main">
        <span className="ui-hero-card__value">{fmt(o)}</span>
        <span className="ui-hero-card__unit">{unit}</span>
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

function NodeHighlightMarkers({ nodeHighlights, showBarriers, showSignals, showJunctionDanger, showCalming, theme }) {
  const map = useMap();
  const [zoom, setZoom] = useState(() => map.getZoom());
  useEffect(() => {
    const onZoom = () => setZoom(map.getZoom());
    map.on('zoomend', onZoom);
    return () => map.off('zoomend', onZoom);
  }, [map]);
  const radiusScale = Math.pow(2, (zoom - 12) / 4);
  const getRadius = (isJunctionDanger) => Math.max(1, Math.round((isJunctionDanger ? 1.5 : 1) * radiusScale));

  const filtered = nodeHighlights.filter(h =>
    (h.type === 'barrier' && showBarriers) ||
    (h.type === 'signal' && showSignals) ||
    ((h.type === 'junction' || h.type === 'junction_danger' || h.type === 'give_way' || h.type === 'stop_sign') && showJunctionDanger) ||
    (h.type === 'calming' && showCalming)
  );

  const getFillColor = (type) => {
    if (type === 'barrier') return theme.nodeBarrier;
    if (type === 'signal') return theme.nodeSignal;
    if (type === 'calming') return theme.nodeCalming;
    return theme.nodeJunction;
  };

  return (
    <>
      {filtered.map((h, i) => (
        <CircleMarker
          key={`node-${i}-${h.lat}-${h.lon}`}
          center={[h.lat, h.lon]}
          radius={getRadius(h.type === 'junction_danger')}
          pathOptions={{ fillColor: getFillColor(h.type), color: '#333', weight: 1.5, fillOpacity: 0.9 }}
        >
          <Popup>
            <div style={{ fontSize: '12px', minWidth: '120px' }}>
              <strong style={{ textTransform: 'capitalize' }}>{h.type.replace('_', ' ')}</strong>
              {Object.entries(h.details || {}).map(([k, v]) => (
                <div key={k}><span style={{ color: '#666' }}>{k}:</span> {String(v)}</div>
              ))}
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </>
  );
}

// --- MAIN APP ---

function App() {
  const [start, setStart] = useState(null);
  const [end, setEnd] = useState(null);
  const [startLabel, setStartLabel] = useState('');
  const [endLabel, setEndLabel] = useState('');
  const [flyTarget, setFlyTarget] = useState(null);
  const [status, setStatus] = useState("Loading profiles...");

  const [profiles, setProfiles] = useState([]);
  const [activeProfileId, setActiveProfileId] = useState(
    () => localStorage.getItem('activeProfileId') || 'preset_safe'
  );
  const [activeProfile, setActiveProfile] = useState(null);
  const [testMode, setTestMode] = useState(false);
  const [showWizard, setShowWizard] = useState(false);
  const [routeRevealed, setRouteRevealed] = useState(false);
  const [isCalculating, setIsCalculating] = useState(false);
  const [lastRouteMeta, setLastRouteMeta] = useState(null);
  const routeRevealedRef = useRef(false);
  useEffect(() => { routeRevealedRef.current = routeRevealed; }, [routeRevealed]);

  useEffect(() => {
    if (!getMapboxToken()) {
      console.warn('REACT_APP_MAPBOX_API_KEY is not set — location search disabled.');
    }
  }, []);

  const [fastestData, setFastestData] = useState(null);
  const [safestData, setSafestData] = useState(null);
  const [litSegments, setLitSegments] = useState([]);
  const [steepSegments, setSteepSegments] = useState([]);
  const [tflCyclewayChunks, setTflCyclewayChunks] = useState([]);
  const [tflQuietwayChunks, setTflQuietwayChunks] = useState([]);
  const [greenChunks, setGreenChunks] = useState([]);
  const [narrowChunks, setNarrowChunks] = useState([]);
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

  const theme = useLighting ? {
      mode: 'dark', bg: '#1a1a1a',
      textMain: '#e0e0e0', textSub: '#a0a0a0', border: '#333', toggleInactive: '#444',
      routeGrey: '#ffffff', routeOptimized: '#40E0D0', litColor: '#FFFF00', steepColor: '#00FF00',
      tflCyclewayColor: '#2196F3', tflQuietwayColor: '#8BC34A', greenColor: '#009688', narrowColor: '#7B1FA2',
      nodeBarrier: '#5D4037', nodeSignal: '#F57C00', nodeJunction: '#795548', nodeCalming: '#00838F',
      disruptionColor: '#FF0000',
      tileFilter: 'invert(100%) hue-rotate(180deg) brightness(95%) contrast(90%)'
  } : {
      mode: 'light', bg: 'white',
      textMain: '#333', textSub: '#666', border: '#f0f0f0', toggleInactive: '#ccc',
      routeGrey: '#555', routeOptimized: '#d32f2f', litColor: '#FFD700', steepColor: '#00cc00',
      tflCyclewayColor: '#1976D2', tflQuietwayColor: '#388E3C', greenColor: '#00796B', narrowColor: '#7B1FA2',
      nodeBarrier: '#5D4037', nodeSignal: '#F57C00', nodeJunction: '#795548', nodeCalming: '#00838F',
      disruptionColor: '#FFD700',
      tileFilter: 'none'
  };

  const toggleState = {
    useSafetyRouting, useLighting, useRoadBike, useHillRouting,
    useTflCycleway, useGreen, useSpeedStress, useVehicularFree,
    useBarriers, useCalming, useJunctionDanger, useSignals, useTflLive, useTomtomLive,
  };

  const effectiveWeights = testMode
    ? togglesToWeights(toggleState)
    : (activeProfile?.weights || emptyWeights());

  const loadProfileList = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/profiles`);
      const data = await res.json();
      setProfiles(data.profiles || []);
    } catch {
      setStatus('Could not load profiles');
    }
  }, []);

  const loadActiveProfile = useCallback(async (profileId) => {
    try {
      const res = await fetch(`${API_BASE}/profiles/${profileId}`);
      if (!res.ok) return;
      const data = await res.json();
      setActiveProfile(data);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadProfileList(); }, [loadProfileList]);

  useEffect(() => {
    if (activeProfileId) {
      localStorage.setItem('activeProfileId', activeProfileId);
      loadActiveProfile(activeProfileId);
    }
  }, [activeProfileId, loadActiveProfile]);

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
    setTflQuietwayChunks([]);
    setGreenChunks([]);
    setNarrowChunks([]);
    setDisruptionChunks([]);
    setNodeHighlights([]);
    setLastRouteMeta(null);
  }, []);

  const setStartPoint = useCallback((lat, lon, label) => {
    setStart([lat, lon]);
    setStartLabel(label ?? `${lat.toFixed(4)}, ${lon.toFixed(4)}`);
    setRouteRevealed(false);
    setStatus(end ? 'Calculating route in background...' : 'Set Destination.');
  }, [end]);

  const setEndPoint = useCallback((lat, lon, label) => {
    setEnd([lat, lon]);
    setEndLabel(label ?? `${lat.toFixed(4)}, ${lon.toFixed(4)}`);
    setRouteRevealed(false);
    setStatus('Calculating route in background...');
  }, []);

  const handleStartSearchSelect = useCallback(({ lat, lon, label }) => {
    setStartPoint(lat, lon, label);
    setFlyTarget([lat, lon]);
  }, [setStartPoint]);

  const handleEndSearchSelect = useCallback(({ lat, lon, label }) => {
    setEndPoint(lat, lon, label);
    setFlyTarget([lat, lon]);
  }, [setEndPoint]);

  const minWeightPreview = computeMinWeightPerM(effectiveWeights);

  const fetchRoutes = useCallback(async (s, e) => {
    const startCoord = s || start;
    const endCoord = e || end;
    if (!startCoord || !endCoord) return;
    setIsCalculating(true);
    if (routeRevealedRef.current) {
      setStatus(`Calculating... | min weight/m: ${minWeightPreview.toFixed(3)}`);
    } else {
      setStatus('Calculating route in background...');
    }
    const params = new URLSearchParams({
      start_lat: startCoord[0], start_lon: startCoord[1],
      end_lat: endCoord[0], end_lon: endCoord[1],
    });
    if (testMode) {
      const w = togglesToWeights(toggleState);
      ALL_WEIGHT_KEYS.forEach((k) => params.set(k, w[k]));
    } else if (activeProfileId) {
      params.set('profile_id', activeProfileId);
    }
    try {
      const response = await fetch(`${API_BASE}/route?${params}`);
      const data = await response.json();
      if (data.status === "success") {
        setFastestData(data.fastest);
        setSafestData(data.safest);
        setLitSegments(data.safest.lit_chunks || []);
        setSteepSegments(data.safest.steep_chunks || []);
        setTflCyclewayChunks(data.safest.tfl_cycleway_chunks || []);
        setTflQuietwayChunks(data.safest.tfl_quietway_chunks || []);
        setGreenChunks(data.safest.green_chunks || []);
        setNarrowChunks(data.safest.narrow_chunks || []);
        setDisruptionChunks(data.safest.disruption_chunks || []);
        setNodeHighlights(data.safest.node_highlights || []);
        const meta = data.meta || {};
        const minWeight = meta.cost_per_m_lower_bound ?? minWeightPreview;
        const timingMs = meta.timing_ms?.total ?? 0;
        const profileName = testMode ? 'Test Mode' : (activeProfile?.name || '');
        const metaBundle = {
          minWeight, timingMs, profileName,
          bikeType: meta.bike_type, preset: meta.preset,
          clamps: meta.translation_clamps || [],
          lightGatedOff: !!meta.light_gated_off,
          lightingActive: (meta.weights?.light_weight ?? 0) > 0,
        };
        setLastRouteMeta(metaBundle);
        setStatus(routeRevealedRef.current
          ? formatRouteStatus(minWeight, timingMs, profileName)
          : 'Route ready — click Get Route');
      } else {
        setStatus("Error: " + data.error);
      }
    } catch {
      setStatus("Backend Error.");
    } finally {
      setIsCalculating(false);
    }
  }, [
    start, end, testMode, activeProfileId, activeProfile, minWeightPreview,
    useSafetyRouting, useLighting, useRoadBike, useHillRouting,
    useTflCycleway, useGreen, useSpeedStress, useVehicularFree,
    useBarriers, useCalming, useJunctionDanger, useSignals, useTflLive, useTomtomLive,
  ]);

  useEffect(() => {
    if (!start || !end) return;
    setRouteRevealed(false);
    fetchRoutes(start, end);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    start, end, activeProfileId, testMode,
    useSafetyRouting, useLighting, useRoadBike, useHillRouting,
    useTflCycleway, useGreen, useSpeedStress, useVehicularFree,
    useBarriers, useCalming, useJunctionDanger, useSignals, useTflLive, useTomtomLive,
  ]);

  useEffect(() => {
    if (routeRevealed && !isCalculating && lastRouteMeta) {
      setStatus(formatRouteStatus(lastRouteMeta.minWeight, lastRouteMeta.timingMs, lastRouteMeta.profileName));
    }
  }, [routeRevealed, isCalculating, lastRouteMeta]);

  const handleGetRoute = () => {
    if (!start || !end) return;
    setOverlayVisibility(defaultOverlayVisibility());
    setRouteRevealed(true);
    if (isCalculating) {
      setStatus(`Calculating... | min weight/m: ${minWeightPreview.toFixed(3)}`);
      return;
    }
    if (lastRouteMeta && fastestData && safestData) {
      setStatus(formatRouteStatus(lastRouteMeta.minWeight, lastRouteMeta.timingMs, lastRouteMeta.profileName));
    } else {
      fetchRoutes(start, end);
    }
  };

  const handleProfileChange = (e) => setActiveProfileId(e.target.value);

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

  function MapEvents() {
    const disruptionActive = routeRevealed && overlayVisibility.disruptions;

    const doStartEndClick = (e) => {
      const lat = e.latlng.lat;
      const lon = e.latlng.lng;
      const mapLabel = 'Map location';
      if (!start) {
        setStartPoint(lat, lon, mapLabel);
      } else if (!end) {
        setEndPoint(lat, lon, mapLabel);
      } else {
        setStartPoint(lat, lon, mapLabel);
        setEnd(null);
        setEndLabel('');
        clearRouteData();
        setRouteRevealed(false);
        setStatus('New Start.');
      }
    };

    useMapEvents({
      click(e) {
        if (inspectorData) {
          setInspectorData(null);
          setInspectorGeo(null);
          return;
        }
        const lat = e.latlng.lat, lon = e.latlng.lng;
        const pos = { x: e.originalEvent.clientX, y: e.originalEvent.clientY };

        if (disruptionActive) {
          const checkTfl = fetch(`${API_BASE}/tfl_disruption_at?lat=${lat}&lon=${lon}&tolerance=0.00025`).then(r => r.json());
          const checkTomtom = fetch(`${API_BASE}/tomtom_disruption_at?lat=${lat}&lon=${lon}&tolerance=0.00025`).then(r => r.json());
          Promise.all([checkTfl, checkTomtom]).then(([tflData, tomtomData]) => {
            const tflHit = tflData?.disruptions?.length > 0;
            const tomtomHit = tomtomData?.disruptions?.length > 0;
            if (tflHit) setTflDisruptionDetail({ disruptions: tflData.disruptions, position: pos });
            else setTflDisruptionDetail(null);
            if (tomtomHit) setTomtomDisruptionDetail({ disruptions: tomtomData.disruptions, position: pos });
            else setTomtomDisruptionDetail(null);
            if (tflHit || tomtomHit) return;
            doStartEndClick(e);
          });
          return;
        }
        doStartEndClick(e);
      },
      contextmenu(e) {
        setTflDisruptionDetail(null);
        setTomtomDisruptionDetail(null);
        fetch(`${API_BASE}/inspect?lat=${e.latlng.lat}&lon=${e.latlng.lng}`)
            .then(res => res.json())
            .then(data => {
                if (!data.error) {
                    setInspectorData(data.tags);
                    setInspectorGeo(data.geometry);
                    setInspectorPos({ x: e.originalEvent.clientX, y: e.originalEvent.clientY });
                }
            });
      }
    });
    return null;
  }

  return (
    <div className="app-root" data-theme={theme.mode} style={{ height: "100vh", position: "relative", fontFamily: "Segoe UI, Arial, sans-serif" }}>
      <style>{`.leaflet-tile { filter: ${theme.tileFilter} !important; }`}</style>

      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: "50px",
        background: "#111", color: "white", display: "flex", alignItems: "center",
        justifyContent: "space-between", padding: "0 20px", zIndex: 1000,
        boxShadow: "0 2px 10px rgba(0,0,0,0.5)",
      }}>
        <div style={{ display: "flex", alignItems: "center", minWidth: 0, flex: 1 }}>
          <span style={{ fontWeight: "bold", flexShrink: 0 }}>Tuned Cycling</span>
          <span style={{ marginLeft: "15px", fontSize: "14px", color: "#aaa", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            | {status}
          </span>
        </div>
        <HeaderBarToggle label="Test Mode" isOn={testMode} setIsOn={setTestMode} />
      </div>

      {/* PROFILE SELECTOR */}
      <div className="ui-panel" style={{
        position: "absolute", top: "60px", left: "20px", width: "260px", padding: "12px",
        zIndex: 1000,
      }}>
        <div className="ui-panel-title">Active Profile</div>
        <select
          className="ui-select"
          value={activeProfileId}
          onChange={handleProfileChange}
          style={{ marginBottom: "10px" }}
        >
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <div style={{ fontSize: "10px", fontWeight: "bold", color: theme.textSub, textTransform: "uppercase", marginBottom: "6px", borderTop: `1px solid ${theme.border}`, paddingTop: "8px" }}>
          Route points
        </div>
        <LocationSearchInput
          label="Start"
          value={startLabel}
          placeholder="Search start location"
          theme={theme}
          onSelect={handleStartSearchSelect}
        />
        <LocationSearchInput
          label="End"
          value={endLabel}
          placeholder="Search destination"
          theme={theme}
          onSelect={handleEndSearchSelect}
        />
        <button
          type="button"
          className="ui-btn"
          onClick={() => setShowWizard(true)}
          style={{ marginBottom: "8px" }}
        >
          New Profile Wizard
        </button>
        <button
          type="button"
          className="ui-btn primary"
          onClick={handleGetRoute}
          disabled={!start || !end}
        >
          {isCalculating && routeRevealed ? 'Calculating...' : 'Get Route'}
        </button>
      </div>

      {showWizard && (
        <PresetWizard
          apiBase={API_BASE}
          themeMode={theme.mode}
          onClose={() => setShowWizard(false)}
          onCreated={handleProfileCreated}
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

      <MapContainer center={[51.505, -0.09]} zoom={13} zoomControl={false} style={{ height: "100%", width: "100%", background: "#111" }}>
        <ZoomControl position="bottomright" />
        <MapFlyTo target={flyTarget} />
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; OpenStreetMap' />
        <MapEvents />
        {start && <Marker position={start} />}
        {end && <Marker position={end} />}
        {inspectorGeo && <Polyline positions={inspectorGeo} color="red" weight={6} opacity={0.8} />}
        {routeRevealed && fastestData && <Polyline positions={fastestData.path} color={theme.routeGrey} weight={6} opacity={0.4} />}
        {routeRevealed && safestData && <Polyline positions={safestData.path} color={theme.routeOptimized} weight={5} opacity={1.0} />}
        {routeRevealed && overlayVisibility.lit && lastRouteMeta?.lightingActive && litSegments.map((s, i) => <Polyline key={`lit-${i}`} positions={s} color={theme.litColor} weight={4} opacity={1.0} />)}
        {routeRevealed && overlayVisibility.steep && !overlayVisibility.lit && steepSegments.map((s, i) => <Polyline key={`steep-${i}`} positions={s} color={theme.steepColor} weight={5} opacity={1.0} />)}
        {routeRevealed && overlayVisibility.tflCycleway && tflCyclewayChunks.map((s, i) => <Polyline key={`tfl-c-${i}`} positions={s} color={theme.tflCyclewayColor} weight={4} opacity={0.9} />)}
        {routeRevealed && overlayVisibility.tflQuietway && tflQuietwayChunks.map((s, i) => <Polyline key={`tfl-q-${i}`} positions={s} color={theme.tflQuietwayColor} weight={4} opacity={0.9} />)}
        {routeRevealed && overlayVisibility.green && greenChunks.map((s, i) => <Polyline key={`green-${i}`} positions={s} color={theme.greenColor} weight={4} opacity={0.9} />)}
        {routeRevealed && overlayVisibility.narrow && narrowChunks.map((s, i) => <Polyline key={`narrow-${i}`} positions={s} color={theme.narrowColor} weight={4} opacity={0.9} />)}
        {routeRevealed && overlayVisibility.disruptions && disruptionChunks.map((s, i) => <Polyline key={`dis-${i}`} positions={s} color={theme.disruptionColor} weight={5} opacity={0.9} />)}
        {routeRevealed && (overlayVisibility.barriers || overlayVisibility.signals || overlayVisibility.junctionDanger || overlayVisibility.calming) && (
          <NodeHighlightMarkers
            nodeHighlights={nodeHighlights}
            showBarriers={overlayVisibility.barriers}
            showSignals={overlayVisibility.signals}
            showJunctionDanger={overlayVisibility.junctionDanger}
            showCalming={overlayVisibility.calming}
            theme={theme}
          />
        )}
      </MapContainer>

      {/* TEST MODE PANEL (routing overrides — separate from route overlay picker) */}
      {testMode && (
      <div className="ui-panel" style={{ position: "absolute", bottom: "200px", right: "20px", width: "240px", maxHeight: "45vh", overflowY: "auto", padding: "15px", zIndex: 1000 }}>
          <h4 style={{ margin: "0 0 4px 0", color: theme.textMain }}>Test Mode</h4>
          <p style={{ fontSize: "10px", color: theme.textSub, margin: "0 0 8px 0", borderBottom: `1px solid ${theme.border}`, paddingBottom: "6px" }}>Overrides active profile</p>
          <div style={{ fontSize: "10px", fontWeight: "bold", color: theme.textSub, marginBottom: "6px", textTransform: "uppercase" }}>Safety</div>
          <Toggle label="Avoid Accidents" isOn={useSafetyRouting} setIsOn={setUseSafetyRouting} activeColor={theme.routeOptimized} theme={theme} />
          <Toggle label="Night Mode" isOn={useLighting} setIsOn={setUseLighting} activeColor="#1976D2" theme={theme} />
          <Toggle label="TfL network (incl. quietways)" isOn={useTflCycleway} setIsOn={setUseTflCycleway} activeColor="#1976D2" theme={theme} />
          <Toggle label="Car-free corridors" isOn={useVehicularFree} setIsOn={setUseVehicularFree} activeColor="#7B1FA2" theme={theme} />
          <Toggle label="Speed stress" isOn={useSpeedStress} setIsOn={setUseSpeedStress} activeColor="#E65100" theme={theme} />
          <Toggle label="Traffic signals" isOn={useSignals} setIsOn={setUseSignals} activeColor="#F57C00" theme={theme} />
          <Toggle label="Barriers" isOn={useBarriers} setIsOn={setUseBarriers} activeColor="#5D4037" theme={theme} />
          <Toggle label="Junction danger" isOn={useJunctionDanger} setIsOn={setUseJunctionDanger} activeColor="#795548" theme={theme} />
          <Toggle label="Live TfL Disruptions" isOn={useTflLive} setIsOn={setUseTflLive} activeColor={theme.disruptionColor} theme={theme} />
          {useTflLive && (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px", marginLeft: "12px" }}>
              <button type="button" onClick={handleRefreshTfl} style={{ padding: "4px 10px", fontSize: "11px", background: theme.toggleInactive, border: `1px solid ${theme.border}`, borderRadius: "4px", cursor: "pointer", color: theme.textMain }}>Refresh</button>
              <span style={{ fontSize: "10px", color: theme.textSub }}>{tflDisruptionStatus || "Not loaded"}</span>
            </div>
          )}
          <Toggle label="Live TomTom Disruptions" isOn={useTomtomLive} setIsOn={setUseTomtomLive} activeColor={theme.disruptionColor} theme={theme} />
          {useTomtomLive && (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px", marginLeft: "12px" }}>
              <button type="button" onClick={handleRefreshTomtom} style={{ padding: "4px 10px", fontSize: "11px", background: theme.toggleInactive, border: `1px solid ${theme.border}`, borderRadius: "4px", cursor: "pointer", color: theme.textMain }}>Refresh</button>
              <span style={{ fontSize: "10px", color: theme.textSub }}>{tomtomDisruptionStatus || "Not loaded"}</span>
            </div>
          )}
          <div style={{ fontSize: "10px", fontWeight: "bold", color: theme.textSub, marginTop: "8px", marginBottom: "6px", textTransform: "uppercase" }}>Comfort</div>
          <Toggle label="Road Bike (Smooth)" isOn={useRoadBike} setIsOn={setUseRoadBike} activeColor="#4CAF50" theme={theme} />
          <Toggle label="Flat Route" isOn={useHillRouting} setIsOn={setUseHillRouting} activeColor="#FFA500" theme={theme} />
          <Toggle label="Traffic calming" isOn={useCalming} setIsOn={setUseCalming} activeColor="#00838F" theme={theme} />
          <div style={{ fontSize: "10px", fontWeight: "bold", color: theme.textSub, marginTop: "8px", marginBottom: "6px", textTransform: "uppercase" }}>Scenery</div>
          <Toggle label="Green / scenic" isOn={useGreen} setIsOn={setUseGreen} activeColor="#00796B" theme={theme} />
      </div>
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
      {routeRevealed && fastestData && safestData && (
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
          <div className="ui-stats-layout">
            <div className="ui-stats-hero">
              <RouteHeroCard label="Time" fastest={fastestData.stats.duration_min} optimized={safestData.stats.duration_min} unit="min" theme={theme} />
              <RouteHeroCard label="Distance" fastest={(fastestData.stats.length_m / 1000).toFixed(1)} optimized={(safestData.stats.length_m / 1000).toFixed(1)} unit="km" theme={theme} />
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
                  statsFastest={fastestData.stats}
                  statsOptimized={safestData.stats}
                  unit={row.unit}
                  invertDiff={row.invertDiff}
                  integer={row.integer}
                  theme={theme}
                />
              ))}
            </div>
          </div>
      </div>
      )}
    </div>
  );
}

export default App;

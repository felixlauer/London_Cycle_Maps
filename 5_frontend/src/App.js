/**
 * Main app: profile-driven cycling route planner (Tuned Cycling).
 * Backend: 4_backend_engine/app.py (port 5000).
 * When changing features or architecture, update 0_documentation/APP_MAIN.md
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Polyline, CircleMarker, Popup, useMapEvents, useMap, ZoomControl } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

import LocationSearchInput from './LocationSearchInput';
import MapFlyTo from './MapFlyTo';
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

const WEIGHT_FIELD_GROUPS = [
  {
    title: 'Safety',
    fields: [
      { key: 'risk_weight', label: 'Avoid Accidents' },
      { key: 'light_weight', label: 'Lit roads' },
      { key: 'tfl_cycleway_weight', label: 'TfL Cycleways' },
      { key: 'width_weight', label: 'Narrow facility' },
      { key: 'speed_weight', label: 'Speed stress' },
      { key: 'signal_weight', label: 'Traffic signals' },
      { key: 'barrier_weight', label: 'Barriers' },
      { key: 'junction_weight', label: 'Junction danger' },
      { key: 'tfl_live_weight', label: 'Live disruptions' },
    ],
  },
  {
    title: 'Comfort',
    fields: [
      { key: 'surface_weight', label: 'Road Bike (Smooth)' },
      { key: 'hill_weight', label: 'Flat Route' },
      { key: 'calming_weight', label: 'Traffic calming' },
    ],
  },
  {
    title: 'Scenery',
    fields: [
      { key: 'tfl_quietway_weight', label: 'TfL Quietways' },
      { key: 'green_weight', label: 'Green / scenic' },
    ],
  },
];

const ALL_WEIGHT_KEYS = WEIGHT_FIELD_GROUPS.flatMap((g) => g.fields.map((f) => f.key));

const METRIC_ROWS = [
  { label: 'Accidents', key: 'accidents', unit: '', invertDiff: false, integer: true },
  { label: 'Lit', key: 'illumination_pct', unit: '%', invertDiff: true },
  { label: 'Rough Surf.', key: 'rough_pct', unit: '%', invertDiff: false },
  { label: 'Elevation', key: 'elevation_gain', unit: 'm', invertDiff: false, integer: true },
  { label: 'Steep Seg.', key: 'steep_count', unit: '', invertDiff: false, integer: true },
  { label: 'TfL Cycleway', key: 'tfl_cycleway_pct', unit: '%', invertDiff: true },
  { label: 'TfL Quietway', key: 'tfl_quietway_pct', unit: '%', invertDiff: true },
  { label: 'Speed stress', key: 'speed_stress_pct', unit: '%', invertDiff: false },
  { label: 'Narrow', key: 'narrow_km', unit: 'km', invertDiff: false },
  { label: 'Green', key: 'green_km', unit: 'km', invertDiff: true },
  { label: 'Barriers', key: 'barrier_count', unit: '', invertDiff: false, integer: true },
  { label: 'Calming', key: 'calming_count', unit: '', invertDiff: false, integer: true },
  { label: 'Signals', key: 'signal_count', unit: '', invertDiff: false, integer: true },
  { label: 'Junctions', key: 'junction_count', unit: '', invertDiff: false, integer: true },
  { label: 'Disruptions', key: 'disruption_count', unit: '', invertDiff: false, integer: true },
];

const clampWeight = (value) => {
  const n = parseFloat(value);
  if (Number.isNaN(n)) return 0;
  return Math.min(1, Math.max(0, n));
};

const emptyWeights = () => Object.fromEntries(ALL_WEIGHT_KEYS.map((k) => [k, 0]));

const togglesToWeights = (t) => ({
  risk_weight: t.useSafetyRouting ? 1 : 0,
  light_weight: t.useLighting ? 1 : 0,
  surface_weight: t.useRoadBike ? 1 : 0,
  hill_weight: t.useHillRouting ? 1 : 0,
  tfl_cycleway_weight: t.useTflCycleway ? 1 : 0,
  tfl_quietway_weight: t.useTflQuietway ? 1 : 0,
  speed_weight: t.useSpeedStress ? 1 : 0,
  width_weight: t.useWidth ? 1 : 0,
  green_weight: t.useGreen ? 1 : 0,
  barrier_weight: t.useBarriers ? 1 : 0,
  calming_weight: t.useCalming ? 1 : 0,
  junction_weight: t.useJunctionDanger ? 1 : 0,
  signal_weight: t.useSignals ? 1 : 0,
  tfl_live_weight: (t.useTflLive || t.useTomtomLive) ? 1 : 0,
});

const computeMinWeightPerM = (weights) => {
  let r = 1.0;
  if ((weights.tfl_cycleway_weight || 0) > 0) r *= 0.75;
  if ((weights.tfl_quietway_weight || 0) > 0) r *= 0.75;
  if ((weights.green_weight || 0) > 0) r *= 0.8;
  return Math.max(R_MIN, r);
};

const formatRouteStatus = (minWeight, timingMs, profileName) => {
  const timeLabel = timingMs >= 1000
    ? `${(timingMs / 1000).toFixed(1)}s`
    : `${Math.round(timingMs)} ms`;
  const profileBit = profileName ? ` | ${profileName}` : '';
  return `Route calculated in ${timeLabel} | min weight/m: ${minWeight.toFixed(3)}${profileBit}`;
};

const isWeightFormValid = (weights) =>
  ALL_WEIGHT_KEYS.every((k) => {
    const v = weights[k];
    const n = parseFloat(v);
    return !Number.isNaN(n) && n >= 0 && n <= 1;
  });

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

const HeroStat = ({ label, fastest, optimized, unit, theme, optimizedColor }) => {
  const f = parseFloat(fastest);
  const o = parseFloat(optimized);
  const diff = o - f;
  const fmt = (n) => n.toFixed(1);
  const displayDiff = (diff > 0 ? '+' : '') + fmt(diff);
  const diffColor = diff > 0 ? '#f44336' : diff < 0 ? '#4CAF50' : theme.textSub;
  return (
    <div style={{ marginBottom: '8px', fontSize: '12px' }}>
      <div style={{ fontWeight: 'bold', color: theme.textSub, fontSize: '10px', textTransform: 'uppercase', marginBottom: '2px' }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', flexWrap: 'wrap' }}>
        <span style={{ color: theme.textSub }}>{fmt(f)} {unit}</span>
        <span style={{ color: theme.textSub }}>→</span>
        <span style={{ color: optimizedColor, fontWeight: 'bold' }}>{fmt(o)} {unit}</span>
        <span style={{ color: diffColor, marginLeft: 'auto' }}>{displayDiff} {unit}</span>
      </div>
    </div>
  );
};

const CondensedStatRow = ({ label, fastest, optimized, unit, invertDiff, integer, theme }) => {
  const f = parseFloat(fastest);
  const o = parseFloat(optimized);
  const diff = o - f;
  const fmt = integer ? (n) => Math.round(n) : (n) => n.toFixed(1);
  const displayDiff = (diff > 0 ? '+' : '') + fmt(diff);
  let diffColor = theme.textSub;
  if (!invertDiff) {
    if (diff < 0) diffColor = '#4CAF50';
    if (diff > 0) diffColor = '#f44336';
  } else {
    if (diff > 0) diffColor = '#4CAF50';
    if (diff < 0) diffColor = '#f44336';
  }
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', padding: '3px 0', borderBottom: `1px solid ${theme.border}` }}>
      <span style={{ color: theme.textMain, fontWeight: '600', width: '38%' }}>{label}</span>
      <span style={{ color: theme.textMain, width: '32%', textAlign: 'right' }}>{fmt(o)}{unit ? ` ${unit}` : ''}</span>
      <span style={{ color: diffColor, width: '30%', textAlign: 'right' }}>{displayDiff}{unit ? ` ${unit}` : ''}</span>
    </div>
  );
};

const WeightSlider = ({ label, value, onChange, theme }) => (
  <div style={{ marginBottom: '10px' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px', fontSize: '12px' }}>
      <span>{label}</span>
      <span style={{ fontWeight: 'bold', color: theme.textMain, minWidth: '36px', textAlign: 'right' }}>
        {clampWeight(value).toFixed(2)}
      </span>
    </div>
    <input
      type="range"
      min="0"
      max="1"
      step="0.05"
      value={clampWeight(value)}
      onChange={(e) => onChange(clampWeight(e.target.value))}
      style={{ width: '100%', accentColor: theme.routeOptimized, cursor: 'pointer' }}
    />
  </div>
);

const CreateProfileModal = ({ theme, templateWeights, onClose, onCreated }) => {
  const [name, setName] = useState('');
  const [weights, setWeights] = useState({ ...templateWeights });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleWeightChange = (key, raw) => {
    setWeights((prev) => ({ ...prev, [key]: clampWeight(raw) }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!name.trim()) { setError('Profile name is required'); return; }
    if (!isWeightFormValid(weights)) { setError('All weights must be between 0.0 and 1.0'); return; }
    setSubmitting(true);
    try {
      const payload = {
        name: name.trim(),
        weights: Object.fromEntries(ALL_WEIGHT_KEYS.map((k) => [k, clampWeight(weights[k])])),
      };
      const res = await fetch(`${API_BASE}/profiles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.error || 'Failed to create profile'); return; }
      onCreated(data);
    } catch {
      setError('Backend connection error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 3000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px',
    }}>
      <div style={{
        background: theme.bg, color: theme.textMain, borderRadius: '10px',
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)', width: '100%', maxWidth: '420px',
        maxHeight: '85vh', overflow: 'hidden', display: 'flex', flexDirection: 'column',
        border: `1px solid ${theme.border}`,
      }}>
        <div style={{ padding: '14px 16px', borderBottom: `1px solid ${theme.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <strong style={{ fontSize: '15px' }}>Create Profile</strong>
          <button type="button" onClick={onClose} style={{ background: 'none', border: 'none', color: theme.textSub, cursor: 'pointer', fontSize: '16px' }}>✕</button>
        </div>
        <form onSubmit={handleSubmit} style={{ overflowY: 'auto', padding: '14px 16px', flex: 1 }}>
          <p style={{ fontSize: '11px', color: theme.textSub, margin: '0 0 12px 0' }}>
            Weights are activation scalars: 0 = off, 1 = full (100%). Backend penalties handle magnitude.
          </p>
          <label style={{ display: 'block', marginBottom: '12px', fontSize: '12px' }}>
            <span style={{ fontWeight: 'bold' }}>Profile name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={{ display: 'block', width: '100%', marginTop: '4px', padding: '8px', borderRadius: '4px', border: `1px solid ${theme.border}`, background: theme.bg, color: theme.textMain, boxSizing: 'border-box' }}
              placeholder="My custom route style"
            />
          </label>
          {WEIGHT_FIELD_GROUPS.map((group) => (
            <div key={group.title} style={{ marginBottom: '12px' }}>
              <div style={{ fontSize: '10px', fontWeight: 'bold', color: theme.textSub, textTransform: 'uppercase', marginBottom: '6px' }}>{group.title}</div>
              {group.fields.map(({ key, label }) => (
                <WeightSlider
                  key={key}
                  label={label}
                  value={weights[key] ?? 0}
                  onChange={(v) => handleWeightChange(key, v)}
                  theme={theme}
                />
              ))}
            </div>
          ))}
          {error && <p style={{ color: '#f44336', fontSize: '12px', margin: '8px 0 0' }}>{error}</p>}
          <button
            type="submit"
            disabled={submitting || !isWeightFormValid(weights) || !name.trim()}
            style={{
              marginTop: '12px', width: '100%', padding: '10px', borderRadius: '6px', border: 'none',
              background: submitting ? theme.toggleInactive : theme.routeOptimized,
              color: 'white', fontWeight: 'bold', cursor: submitting ? 'default' : 'pointer',
              opacity: (!isWeightFormValid(weights) || !name.trim()) ? 0.5 : 1,
            }}
          >
            {submitting ? 'Saving…' : 'Create Profile'}
          </button>
        </form>
      </div>
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
    () => localStorage.getItem('activeProfileId') || 'safe_commuter'
  );
  const [activeProfile, setActiveProfile] = useState(null);
  const [testMode, setTestMode] = useState(false);
  const [showCreateProfile, setShowCreateProfile] = useState(false);
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

  const [useSafetyRouting, setUseSafetyRouting] = useState(true);
  const [useLighting, setUseLighting] = useState(false);
  const [useTflCycleway, setUseTflCycleway] = useState(false);
  const [useWidth, setUseWidth] = useState(false);
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
  const [useTflQuietway, setUseTflQuietway] = useState(false);
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
    useTflCycleway, useTflQuietway, useGreen, useSpeedStress, useWidth,
    useBarriers, useCalming, useJunctionDanger, useSignals, useTflLive, useTomtomLive,
  };

  const effectiveWeights = testMode
    ? togglesToWeights(toggleState)
    : (activeProfile?.weights || emptyWeights());

  const overlayFlags = testMode ? {
    light: useLighting, hill: useHillRouting, tflCycleway: useTflCycleway,
    tflQuietway: useTflQuietway, green: useGreen, narrow: useWidth,
    disruptions: useTflLive || useTomtomLive,
    barriers: useBarriers, signals: useSignals, junctionDanger: useJunctionDanger, calming: useCalming,
  } : {
    light: effectiveWeights.light_weight > 0,
    hill: effectiveWeights.hill_weight > 0,
    tflCycleway: effectiveWeights.tfl_cycleway_weight > 0,
    tflQuietway: effectiveWeights.tfl_quietway_weight > 0,
    green: effectiveWeights.green_weight > 0,
    narrow: effectiveWeights.width_weight > 0,
    disruptions: effectiveWeights.tfl_live_weight > 0,
    barriers: effectiveWeights.barrier_weight > 0,
    signals: effectiveWeights.signal_weight > 0,
    junctionDanger: effectiveWeights.junction_weight > 0,
    calming: effectiveWeights.calming_weight > 0,
  };

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
        const metaBundle = { minWeight, timingMs, profileName };
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
    useTflCycleway, useTflQuietway, useGreen, useSpeedStress, useWidth,
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
    useTflCycleway, useTflQuietway, useGreen, useSpeedStress, useWidth,
    useBarriers, useCalming, useJunctionDanger, useSignals, useTflLive, useTomtomLive,
  ]);

  useEffect(() => {
    if (routeRevealed && !isCalculating && lastRouteMeta) {
      setStatus(formatRouteStatus(lastRouteMeta.minWeight, lastRouteMeta.timingMs, lastRouteMeta.profileName));
    }
  }, [routeRevealed, isCalculating, lastRouteMeta]);

  const handleGetRoute = () => {
    if (!start || !end) return;
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
    setShowCreateProfile(false);
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
    if (overlayFlags.disruptions && testMode && useTflLive && !tflDisruptionStatus) {
      fetch(`${API_BASE}/admin/tfl_status`)
        .then(r => r.json())
        .then(st => { if (st.edge_count !== undefined) setTflDisruptionStatus(`${st.edge_count} edges`); })
        .catch(() => {});
    }
  }, [overlayFlags.disruptions, testMode, useTflLive, tflDisruptionStatus]);

  useEffect(() => {
    if (overlayFlags.disruptions && testMode && useTomtomLive && !tomtomDisruptionStatus) {
      fetch(`${API_BASE}/admin/tomtom_status`)
        .then(r => r.json())
        .then(st => { if (st.edge_count !== undefined) setTomtomDisruptionStatus(`${st.edge_count} edges`); })
        .catch(() => {});
    }
  }, [overlayFlags.disruptions, testMode, useTomtomLive, tomtomDisruptionStatus]);

  function MapEvents() {
    const disruptionActive = routeRevealed && overlayFlags.disruptions;

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
          const checkTfl = (testMode && useTflLive) || (!testMode && effectiveWeights.tfl_live_weight > 0)
            ? fetch(`${API_BASE}/tfl_disruption_at?lat=${lat}&lon=${lon}&tolerance=0.00025`).then(r => r.json())
            : Promise.resolve({ disruptions: [] });
          const checkTomtom = (testMode && useTomtomLive)
            ? fetch(`${API_BASE}/tomtom_disruption_at?lat=${lat}&lon=${lon}&tolerance=0.00025`).then(r => r.json())
            : Promise.resolve({ disruptions: [] });
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

  const templateWeights = activeProfile?.weights || emptyWeights();

  return (
    <div style={{ height: "100vh", position: "relative", fontFamily: "Segoe UI, Arial, sans-serif" }}>
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
      <div style={{
        position: "absolute", top: "60px", left: "20px", width: "260px", padding: "12px",
        background: theme.bg, borderRadius: "8px", boxShadow: "0 4px 15px rgba(0,0,0,0.5)",
        zIndex: 1000, border: `1px solid ${theme.border}`,
      }}>
        <div style={{ fontSize: "11px", fontWeight: "bold", color: theme.textSub, textTransform: "uppercase", marginBottom: "6px" }}>Active Profile</div>
        <select
          value={activeProfileId}
          onChange={handleProfileChange}
          style={{
            width: "100%", padding: "8px", borderRadius: "4px", border: `1px solid ${theme.border}`,
            background: theme.bg, color: theme.textMain, fontSize: "13px", marginBottom: "10px",
          }}
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
          onClick={() => setShowCreateProfile(true)}
          style={{
            width: "100%", padding: "8px", marginBottom: "8px", borderRadius: "4px",
            border: `1px solid ${theme.border}`, background: theme.toggleInactive,
            color: theme.textMain, fontSize: "12px", fontWeight: "bold", cursor: "pointer",
          }}
        >
          Create Profile
        </button>
        <button
          type="button"
          onClick={handleGetRoute}
          disabled={!start || !end}
          style={{
            width: "100%", padding: "10px", borderRadius: "6px", border: "none",
            background: (!start || !end) ? theme.toggleInactive : theme.routeOptimized,
            color: "white", fontSize: "13px", fontWeight: "bold",
            cursor: (!start || !end) ? "default" : "pointer",
            opacity: (!start || !end) ? 0.55 : 1,
            boxShadow: start && end ? "0 2px 8px rgba(0,0,0,0.25)" : "none",
          }}
        >
          {isCalculating && routeRevealed ? 'Calculating...' : 'Get Route'}
        </button>
      </div>

      {showCreateProfile && (
        <CreateProfileModal
          theme={theme}
          templateWeights={templateWeights}
          onClose={() => setShowCreateProfile(false)}
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
        {routeRevealed && overlayFlags.light && litSegments.map((s, i) => <Polyline key={`lit-${i}`} positions={s} color={theme.litColor} weight={4} opacity={1.0} />)}
        {routeRevealed && overlayFlags.hill && !overlayFlags.light && steepSegments.map((s, i) => <Polyline key={`steep-${i}`} positions={s} color={theme.steepColor} weight={5} opacity={1.0} />)}
        {routeRevealed && overlayFlags.tflCycleway && tflCyclewayChunks.map((s, i) => <Polyline key={`tfl-c-${i}`} positions={s} color={theme.tflCyclewayColor} weight={4} opacity={0.9} />)}
        {routeRevealed && overlayFlags.tflQuietway && tflQuietwayChunks.map((s, i) => <Polyline key={`tfl-q-${i}`} positions={s} color={theme.tflQuietwayColor} weight={4} opacity={0.9} />)}
        {routeRevealed && overlayFlags.green && greenChunks.map((s, i) => <Polyline key={`green-${i}`} positions={s} color={theme.greenColor} weight={4} opacity={0.9} />)}
        {routeRevealed && overlayFlags.narrow && narrowChunks.map((s, i) => <Polyline key={`narrow-${i}`} positions={s} color={theme.narrowColor} weight={4} opacity={0.9} />)}
        {routeRevealed && overlayFlags.disruptions && disruptionChunks.map((s, i) => <Polyline key={`dis-${i}`} positions={s} color={theme.disruptionColor} weight={5} opacity={0.9} />)}
        {routeRevealed && (overlayFlags.barriers || overlayFlags.signals || overlayFlags.junctionDanger || overlayFlags.calming) && (
          <NodeHighlightMarkers
            nodeHighlights={nodeHighlights}
            showBarriers={overlayFlags.barriers}
            showSignals={overlayFlags.signals}
            showJunctionDanger={overlayFlags.junctionDanger}
            showCalming={overlayFlags.calming}
            theme={theme}
          />
        )}
      </MapContainer>

      {/* TEST MODE PANEL */}
      {testMode && (
      <div style={{ position: "absolute", bottom: "90px", right: "20px", width: "240px", maxHeight: "55vh", overflowY: "auto", padding: "15px", background: theme.bg, borderRadius: "8px", boxShadow: "0 4px 15px rgba(0,0,0,0.5)", zIndex: 1000 }}>
          <h4 style={{ margin: "0 0 4px 0", color: theme.textMain }}>Test Mode</h4>
          <p style={{ fontSize: "10px", color: theme.textSub, margin: "0 0 8px 0", borderBottom: `1px solid ${theme.border}`, paddingBottom: "6px" }}>Overrides active profile</p>
          <div style={{ fontSize: "10px", fontWeight: "bold", color: theme.textSub, marginBottom: "6px", textTransform: "uppercase" }}>Safety</div>
          <Toggle label="Avoid Accidents" isOn={useSafetyRouting} setIsOn={setUseSafetyRouting} activeColor={theme.routeOptimized} theme={theme} />
          <Toggle label="Night Mode" isOn={useLighting} setIsOn={setUseLighting} activeColor="#1976D2" theme={theme} />
          <Toggle label="TfL Cycleways" isOn={useTflCycleway} setIsOn={setUseTflCycleway} activeColor="#1976D2" theme={theme} />
          <Toggle label="Narrow facility" isOn={useWidth} setIsOn={setUseWidth} activeColor="#7B1FA2" theme={theme} />
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
          <Toggle label="TfL Quietways" isOn={useTflQuietway} setIsOn={setUseTflQuietway} activeColor="#388E3C" theme={theme} />
          <Toggle label="Green / scenic" isOn={useGreen} setIsOn={setUseGreen} activeColor="#00796B" theme={theme} />
      </div>
      )}

      {/* STATS PANEL */}
      {routeRevealed && fastestData && safestData && (
      <div style={{ position: "absolute", bottom: "30px", left: "20px", width: "260px", maxHeight: "70vh", overflowY: "auto", padding: "15px", background: theme.bg, borderRadius: "8px", boxShadow: "0 4px 15px rgba(0,0,0,0.5)", zIndex: 1000 }}>
          <h4 style={{ margin: "0 0 10px 0", borderBottom: `1px solid ${theme.border}`, paddingBottom: "5px", color: theme.textMain }}>Route Analysis</h4>
          <HeroStat label="Time" fastest={fastestData.stats.duration_min} optimized={safestData.stats.duration_min} unit="min" theme={theme} optimizedColor={theme.textMain} />
          <HeroStat label="Distance" fastest={(fastestData.stats.length_m / 1000).toFixed(1)} optimized={(safestData.stats.length_m / 1000).toFixed(1)} unit="km" theme={theme} optimizedColor={theme.textMain} />
          <div style={{ borderTop: `1px solid ${theme.border}`, marginTop: "8px", paddingTop: "6px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", fontWeight: "bold", color: theme.textSub, marginBottom: "4px" }}>
              <span style={{ width: "38%" }}>METRIC</span>
              <span style={{ width: "32%", textAlign: "right" }}>VALUE</span>
              <span style={{ width: "30%", textAlign: "right" }}>DELTA</span>
            </div>
            {METRIC_ROWS.map((row) => (
              <CondensedStatRow
                key={row.key}
                label={row.label}
                fastest={fastestData.stats[row.key]}
                optimized={safestData.stats[row.key]}
                unit={row.unit}
                invertDiff={row.invertDiff}
                integer={row.integer}
                theme={theme}
              />
            ))}
          </div>
      </div>
      )}
    </div>
  );
}

export default App;

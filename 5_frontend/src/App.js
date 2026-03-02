/**
 * Main app: cycling route planner (fastest vs optimized, toggles, inspector).
 * Backend: 4_backend_engine/app.py (port 5000).
 * When changing features or architecture, update 0_documentation/APP_MAIN.md
 */
import React, { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Polyline, CircleMarker, Popup, useMapEvents, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

let DefaultIcon = L.icon({
    iconUrl: icon, shadowUrl: iconShadow,
    iconSize: [25, 41], iconAnchor: [12, 41]
});
L.Marker.prototype.options.icon = DefaultIcon;

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

const Toggle = ({ label, isOn, setIsOn, activeColor, theme }) => (
    <div style={toggleStyle.container} onClick={() => setIsOn(!isOn)}>
        <span style={{ fontSize: "13px", fontWeight: "bold", color: theme.textMain }}>{label}</span>
        <div style={toggleStyle.switch}>
            <div style={toggleStyle.slider(isOn, activeColor, theme.toggleInactive)}>
                <div style={toggleStyle.knob(isOn)}></div>
            </div>
        </div>
    </div>
);

const StatRow = ({ label, valGrey, valRed, unit, invertDiff = false, theme, optimizedColor }) => {
    const numGrey = parseFloat(valGrey);
    const numRed = parseFloat(valRed);
    const diff = numRed - numGrey;
    
    let format = (n) => n.toFixed(1);
    if (["Accidents", "Elevation", "Steep Seg.", "Barriers", "Calming", "Signals", "Junctions"].includes(label)) format = (n) => Math.round(n);
    if (label === "Speed stress" && unit === "%") format = (n) => n.toFixed(1);
    
    const displayDiff = (diff > 0 ? "+" : "") + format(diff);
    
    let diffColor = theme.textMain;
    if (!invertDiff) {
        if (diff < 0) diffColor = "#4CAF50"; 
        if (diff > 0) diffColor = "#f44336"; 
    } else {
        if (diff > 0) diffColor = "#4CAF50"; 
        if (diff < 0) diffColor = "#f44336";
    }

    return (
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", marginBottom: "8px", borderBottom: `1px solid ${theme.border}`, paddingBottom: "4px" }}>
            <span style={{ color: theme.textMain, fontWeight: "bold", width: "30%" }}>{label}</span>
            <span style={{ color: theme.textSub, width: "25%" }}>{valGrey} {unit}</span>
            <span style={{ color: optimizedColor, width: "25%", fontWeight: "bold" }}>{valRed} {unit}</span>
            <span style={{ color: diffColor, width: "20%", textAlign: "right" }}>{displayDiff} {unit}</span>
        </div>
    );
};

// --- TfL / TomTom DISRUPTION DETAIL WINDOWS (left-click on disruption) ---
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
      background: theme.bg,
      color: theme.textMain,
      padding: '12px',
      borderRadius: '8px',
      boxShadow: '0 4px 15px rgba(0,0,0,0.5)',
      zIndex: 2000,
      width: panelWidth,
      maxWidth: '92vw',
      maxHeight: maxPanelHeight,
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      fontSize: '11px',
      border: `1px solid ${theme.border}`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', borderBottom: `1px solid ${theme.border}`, flexShrink: 0 }}>
        <strong style={{ fontSize: '13px' }}>TfL disruption data</strong>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: theme.textSub, cursor: 'pointer', padding: '0 4px' }}>✕</button>
      </div>
      <div style={{ overflowY: 'auto', flex: 1, minHeight: 0 }}>
        {disruptions.map((d, idx) => {
          const id = d.id ?? d.disruptionId ?? `#${idx + 1}`;
          return (
            <div key={id} style={{ marginBottom: idx < disruptions.length - 1 ? '16px' : 0, breakInside: 'avoid' }}>
              {disruptions.length > 1 && (
                <div style={{ fontWeight: 'bold', color: theme.textSub, marginBottom: '6px', fontSize: '10px' }}>Disruption {idx + 1}: {id}</div>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                {Object.keys(d).sort().map((k) => {
                  const v = d[k];
                  const str = formatDisruptionValue(v);
                  const isLong = str.length > 120;
                  return (
                    <div key={k} style={{ lineHeight: 1.4, borderBottom: `1px solid ${theme.border}`, paddingBottom: '4px', marginBottom: '4px' }}>
                      <span style={{ color: theme.textSub, fontWeight: '600', fontSize: '10px' }}>{k}:</span>
                      <div style={{ wordBreak: 'break-word', whiteSpace: isLong ? 'pre-wrap' : 'normal', fontSize: '11px', marginTop: '2px' }}>{str}</div>
                    </div>
                  );
                })}
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
      background: theme.bg,
      color: theme.textMain,
      padding: '12px',
      borderRadius: '8px',
      boxShadow: '0 4px 15px rgba(0,0,0,0.5)',
      zIndex: 2000,
      width: panelWidth,
      maxWidth: '92vw',
      maxHeight: maxPanelHeight,
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      fontSize: '11px',
      border: `1px solid ${theme.border}`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', borderBottom: `1px solid ${theme.border}`, flexShrink: 0 }}>
        <strong style={{ fontSize: '13px' }}>TomTom disruption data</strong>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: theme.textSub, cursor: 'pointer', padding: '0 4px' }}>✕</button>
      </div>
      <div style={{ overflowY: 'auto', flex: 1, minHeight: 0 }}>
        {disruptions.map((d, idx) => {
          const id = (d.properties && d.properties.id) ?? d.id ?? `#${idx + 1}`;
          return (
            <div key={String(id)} style={{ marginBottom: idx < disruptions.length - 1 ? '16px' : 0, breakInside: 'avoid' }}>
              {disruptions.length > 1 && (
                <div style={{ fontWeight: 'bold', color: theme.textSub, marginBottom: '6px', fontSize: '10px' }}>Incident {idx + 1}: {id}</div>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                {Object.keys(d).sort().map((k) => {
                  const v = d[k];
                  const str = formatDisruptionValue(v);
                  const isLong = str.length > 120;
                  return (
                    <div key={k} style={{ lineHeight: 1.4, borderBottom: `1px solid ${theme.border}`, paddingBottom: '4px', marginBottom: '4px' }}>
                      <span style={{ color: theme.textSub, fontWeight: '600', fontSize: '10px' }}>{k}:</span>
                      <div style={{ wordBreak: 'break-word', whiteSpace: isLong ? 'pre-wrap' : 'normal', fontSize: '11px', marginTop: '2px' }}>{str}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// --- INSPECTOR WINDOW ---
const InspectorWindow = ({ data, position, onClose, theme }) => {
    const [expanded, setExpanded] = useState(false);

    // Default keys: core segment + elevation + edge-based point features (barrier, give_way, stop_sign)
    const coreKeys = ['name', 'surface', 'maxspeed', 'grade', 'length', 'elevation_start', 'elevation_end', 'barrier', 'barrier_lat', 'barrier_lon', 'give_way', 'give_way_lat', 'give_way_lon', 'stop_sign', 'stop_sign_lat', 'stop_sign_lon', 'tfl_live_category', 'tfl_live_severity', 'tfl_live_description'];
    
    const content = expanded ? data : Object.keys(data)
        .filter(key => coreKeys.includes(key))
        .reduce((obj, key) => { obj[key] = data[key]; return obj; }, {});

    return (
        <div style={{
            position: 'absolute', left: position.x + 20, top: position.y - 40,
            background: theme.bg, color: theme.textMain,
            padding: '15px', borderRadius: '8px',
            boxShadow: '0 4px 15px rgba(0,0,0,0.5)', zIndex: 2000,
            maxWidth: '250px', fontSize: '12px'
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

            <button 
                onClick={() => setExpanded(!expanded)}
                style={{
                    marginTop: '10px', width: '100%', padding: '5px',
                    background: theme.toggleInactive, color: theme.textMain,
                    border: 'none', borderRadius: '4px', cursor: 'pointer'
                }}
            >
                {expanded ? "Show Less" : "Show All Tags"}
            </button>
        </div>
    );
};

// --- NODE HIGHLIGHT MARKERS (zoom-dependent circle size) ---
function NodeHighlightMarkers({ nodeHighlights, useBarriers, useSignals, useJunctionDanger, useCalming, theme }) {
  const map = useMap();
  const [zoom, setZoom] = useState(() => map.getZoom());
  useEffect(() => {
    const onZoom = () => setZoom(map.getZoom());
    map.on('zoomend', onZoom);
    return () => map.off('zoomend', onZoom);
  }, [map]);
  const baseRadius = 1;
  const junctionDangerRadius = 1.5;
  const radiusScale = Math.pow(2, (zoom - 12) / 4);
  const getRadius = (isJunctionDanger) => Math.max(1, Math.round((isJunctionDanger ? junctionDangerRadius : baseRadius) * radiusScale));

  const filtered = nodeHighlights.filter(h =>
    (h.type === 'barrier' && useBarriers) ||
    (h.type === 'signal' && useSignals) ||
    ((h.type === 'junction' || h.type === 'junction_danger' || h.type === 'give_way' || h.type === 'stop_sign') && useJunctionDanger) ||
    (h.type === 'calming' && useCalming)
  );

  const getFillColor = (type) => {
    if (type === 'barrier') return theme.nodeBarrier;
    if (type === 'signal') return theme.nodeSignal;
    if (type === 'calming') return theme.nodeCalming;
    return theme.nodeJunction; // junction, junction_danger, give_way, stop_sign
  };

  return (
    <>
      {filtered.map((h, i) => (
        <CircleMarker
          key={`node-${i}-${h.lat}-${h.lon}`}
          center={[h.lat, h.lon]}
          radius={getRadius(h.type === 'junction_danger')}
          pathOptions={{
            fillColor: getFillColor(h.type),
            color: '#333',
            weight: 1.5,
            fillOpacity: 0.9,
          }}
          eventHandlers={{ click: () => {} }}
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
  const [status, setStatus] = useState("Checking Daylight...");

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

  // Toggles — Safety (incl. TfL Cycleways and Narrow facility)
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
  // Comfort
  const [useRoadBike, setUseRoadBike] = useState(false);
  const [useHillRouting, setUseHillRouting] = useState(false);
  const [useCalming, setUseCalming] = useState(false);
  // Scenery
  const [useTflQuietway, setUseTflQuietway] = useState(false);
  const [useGreen, setUseGreen] = useState(false); 
  
  // Inspector State
  const [inspectorData, setInspectorData] = useState(null);
  const [inspectorPos, setInspectorPos] = useState(null); // {x, y}
  const [inspectorGeo, setInspectorGeo] = useState(null); // Geometry for Red Overlay

  const theme = useLighting ? {
      mode: 'dark',
      bg: '#1a1a1a',
      textMain: '#e0e0e0', textSub: '#a0a0a0', border: '#333', toggleInactive: '#444',
      routeGrey: '#ffffff', routeOptimized: '#40E0D0', litColor: '#FFFF00', steepColor: '#00FF00',
      tflCyclewayColor: '#2196F3', tflQuietwayColor: '#8BC34A', greenColor: '#009688', narrowColor: '#7B1FA2',
      nodeBarrier: '#5D4037', nodeSignal: '#F57C00', nodeJunction: '#795548', nodeCalming: '#00838F',
      disruptionColor: '#FF6D00',
      tileFilter: 'invert(100%) hue-rotate(180deg) brightness(95%) contrast(90%)'
  } : {
      mode: 'light',
      bg: 'white',
      textMain: '#333', textSub: '#666', border: '#f0f0f0', toggleInactive: '#ccc',
      routeGrey: '#555', routeOptimized: '#d32f2f', litColor: 'transparent', steepColor: '#00cc00',
      tflCyclewayColor: '#1976D2', tflQuietwayColor: '#388E3C', greenColor: '#00796B', narrowColor: '#7B1FA2',
      nodeBarrier: '#5D4037', nodeSignal: '#F57C00', nodeJunction: '#795548', nodeCalming: '#00838F',
      disruptionColor: '#FF6D00',
      tileFilter: 'none'
  };

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
                } else {
                    setStatus("Daytime detected. Click map to start.");
                }
            }
        } catch (error) { setStatus("Click map to set Start"); }
    };
    checkDaylight();
  }, []);

// Map Events: start/end, inspector (right-click), disruption detail (left-click when overlay on)
  function MapEvents() {
    const doStartEndClick = (e) => {
      if (!start) {
        setStart([e.latlng.lat, e.latlng.lng]);
        setStatus("Set Destination.");
      } else if (!end) {
        setEnd([e.latlng.lat, e.latlng.lng]);
        setStatus("Calculating...");
        fetchRoutes(start, [e.latlng.lat, e.latlng.lng]);
      } else {
        setStart([e.latlng.lat, e.latlng.lng]);
        setEnd(null);
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
        setStatus("New Start.");
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

        if (useTflLive || useTomtomLive) {
          const checkTfl = useTflLive ? fetch(`http://127.0.0.1:5000/tfl_disruption_at?lat=${lat}&lon=${lon}&tolerance=0.00025`).then(r => r.json()) : Promise.resolve({ disruptions: [] });
          const checkTomtom = useTomtomLive ? fetch(`http://127.0.0.1:5000/tomtom_disruption_at?lat=${lat}&lon=${lon}&tolerance=0.00025`).then(r => r.json()) : Promise.resolve({ disruptions: [] });
          Promise.all([checkTfl, checkTomtom]).then(([tflData, tomtomData]) => {
            const tflHit = useTflLive && tflData?.disruptions?.length > 0;
            const tomtomHit = useTomtomLive && tomtomData?.disruptions?.length > 0;
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
        fetch(`http://127.0.0.1:5000/inspect?lat=${e.latlng.lat}&lon=${e.latlng.lng}`)
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

  const fetchRoutes = async (s, e) => {
    const startCoord = s || start;
    const endCoord = e || end;
    if (!startCoord || !endCoord) return;
    const params = new URLSearchParams({
      start_lat: startCoord[0], start_lon: startCoord[1], end_lat: endCoord[0], end_lon: endCoord[1],
      risk_weight: useSafetyRouting ? 1 : 0, light_weight: useLighting ? 1 : 0,
      surface_weight: useRoadBike ? 1 : 0, hill_weight: useHillRouting ? 1 : 0,
      tfl_cycleway_weight: useTflCycleway ? 1 : 0, tfl_quietway_weight: useTflQuietway ? 1 : 0,
      speed_weight: useSpeedStress ? 1 : 0, width_weight: useWidth ? 1 : 0, green_weight: useGreen ? 1 : 0,
      barrier_weight: useBarriers ? 1 : 0, calming_weight: useCalming ? 1 : 0,
      junction_weight: useJunctionDanger ? 1 : 0, signal_weight: useSignals ? 1 : 0,
      tfl_live_weight: (useTflLive || useTomtomLive) ? 1 : 0,
    });
    try {
      const response = await fetch(`http://127.0.0.1:5000/route?${params}`);
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
        setStatus("Route Calculated.");
      } else { setStatus("Error: " + data.error); }
    } catch (err) { console.error(err); setStatus("Backend Error."); }
  };

  useEffect(() => {
    if (start && end) fetchRoutes(start, end);
  }, [
    useSafetyRouting, useLighting, useRoadBike, useHillRouting,
    useTflCycleway, useTflQuietway, useGreen, useSpeedStress, useWidth, useBarriers, useCalming, useJunctionDanger, useSignals, useTflLive, useTomtomLive
  ]);

  const handleRefreshTfl = () => {
    setTflDisruptionStatus("Fetching...");
    fetch("http://127.0.0.1:5000/admin/update_tfl", { method: "POST" })
      .then(r => r.json())
      .then(d => {
        if (d.ok) setTflDisruptionStatus(`${d.count} disruptions matched`);
        else setTflDisruptionStatus(d.message || "Error");
      })
      .catch(() => setTflDisruptionStatus("Connection error"));
  };

  const handleRefreshTomtom = () => {
    setTomtomDisruptionStatus("Fetching...");
    fetch("http://127.0.0.1:5000/admin/update_tomtom", { method: "POST" })
      .then(r => r.json())
      .then(d => {
        if (d.ok) setTomtomDisruptionStatus(`${d.count} incidents matched`);
        else setTomtomDisruptionStatus(d.message || "Error");
      })
      .catch(() => setTomtomDisruptionStatus("Connection error"));
  };

  // When first turning on a disruption mode, load status from backend if not yet loaded
  useEffect(() => {
    if (useTflLive && !tflDisruptionStatus) {
      fetch("http://127.0.0.1:5000/admin/tfl_status")
        .then(r => r.json())
        .then(st => { if (st.edge_count !== undefined) setTflDisruptionStatus(`${st.edge_count} edges`); })
        .catch(() => {});
    }
  }, [useTflLive]);
  useEffect(() => {
    if (useTomtomLive && !tomtomDisruptionStatus) {
      fetch("http://127.0.0.1:5000/admin/tomtom_status")
        .then(r => r.json())
        .then(st => { if (st.edge_count !== undefined) setTomtomDisruptionStatus(`${st.edge_count} edges`); })
        .catch(() => {});
    }
  }, [useTomtomLive]); 

  return (
    <div style={{ height: "100vh", position: "relative", fontFamily: "Segoe UI, Arial, sans-serif" }}>
      <style>{`.leaflet-tile { filter: ${theme.tileFilter} !important; }`}</style>

      {/* HEADER */}
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: "50px", background: "#111", color: "white", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, boxShadow: "0 2px 10px rgba(0,0,0,0.5)" }}>
        <span style={{ fontWeight: "bold" }}>London Cycle Maps</span>
        <span style={{ marginLeft: "15px", fontSize: "14px", color: "#aaa" }}>| {status}</span>
      </div>

      {/* INSPECTOR WINDOW (If Active) */}
      {inspectorData && inspectorPos && (
          <InspectorWindow 
            data={inspectorData} 
            position={inspectorPos} 
            onClose={() => { setInspectorData(null); setInspectorGeo(null); }} 
            theme={theme} 
          />
      )}
      {tflDisruptionDetail && (
        <TflDisruptionDetailWindow
          disruptions={tflDisruptionDetail.disruptions}
          position={tflDisruptionDetail.position}
          onClose={() => setTflDisruptionDetail(null)}
          theme={theme}
        />
      )}
      {tomtomDisruptionDetail && (
        <TomtomDisruptionDetailWindow
          disruptions={tomtomDisruptionDetail.disruptions}
          position={tomtomDisruptionDetail.position}
          onClose={() => setTomtomDisruptionDetail(null)}
          theme={theme}
        />
      )}

      {/* MAP */}
      <MapContainer center={[51.505, -0.09]} zoom={13} style={{ height: "100%", width: "100%", background: "#111" }}>
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; OpenStreetMap' />
        <MapEvents />
        {start && <Marker position={start} />}
        {end && <Marker position={end} />}

        {/* INSPECTOR RED OVERLAY */}
        {inspectorGeo && (
             <Polyline positions={inspectorGeo} color="red" weight={6} opacity={0.8} />
        )}

        {fastestData && <Polyline positions={fastestData.path} color={theme.routeGrey} weight={6} opacity={0.4} />}
        {safestData && <Polyline positions={safestData.path} color={theme.routeOptimized} weight={5} opacity={1.0} />}
        {useLighting && litSegments.map((s, i) => <Polyline key={`lit-${i}`} positions={s} color={theme.litColor} weight={4} opacity={1.0} />)}
        {useHillRouting && !useLighting && steepSegments.map((s, i) => <Polyline key={`steep-${i}`} positions={s} color={theme.steepColor} weight={5} opacity={1.0} />)}
        {useTflCycleway && tflCyclewayChunks.map((s, i) => <Polyline key={`tfl-c-${i}`} positions={s} color={theme.tflCyclewayColor} weight={4} opacity={0.9} />)}
        {useTflQuietway && tflQuietwayChunks.map((s, i) => <Polyline key={`tfl-q-${i}`} positions={s} color={theme.tflQuietwayColor} weight={4} opacity={0.9} />)}
        {useGreen && greenChunks.map((s, i) => <Polyline key={`green-${i}`} positions={s} color={theme.greenColor} weight={4} opacity={0.9} />)}
        {useWidth && narrowChunks.map((s, i) => <Polyline key={`narrow-${i}`} positions={s} color={theme.narrowColor} weight={4} opacity={0.9} />)}
        {(useTflLive || useTomtomLive) && disruptionChunks.map((s, i) => <Polyline key={`dis-${i}`} positions={s} color={theme.disruptionColor} weight={5} opacity={0.9} />)}
        {(useBarriers || useSignals || useJunctionDanger || useCalming) && (
          <NodeHighlightMarkers
            nodeHighlights={nodeHighlights}
            useBarriers={useBarriers}
            useSignals={useSignals}
            useJunctionDanger={useJunctionDanger}
            useCalming={useCalming}
            theme={theme}
          />
        )}
      </MapContainer>

      {/* CONTROL PANEL — grouped: Safety, Comfort, Scenery */}
      <div style={{ position: "absolute", bottom: "30px", right: "20px", width: "240px", maxHeight: "70vh", overflowY: "auto", padding: "15px", background: theme.bg, borderRadius: "8px", boxShadow: "0 4px 15px rgba(0,0,0,0.5)", zIndex: 1000, transition: "background 0.3s" }}>
          <h4 style={{ margin: "0 0 8px 0", borderBottom: `1px solid ${theme.border}`, paddingBottom: "5px", color: theme.textMain }}>Optimization</h4>
          <div style={{ fontSize: "10px", fontWeight: "bold", color: theme.textSub, marginBottom: "6px", textTransform: "uppercase" }}>Safety</div>
          <Toggle label="Avoid Accidents" isOn={useSafetyRouting} setIsOn={setUseSafetyRouting} activeColor={theme.routeOptimized} theme={theme} />
          <Toggle label="Night Mode" isOn={useLighting} setIsOn={setUseLighting} activeColor="#1976D2" theme={theme} />
          <Toggle label="TfL Cycleways" isOn={useTflCycleway} setIsOn={setUseTflCycleway} activeColor="#1976D2" theme={theme} />
          <Toggle label="Narrow facility" isOn={useWidth} setIsOn={setUseWidth} activeColor="#7B1FA2" theme={theme} />
          <Toggle label="Speed stress" isOn={useSpeedStress} setIsOn={setUseSpeedStress} activeColor="#E65100" theme={theme} />
          <Toggle label="Traffic signals" isOn={useSignals} setIsOn={setUseSignals} activeColor="#F57C00" theme={theme} />
          <Toggle label="Barriers" isOn={useBarriers} setIsOn={setUseBarriers} activeColor="#5D4037" theme={theme} />
          <Toggle label="Junction danger" isOn={useJunctionDanger} setIsOn={setUseJunctionDanger} activeColor="#795548" theme={theme} />
          <Toggle label="Live TfL Disruptions" isOn={useTflLive} setIsOn={setUseTflLive} activeColor="#FF6D00" theme={theme} />
          {useTflLive && (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px", marginLeft: "12px" }}>
              <button type="button" onClick={handleRefreshTfl} style={{ padding: "4px 10px", fontSize: "11px", background: theme.toggleInactive, border: `1px solid ${theme.border}`, borderRadius: "4px", cursor: "pointer", color: theme.textMain }}>Refresh</button>
              <span style={{ fontSize: "10px", color: theme.textSub }}>{tflDisruptionStatus || "Not loaded"}</span>
            </div>
          )}
          <Toggle label="Live TomTom Disruptions" isOn={useTomtomLive} setIsOn={setUseTomtomLive} activeColor="#D32F2F" theme={theme} />
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

      {/* STATS PANEL */}
      {fastestData && safestData && (
      <div style={{ position: "absolute", bottom: "30px", left: "20px", width: "290px", padding: "15px", background: theme.bg, borderRadius: "8px", boxShadow: "0 4px 15px rgba(0,0,0,0.5)", zIndex: 1000, transition: "background 0.3s" }}>
          <h4 style={{ margin: "0 0 10px 0", borderBottom: `1px solid ${theme.border}`, paddingBottom: "5px", color: theme.textMain }}>Route Analysis</h4>
          
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", fontWeight: "bold", color: theme.textSub, marginBottom: "5px" }}>
              <span style={{ width: "30%" }}>METRIC</span>
              <span style={{ width: "25%" }}>FASTEST</span>
              <span style={{ width: "25%" }}>OPTIMIZED</span>
              <span style={{ width: "20%", textAlign: "right" }}>DIFF</span>
          </div>

          <StatRow label="Time" valGrey={fastestData.stats.duration_min} valRed={safestData.stats.duration_min} unit="min" theme={theme} optimizedColor={theme.routeOptimized} />
          <StatRow label="Distance" valGrey={(fastestData.stats.length_m / 1000).toFixed(1)} valRed={(safestData.stats.length_m / 1000).toFixed(1)} unit="km" theme={theme} optimizedColor={theme.routeOptimized} />
          {useSafetyRouting && <StatRow label="Accidents" valGrey={fastestData.stats.accidents} valRed={safestData.stats.accidents} unit="" theme={theme} optimizedColor={theme.routeOptimized} />}
          {useLighting && <StatRow label="Lit" valGrey={fastestData.stats.illumination_pct} valRed={safestData.stats.illumination_pct} unit="%" invertDiff={true} theme={theme} optimizedColor={theme.routeOptimized} />}
          {useRoadBike && <StatRow label="Rough Surf." valGrey={fastestData.stats.rough_pct} valRed={safestData.stats.rough_pct} unit="%" theme={theme} optimizedColor={theme.routeOptimized} />}
          {useHillRouting && (
            <>
              <StatRow label="Elevation" valGrey={fastestData.stats.elevation_gain} valRed={safestData.stats.elevation_gain} unit="m" theme={theme} optimizedColor={theme.routeOptimized} />
              <StatRow label="Steep Seg." valGrey={fastestData.stats.steep_count} valRed={safestData.stats.steep_count} unit="" theme={theme} optimizedColor={theme.routeOptimized} />
            </>
          )}
          {useTflCycleway && <StatRow label="TfL Cycleway" valGrey={fastestData.stats.tfl_cycleway_pct} valRed={safestData.stats.tfl_cycleway_pct} unit="%" invertDiff={true} theme={theme} optimizedColor={theme.routeOptimized} />}
          {useTflQuietway && <StatRow label="TfL Quietway" valGrey={fastestData.stats.tfl_quietway_pct} valRed={safestData.stats.tfl_quietway_pct} unit="%" invertDiff={true} theme={theme} optimizedColor={theme.routeOptimized} />}
          {useSpeedStress && <StatRow label="Speed stress" valGrey={fastestData.stats.speed_stress_pct} valRed={safestData.stats.speed_stress_pct} unit="%" theme={theme} optimizedColor={theme.routeOptimized} />}
          {useWidth && <StatRow label="Narrow" valGrey={fastestData.stats.narrow_km} valRed={safestData.stats.narrow_km} unit="km" theme={theme} optimizedColor={theme.routeOptimized} />}
          {useGreen && <StatRow label="Green" valGrey={fastestData.stats.green_km} valRed={safestData.stats.green_km} unit="km" invertDiff={true} theme={theme} optimizedColor={theme.routeOptimized} />}
          {useBarriers && <StatRow label="Barriers" valGrey={fastestData.stats.barrier_count} valRed={safestData.stats.barrier_count} unit="" theme={theme} optimizedColor={theme.routeOptimized} />}
          {useCalming && <StatRow label="Calming" valGrey={fastestData.stats.calming_count} valRed={safestData.stats.calming_count} unit="" theme={theme} optimizedColor={theme.routeOptimized} />}
          {useSignals && <StatRow label="Signals" valGrey={fastestData.stats.signal_count} valRed={safestData.stats.signal_count} unit="" theme={theme} optimizedColor={theme.routeOptimized} />}
          {useJunctionDanger && <StatRow label="Junctions" valGrey={fastestData.stats.junction_count} valRed={safestData.stats.junction_count} unit="" theme={theme} optimizedColor={theme.routeOptimized} />}
          {(useTflLive || useTomtomLive) && <StatRow label="Disruptions" valGrey={fastestData.stats.disruption_count} valRed={safestData.stats.disruption_count} unit="" theme={theme} optimizedColor={theme.routeOptimized} />}
      </div>
      )}
    </div>
  );
}

export default App;
/**
 * Debug app: data overlays (uphill, accidents, surfaces, unlit) + segment inspector.
 * Backend: 4_backend_engine/app_debug.py (port 5001).
 * When changing modes or architecture, update 0_documentation/APP_DEBUG.md
 */
import React, { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Polyline, Polygon, CircleMarker, useMapEvents } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

const toggleStyle = {
    container: { display: "flex", justifyContent: "space-between", marginBottom: "12px", cursor: "pointer" },
    switch: { position: "relative", width: "36px", height: "18px", marginLeft: "10px" },
    slider: (isOn, activeColor) => ({
        position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: isOn ? activeColor : "#ccc", transition: ".3s", borderRadius: "18px"
    }),
    knob: (isOn) => ({
        position: "absolute", height: "14px", width: "14px", left: "2px", bottom: "2px",
        backgroundColor: "white", transition: ".3s", borderRadius: "50%",
        transform: isOn ? "translateX(18px)" : "translateX(0)"
    })
};

const Toggle = ({ label, isOn, setIsOn, activeColor }) => (
    <div style={toggleStyle.container} onClick={() => setIsOn(!isOn)}>
        <span style={{ fontSize: "13px", fontWeight: "bold", color: "#333" }}>{label}</span>
        <div style={toggleStyle.switch}>
            <div style={toggleStyle.slider(isOn, activeColor)}>
                <div style={toggleStyle.knob(isOn)}></div>
            </div>
        </div>
    </div>
);

// Tag groups for inspector (order + all known keys; empty values shown as "—")
const INSPECTOR_GROUPS = [
    { title: 'Identity & geometry', keys: ['osm_id', 'name', 'type', 'length', 'risk', 'barrier_confidence'] },
    { title: 'Surface & quality', keys: ['surface', 'lit', 'maxspeed', 'width', 'bridge', 'tunnel', 'junction', 'smoothness'] },
    { title: 'Cycleway', keys: ['cycleway', 'cycleway_left', 'cycleway_right', 'cycleway_both', 'segregated', 'cycleway_separation', 'cycleway_left_separation', 'cycleway_right_separation', 'cycleway_buffer', 'cycleway_width', 'cycleway_surface', 'cycleway_smoothness'] },
    { title: 'Strategic networks', keys: ['lcn_ref', 'rcn_ref', 'ncn_ref', 'cycle_network', 'tfl_cycle_programme', 'tfl_cycle_route'] },
    { title: 'Traffic & stress', keys: ['hgv', 'traffic_calming', 'traffic_calming_point', 'traffic_calming_point_lat', 'traffic_calming_point_lon'] },
    { title: 'Elevation', keys: ['grade', 'elevation_start', 'elevation_end'] },
    { title: 'Live disruptions', keys: ['tfl_live_category', 'tfl_live_severity', 'tfl_live_description', 'tfl_live_iconCategory', 'tfl_live_magnitudeOfDelay'] },
];

const formatTagValue = (key, v) => {
    if (v === undefined || v === null || String(v).trim() === '' || String(v).toLowerCase() === 'none') return '—';
    if (key === 'length' && typeof v === 'number') return Math.round(v);
    if (key === 'length' && typeof v === 'string') { const n = parseFloat(v); return isNaN(n) ? v : Math.round(n); }
    return v;
};

// --- INSPECTOR WINDOW ---
const InspectorWindow = ({ data, position, onClose }) => {
    const [expanded, setExpanded] = useState(false);

    const allGroupKeys = INSPECTOR_GROUPS.flatMap(g => g.keys);
    const dataKeys = Object.keys(data || {}).filter(k => k !== 'geometry');
    const otherKeys = dataKeys.filter(k => !allGroupKeys.includes(k));
    const totalTags = allGroupKeys.length + otherKeys.length;
    const numCols = totalTags <= 12 ? 1 : totalTags <= 24 ? 2 : 3;
    const colWidth = 160;
    const panelWidth = Math.min(numCols * colWidth + 32, 92 * window.innerWidth / 100);
    const maxPanelHeight = Math.min(420, 70 * window.innerHeight / 100);

    const entriesByGroup = INSPECTOR_GROUPS.map(g => ({
        title: g.title,
        entries: g.keys.map(k => [k, formatTagValue(k, data?.[k])])
    }));
    if (otherKeys.length) {
        entriesByGroup.push({ title: 'Other', entries: otherKeys.map(k => [k, formatTagValue(k, data?.[k])]) });
    }

    return (
        <div style={{
            position: 'absolute', left: Math.min(position.x + 20, window.innerWidth - panelWidth - 20), top: position.y - 40,
            background: 'white', color: '#333',
            padding: '12px', borderRadius: '8px',
            boxShadow: '0 4px 15px rgba(0,0,0,0.5)', zIndex: 2000,
            width: panelWidth, maxWidth: '92vw',
            maxHeight: maxPanelHeight, overflow: 'hidden', display: 'flex', flexDirection: 'column',
            fontSize: '11px'
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', borderBottom: '1px solid #e0e0e0', flexShrink: 0 }}>
                <strong style={{ fontSize: '13px' }}>Segment Inspector</strong>
                <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#666', cursor: 'pointer', padding: '0 4px' }}>✕</button>
            </div>
            <div style={{ overflowY: 'auto', flex: 1, minHeight: 0 }}>
                <div style={{ display: 'grid', gridTemplateColumns: `repeat(${numCols}, 1fr)`, gap: '0 16px', alignItems: 'start' }}>
                    {entriesByGroup.map(grp => (
                        <div key={grp.title} style={{ breakInside: 'avoid' }}>
                            <div style={{ fontWeight: 'bold', color: '#555', marginBottom: '4px', fontSize: '10px', textTransform: 'uppercase' }}>{grp.title}</div>
                            {grp.entries.map(([k, v]) => (
                                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', marginBottom: '2px', lineHeight: 1.35 }}>
                                    <span style={{ color: '#666', flexShrink: 0 }}>{k}:</span>
                                    <span style={{ fontWeight: '500', wordBreak: 'break-word', textAlign: 'right' }}>{v}</span>
                                </div>
                            ))}
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

// --- TfL DISRUPTION DETAIL WINDOW (left-click on disruption: full TfL payload) ---
const formatTflValue = (v) => {
    if (v === undefined || v === null) return '—';
    if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v);
    return JSON.stringify(v, null, 2);
};

const TflDisruptionDetailWindow = ({ disruptions, position, onClose }) => {
    if (!disruptions?.length || !position) return null;
    const maxPanelHeight = Math.min(480, 75 * window.innerHeight / 100);
    const panelWidth = Math.min(420, 90 * window.innerWidth / 100);

    return (
        <div style={{
            position: 'absolute',
            left: Math.min(position.x + 16, window.innerWidth - panelWidth - 16),
            top: Math.min(position.y - 24, window.innerHeight - maxPanelHeight - 16),
            background: 'white',
            color: '#333',
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
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', borderBottom: '1px solid #e0e0e0', flexShrink: 0 }}>
                <strong style={{ fontSize: '13px' }}>TfL disruption data</strong>
                <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#666', cursor: 'pointer', padding: '0 4px' }}>✕</button>
            </div>
            <div style={{ overflowY: 'auto', flex: 1, minHeight: 0 }}>
                {disruptions.map((d, idx) => {
                    const id = d.id ?? d.disruptionId ?? `#${idx + 1}`;
                    return (
                        <div key={id} style={{ marginBottom: idx < disruptions.length - 1 ? '16px' : 0, breakInside: 'avoid' }}>
                            {disruptions.length > 1 && (
                                <div style={{ fontWeight: 'bold', color: '#555', marginBottom: '6px', fontSize: '10px' }}>
                                    Disruption {idx + 1}: {id}
                                </div>
                            )}
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                                {Object.keys(d).sort().map((k) => {
                                    const v = d[k];
                                    const str = formatTflValue(v);
                                    const isLong = str.length > 120;
                                    return (
                                        <div key={k} style={{ lineHeight: 1.4, borderBottom: '1px solid #f0f0f0', paddingBottom: '4px', marginBottom: '4px' }}>
                                            <span style={{ color: '#666', fontWeight: '600', fontSize: '10px' }}>{k}:</span>
                                            <div style={{ wordBreak: 'break-word', whiteSpace: isLong ? 'pre-wrap' : 'normal', fontSize: '11px', marginTop: '2px' }}>
                                                {str}
                                            </div>
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

// --- TomTom DISRUPTION DETAIL WINDOW (left-click on TomTom segment: full TomTom incident payload) ---
const TomtomDisruptionDetailWindow = ({ disruptions, position, onClose }) => {
    if (!disruptions?.length || !position) return null;
    const maxPanelHeight = Math.min(480, 75 * window.innerHeight / 100);
    const panelWidth = Math.min(420, 90 * window.innerWidth / 100);

    return (
        <div style={{
            position: 'absolute',
            left: Math.min(position.x + 16, window.innerWidth - panelWidth - 16),
            top: Math.min(position.y - 24, window.innerHeight - maxPanelHeight - 16),
            background: 'white',
            color: '#333',
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
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', borderBottom: '1px solid #e0e0e0', flexShrink: 0 }}>
                <strong style={{ fontSize: '13px' }}>TomTom disruption data</strong>
                <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#666', cursor: 'pointer', padding: '0 4px' }}>✕</button>
            </div>
            <div style={{ overflowY: 'auto', flex: 1, minHeight: 0 }}>
                {disruptions.map((d, idx) => {
                    const id = (d.properties && d.properties.id) ?? d.id ?? `#${idx + 1}`;
                    return (
                        <div key={String(id)} style={{ marginBottom: idx < disruptions.length - 1 ? '16px' : 0, breakInside: 'avoid' }}>
                            {disruptions.length > 1 && (
                                <div style={{ fontWeight: 'bold', color: '#555', marginBottom: '6px', fontSize: '10px' }}>
                                    Incident {idx + 1}: {id}
                                </div>
                            )}
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                                {Object.keys(d).sort().map((k) => {
                                    const v = d[k];
                                    const str = formatTflValue(v);
                                    const isLong = str.length > 120;
                                    return (
                                        <div key={k} style={{ lineHeight: 1.4, borderBottom: '1px solid #f0f0f0', paddingBottom: '4px', marginBottom: '4px' }}>
                                            <span style={{ color: '#666', fontWeight: '600', fontSize: '10px' }}>{k}:</span>
                                            <div style={{ wordBreak: 'break-word', whiteSpace: isLong ? 'pre-wrap' : 'normal', fontSize: '11px', marginTop: '2px' }}>
                                                {str}
                                            </div>
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

// Surface/smoothness value → color (grouped; matches graph BAD_SURFACES / BAD_SMOOTHNESS)
const SURFACE_VALUE_COLORS = {
    cobblestone: '#E53935', unhewn_cobblestone: '#E53935', sett: '#E53935',
    gravel: '#FB8C00', fine_gravel: '#FB8C00', grit: '#FB8C00', pebblestone: '#FB8C00',
    grass: '#43A047', grass_paver: '#43A047',
    dirt: '#8D6E63', earth: '#8D6E63', mud: '#8D6E63', ground: '#8D6E63', clay: '#8D6E63',
    sand: '#FFD54F', woodchips: '#FFD54F', wood: '#FFD54F',
    unpaved: '#FF7043', stone: '#FF7043', stepping_stones: '#FF7043',
    bad: '#7B1FA2', very_bad: '#7B1FA2', horrible: '#7B1FA2', impassable: '#7B1FA2',
};
const getSurfaceColor = (seg) => {
    if (seg.t === 'no_data') return '#546E7A'; // blue-grey, more visible than grey
    return SURFACE_VALUE_COLORS[seg.s] || '#FF7043';
};

// Unlit type to color
const getUnlitColor = (type) => type === 'no' ? '#1565C0' : '#90CAF9';

// Traffic calming type → color (from graph report; fallback grey)
const TRAFFIC_CALMING_COLORS = {
    table: '#E53935', cushion: '#FB8C00', choker: '#8D6E63', yes: '#78909C',
    hump: '#43A047', bump: '#1E88E5', rumble_strip: '#7B1FA2', chicane: '#00897B',
    no: '#9E9E9E', planter: '#5D4037',
};
const getTrafficCalmingColor = (type) => TRAFFIC_CALMING_COLORS[String(type).toLowerCase()] || '#757575';

// Junction (edge) type → color (roundabout, circular, etc.)
const JUNCTION_COLORS = {
    roundabout: '#7B1FA2', circular: '#AB47BC', approach: '#CE93D8', teardrop: '#E1BEE7',
    intersection: '#F48FB1', jughandle: '#F8BBD9', turning_loop: '#FCE4EC',
};
const getJunctionColor = (type) => JUNCTION_COLORS[String(type).toLowerCase()] || '#9C27B0';

// Barrier clusters (barrier_clusters.py) — one colour per routing group.
const BARRIER_CLUSTER_COLORS = {
    1: '#2E7D32',  // free flow
    2: '#1976D2',  // permeable slow-down
    3: '#F57C00',  // stop & push
    4: '#C62828',  // lift / squeeze / hostile
    5: '#212121',  // impassable
};
const BARRIER_CLUSTER_LABELS = {
    1: 'Free flow (0m)',
    2: 'Permeable (+15m)',
    3: 'Stop/push (+35m)',
    4: 'Hostile (+90m)',
    5: 'Impassable',
};
const getBarrierColor = (point) => {
    const d = point?.details || {};
    if (d.barrier_cluster_color) return d.barrier_cluster_color;
    const c = d.barrier_cluster;
    if (c != null) return BARRIER_CLUSTER_COLORS[c] || '#9E9E9E';
    return '#9E9E9E';
};

// TfL live disruption type → color
const TFL_DISRUPTION_COLORS = {
    closure: '#D32F2F',
    diversion: '#1565C0',
    works: '#F9A825',
    incident: '#E65100',
    other: '#757575',
};
const getTflDisruptionColor = (type) => TFL_DISRUPTION_COLORS[String(type).toLowerCase()] || '#757575';

// TomTom clusters: A=closure, B=roadworks, C=jam, D=environmental (dashed)
const TOMTOM_DISRUPTION_COLORS = {
    closure: '#FF0000',
    roadworks: '#FFD700',
    jam: '#FFA500',
    environmental: '#0000FF',
    other: '#757575',
};
const getTomtomDisruptionColor = (type) => TOMTOM_DISRUPTION_COLORS[String(type).toLowerCase()] || '#757575';

const ATTRACTION_TYPE_COLORS = { park: '#2E7D32', river: '#1565C0', sight: '#6A1B9A' };
const PARK_HOURS_OPEN_COLOR = '#00C853';
const PARK_HOURS_CLOSED_COLOR = '#D50000';

const attractionZonePathOptions = (type, { fillOpacity = 0.18, weight = 1.5, lineOpacity = 0.85 } = {}) => {
    const color = ATTRACTION_TYPE_COLORS[type] || '#00796B';
    return { color, fillColor: color, fillOpacity, weight, opacity: lineOpacity };
};

// Subtoggle (smaller, indented)
const Subtoggle = ({ label, isOn, setIsOn, activeColor }) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', marginLeft: '12px', cursor: 'pointer' }} onClick={() => setIsOn(!isOn)}>
        <span style={{ fontSize: '12px', color: '#555' }}>{label}</span>
        <div style={{ width: '28px', height: '14px', borderRadius: '14px', background: isOn ? (activeColor || '#666') : '#ddd', position: 'relative' }}>
            <div style={{ position: 'absolute', width: '10px', height: '10px', borderRadius: '50%', background: 'white', top: '2px', left: isOn ? '16px' : '2px', transition: 'left 0.2s' }} />
        </div>
    </div>
);

// --- DEBUG PANEL ---
const DebugPanel = ({
    heatmapOn, setHeatmapOn,
    accidentsOn, setAccidentsOn,
    surfacesOn, setSurfacesOn, surfaceNoDataOn, setSurfaceNoDataOn, surfaceLimitReached,
    unlitOn, setUnlitOn, unlitNoDataOn, setUnlitNoDataOn, unlitLimitReached,
    cyclewayOn, setCyclewayOn, cyclewayGeneralOn, setCyclewayGeneralOn, cyclewaySegregatedOn, setCyclewaySegregatedOn,
    hgvBannedOn, setHgvBannedOn,
    graphNetworkOn, setGraphNetworkOn, graphNetworkLimitReached,
    tflRoutesOn, setTflRoutesOn,
    attractionsOn, setAttractionsOn,
    attractionParkOn, setAttractionParkOn,
    attractionRiverOn, setAttractionRiverOn,
    attractionSightOn, setAttractionSightOn,
    attractionParkHoursOn, setAttractionParkHoursOn,
    attractionLimitReached,
    tflDisruptionsOn, setTflDisruptionsOn, onRefreshTfl, tflDisruptionStatus,
    tomtomDisruptionsOn, setTomtomDisruptionsOn, onRefreshTomtom, tomtomDisruptionStatus,
    tflGroundTruthOn, setTflGroundTruthOn,
    trafficCalmingOn, setTrafficCalmingOn,
    calmingSource, setCalmingSource,
    junctionOn, setJunctionOn,
    barriersOn, setBarriersOn, trafficSignalsOn, setTrafficSignalsOn, miniRoundaboutOn, setMiniRoundaboutOn,
    crossingOn, setCrossingOn, giveWayOn, setGiveWayOn, stopOn, setStopOn,
    forceCollapsed,
}) => {
    const [collapsed, setCollapsed] = useState(true);
    const effectivelyCollapsed = forceCollapsed || collapsed;

    return (
        <div style={{
            position: 'absolute', top: '10px', right: '10px',
            background: 'white', borderRadius: '8px',
            boxShadow: '0 4px 15px rgba(0,0,0,0.5)', zIndex: 2000,
            transition: 'width 0.3s',
            width: effectivelyCollapsed ? '40px' : '240px',
            overflow: 'hidden'
        }}>
            <div
                onClick={() => !forceCollapsed && setCollapsed(!collapsed)}
                style={{
                    padding: '10px', cursor: 'pointer', background: '#333', color: 'white',
                    display: 'flex', justifyContent: effectivelyCollapsed ? 'center' : 'space-between', alignItems: 'center'
                }}
            >
                {!effectivelyCollapsed && <span style={{ fontWeight: 'bold', fontSize: '12px' }}>DEBUG SUITE</span>}
                <span>{effectivelyCollapsed ? '⚙️' : '▲'}</span>
            </div>

                {!effectivelyCollapsed && (
                <div style={{ padding: '15px', maxHeight: '85vh', overflowY: 'auto' }}>
                    <Toggle label="Uphill" isOn={heatmapOn} setIsOn={setHeatmapOn} activeColor="#FFA500" />

                    {heatmapOn && (
                        <div style={{ marginTop: '5px', marginBottom: '15px', fontSize: '11px', color: '#666' }}>
                            <div style={{ fontWeight: 'bold', marginBottom: '5px' }}>Ascent Legend:</div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#800080', marginRight: 5 }}></div>
                                <span style={{ color: '#800080', fontWeight: 'bold' }}>Artifact Error (40%)</span>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#FF0000', marginRight: 5 }}></div> Steep Ascent (7.5%)
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#FFD700', marginRight: 5 }}></div> Moderate (3.3% - 7.5%)
                            </div>
                            <p style={{ fontStyle: 'italic', marginTop: '8px', color: '#888' }}>Descents & Flat hidden.</p>
                        </div>
                    )}

                    <Toggle label="Accidents" isOn={accidentsOn} setIsOn={setAccidentsOn} activeColor="#ff4444" />

                    {accidentsOn && (
                        <div style={{ marginTop: '5px', marginBottom: '15px', fontSize: '11px', color: '#666' }}>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#ff4444', borderRadius: '50%', marginRight: 5 }}></div>
                                Cyclist collision location
                            </div>
                        </div>
                    )}

                    <Toggle label="Surfaces" isOn={surfacesOn} setIsOn={setSurfacesOn} activeColor="#8D6E63" />
                    {surfacesOn && (
                        <>
                            <Subtoggle label="No surface data" isOn={surfaceNoDataOn} setIsOn={setSurfaceNoDataOn} activeColor="#546E7A" />
                            {surfaceLimitReached && <div style={{ fontSize: '10px', color: '#E65100', marginLeft: 12, marginBottom: 8 }}>20k limit — zoom in to see areas with no tags</div>}
                        </>
                    )}
                    {surfacesOn && (
                        <div style={{ marginTop: '5px', marginBottom: '15px', fontSize: '11px', color: '#666' }}>
                            <div style={{ fontWeight: 'bold', marginBottom: '5px' }}>Surface legend (surface / cycleway_surface / smoothness):</div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#E53935', marginRight: 5 }}></div> Cobblestone / Sett
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#FB8C00', marginRight: 5 }}></div> Gravel / Grit
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#43A047', marginRight: 5 }}></div> Grass
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#8D6E63', marginRight: 5 }}></div> Dirt / Earth / Mud
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#FFD54F', marginRight: 5 }}></div> Sand / Wood
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#FF7043', marginRight: 5 }}></div> Other unpaved
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#7B1FA2', marginRight: 5 }}></div> Bad smoothness
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#546E7A', marginRight: 5 }}></div> No surface data
                            </div>
                        </div>
                    )}

                    <Toggle label="Unlit" isOn={unlitOn} setIsOn={setUnlitOn} activeColor="#1565C0" />
                    {unlitOn && <Subtoggle label="No data (unknown)" isOn={unlitNoDataOn} setIsOn={setUnlitNoDataOn} activeColor="#90CAF9" />}
                    {unlitOn && unlitLimitReached && <div style={{ fontSize: '10px', color: '#E65100', marginLeft: 12, marginBottom: 8 }}>20k limit — zoom in to see more</div>}
                    {unlitOn && (
                        <div style={{ marginTop: '5px', marginBottom: '15px', fontSize: '11px', color: '#666' }}>
                            <div style={{ fontWeight: 'bold', marginBottom: '5px' }}>Lighting Legend:</div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#1565C0', marginRight: 5 }}></div> Confirmed unlit
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#90CAF9', marginRight: 5 }}></div> No data (unknown)
                            </div>
                        </div>
                    )}

                    <Toggle label="Cycleway" isOn={cyclewayOn} setIsOn={setCyclewayOn} activeColor="#2E7D32" />
                    {cyclewayOn && (
                        <div style={{ marginBottom: 10 }}>
                            <Subtoggle label="General (lane/track etc)" isOn={cyclewayGeneralOn} setIsOn={setCyclewayGeneralOn} activeColor="#2E7D32" />
                            <Subtoggle label="Segregated" isOn={cyclewaySegregatedOn} setIsOn={setCyclewaySegregatedOn} activeColor="#66BB6A" />
                        </div>
                    )}

                    <Toggle label="HGV banned" isOn={hgvBannedOn} setIsOn={setHgvBannedOn} activeColor="#BF360C" />

                    <Toggle label="Graph network" isOn={graphNetworkOn} setIsOn={setGraphNetworkOn} activeColor="#607D8B" />
                    {graphNetworkOn && graphNetworkLimitReached && <div style={{ fontSize: '10px', color: '#E65100', marginLeft: 12, marginBottom: 8 }}>15k limit — zoom in to see more</div>}
                    {graphNetworkOn && (
                        <div style={{ marginTop: '5px', marginBottom: '15px', fontSize: '11px', color: '#666' }}>
                            <div style={{ fontWeight: 'bold', marginBottom: '5px' }}>Graph network legend (highway type):</div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#1976D2', marginRight: 5 }}></div> Cycleway
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#7B1FA2', marginRight: 5 }}></div> Footway / Path
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#D32F2F', marginRight: 5 }}></div> Primary
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#F57C00', marginRight: 5 }}></div> Secondary
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#FBC02D', marginRight: 5 }}></div> Tertiary
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#2E7D32', marginRight: 5 }}></div> Residential
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#5D4037', marginRight: 5 }}></div> Service
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
                                <div style={{ width: 12, height: 12, background: '#9E9E9E', marginRight: 5 }}></div> Other / Unknown
                            </div>
                        </div>
                    )}

                    <Toggle label="TfL cycle routes" isOn={tflRoutesOn} setIsOn={setTflRoutesOn} activeColor="#2E7D32" />
                    <Toggle label="Attraction edges" isOn={attractionsOn} setIsOn={setAttractionsOn} activeColor="#00796B" />
                    {attractionsOn && (
                        <div style={{ marginTop: '5px', marginBottom: '10px', fontSize: '10px', color: '#666' }}>
                            <Subtoggle label="Park (is_park)" isOn={attractionParkOn} setIsOn={setAttractionParkOn} />
                            <Subtoggle label="River (is_river)" isOn={attractionRiverOn} setIsOn={setAttractionRiverOn} />
                            <Subtoggle label="Sight (is_sight)" isOn={attractionSightOn} setIsOn={setAttractionSightOn} />
                            {attractionParkOn && (
                                <Subtoggle
                                    label="Park hours (open/closed)"
                                    isOn={attractionParkHoursOn}
                                    setIsOn={setAttractionParkHoursOn}
                                />
                            )}
                            <div style={{ fontWeight: 'bold', marginTop: '6px', marginBottom: '4px' }}>Colours:</div>
                            {attractionParkOn && attractionParkHoursOn ? (
                                <>
                                    <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                        <div style={{ width: 10, height: 10, background: PARK_HOURS_OPEN_COLOR, borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                        Park open (routable)
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                        <div style={{ width: 10, height: 10, background: PARK_HOURS_CLOSED_COLOR, borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                        Park closed (blocked)
                                    </div>
                                </>
                            ) : (
                                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                    <div style={{ width: 10, height: 10, background: ATTRACTION_TYPE_COLORS.park, borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                    Park
                                </div>
                            )}
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                <div style={{ width: 10, height: 10, background: ATTRACTION_TYPE_COLORS.river, borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                River
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                <div style={{ width: 10, height: 10, background: ATTRACTION_TYPE_COLORS.sight, borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                Sight
                            </div>
                            {attractionLimitReached && (
                                <div style={{ marginTop: '6px', color: '#c62828' }}>20k limit — zoom in</div>
                            )}
                        </div>
                    )}
                    {tflRoutesOn && (
                        <div style={{ marginTop: '5px', marginBottom: '10px', fontSize: '10px', color: '#666' }}>
                            <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>TfL programme:</div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                <div style={{ width: 10, height: 10, background: '#2E7D32', borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                Cycleway
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                <div style={{ width: 10, height: 10, background: '#1565C0', borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                Quietway
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                <div style={{ width: 10, height: 10, background: '#E65100', borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                Superhighway
                            </div>
                        </div>
                    )}
                    <Toggle label="TfL Live Disruptions" isOn={tflDisruptionsOn} setIsOn={setTflDisruptionsOn} activeColor="#D32F2F" />
                    {tflDisruptionsOn && (
                        <>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', marginLeft: '12px' }}>
                                <button
                                    type="button"
                                    onClick={onRefreshTfl}
                                    style={{ padding: '4px 10px', fontSize: '11px', background: '#f5f5f5', border: '1px solid #ccc', borderRadius: '4px', cursor: 'pointer' }}
                                >
                                    Refresh Data
                                </button>
                                <span style={{ fontSize: '10px', color: '#888' }}>
                                    {tflDisruptionStatus || 'Not loaded'}
                                </span>
                            </div>
                            <div style={{ marginTop: '5px', marginBottom: '10px', fontSize: '10px', color: '#666' }}>
                                <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>Disruption type:</div>
                                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                    <div style={{ width: 10, height: 10, background: '#D32F2F', borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                    Closure
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                    <div style={{ width: 10, height: 10, background: '#E65100', borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                    Incident
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                    <div style={{ width: 10, height: 10, background: '#F9A825', borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                    Works
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                    <div style={{ width: 10, height: 10, background: '#1565C0', borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                    Diversion
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                    <div style={{ width: 10, height: 10, background: '#757575', borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                    Other
                                </div>
                            </div>
                            <Subtoggle label="Show TfL ground truth (points/lines/polygons)" isOn={tflGroundTruthOn} setIsOn={setTflGroundTruthOn} activeColor="#9C27B0" />
                        </>
                    )}
                    <Toggle label="TomTom Live Disruptions" isOn={tomtomDisruptionsOn} setIsOn={setTomtomDisruptionsOn} activeColor="#FF0000" />
                    {tomtomDisruptionsOn && (
                        <>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', marginLeft: '12px' }}>
                                <button
                                    type="button"
                                    onClick={onRefreshTomtom}
                                    style={{ padding: '4px 10px', fontSize: '11px', background: '#f5f5f5', border: '1px solid #ccc', borderRadius: '4px', cursor: 'pointer' }}
                                >
                                    Refresh Data
                                </button>
                                <span style={{ fontSize: '10px', color: '#888' }}>
                                    {tomtomDisruptionStatus || 'Not loaded'}
                                </span>
                            </div>
                            <div style={{ marginTop: '5px', marginBottom: '10px', fontSize: '10px', color: '#666' }}>
                                <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>TomTom cluster:</div>
                                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                    <div style={{ width: 10, height: 10, background: '#FF0000', borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                    Closure
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                    <div style={{ width: 10, height: 10, background: '#FFD700', borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                    Roadworks
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                    <div style={{ width: 10, height: 10, background: '#FFA500', borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                    Jam / Accident
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                    <div style={{ width: 10, height: 10, background: '#0000FF', borderRadius: 1, marginRight: 5, flexShrink: 0, border: '1px dashed #000' }}></div>
                                    Weather / Env
                                </div>
                            </div>
                        </>
                    )}
                    <Toggle label="Traffic calming (points)" isOn={trafficCalmingOn} setIsOn={setTrafficCalmingOn} activeColor="#F57C00" />
                    {trafficCalmingOn && (
                        <>
                            <div style={{ marginTop: '4px', marginBottom: '6px', fontSize: '11px' }}>
                                <span style={{ color: '#555', marginRight: '6px' }}>Source:</span>
                                <select value={calmingSource} onChange={(e) => setCalmingSource(e.target.value)} style={{ padding: '2px 6px', fontSize: '11px' }}>
                                    <option value="way">Way (OSM ways)</option>
                                    <option value="point">Point (OSM nodes)</option>
                                    <option value="both">Both</option>
                                </select>
                            </div>
                            <div style={{ marginTop: '5px', marginBottom: '10px', fontSize: '10px', color: '#666' }}>
                                <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>Traffic calming:</div>
                                {Object.entries(TRAFFIC_CALMING_COLORS).map(([t, c]) => (
                                    <div key={t} style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                        <div style={{ width: 10, height: 10, background: c, borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                        {t}
                                    </div>
                                ))}
                                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                    <div style={{ width: 10, height: 10, background: '#757575', borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                    Other
                                </div>
                            </div>
                        </>
                    )}

                    <Toggle label="Junction type (edge)" isOn={junctionOn} setIsOn={setJunctionOn} activeColor="#7B1FA2" />
                    {junctionOn && (
                        <div style={{ marginTop: '5px', marginBottom: '10px', fontSize: '10px', color: '#666' }}>
                            <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>Junction type:</div>
                            {Object.entries(JUNCTION_COLORS).map(([t, c]) => (
                                <div key={t} style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                    <div style={{ width: 10, height: 10, background: c, borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                    {t}
                                </div>
                            ))}
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                <div style={{ width: 10, height: 10, background: '#9C27B0', borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                Other
                            </div>
                        </div>
                    )}

                    <div style={{ marginTop: '10px', fontWeight: 'bold', fontSize: '11px', color: '#555' }}>Node tags</div>
                    <Toggle label="Barriers" isOn={barriersOn} setIsOn={setBarriersOn} activeColor="#5D4037" />
                    {barriersOn && (
                        <div style={{ marginTop: '5px', marginBottom: '10px', fontSize: '10px', color: '#666' }}>
                            <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>Barrier clusters (routing):</div>
                            {Object.entries(BARRIER_CLUSTER_COLORS).map(([id, c]) => (
                                <div key={id} style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                    <div style={{ width: 10, height: 10, background: c, borderRadius: 1, marginRight: 5, flexShrink: 0 }}></div>
                                    {BARRIER_CLUSTER_LABELS[id]}
                                </div>
                            ))}
                        </div>
                    )}
                    <Toggle label="Traffic signals" isOn={trafficSignalsOn} setIsOn={setTrafficSignalsOn} activeColor="#D32F2F" />
                    <Toggle label="Mini roundabouts" isOn={miniRoundaboutOn} setIsOn={setMiniRoundaboutOn} activeColor="#7B1FA2" />
                    <Toggle label="Crossing" isOn={crossingOn} setIsOn={setCrossingOn} activeColor="#1976D2" />
                    <Toggle label="Give way" isOn={giveWayOn} setIsOn={setGiveWayOn} activeColor="#F57C00" />
                    <Toggle label="Stop" isOn={stopOn} setIsOn={setStopOn} activeColor="#E64A19" />

                    <div style={{ marginTop: '15px', paddingTop: '10px', borderTop: '1px solid #eee', fontSize: '11px', color: '#999' }}>
                        Right-click any road to inspect segment tags.
                    </div>
                </div>
            )}
        </div>
    );
};

// --- MODIFY SUITE (bottom-left): manual TfL tag edits ---
const ModifyPanel = ({
    modifyTflOn,
    setModifyTflOn,
    modifyTflProgramme,
    setModifyTflProgramme,
    onUndo,
    canUndo,
}) => {
    const [collapsed, setCollapsed] = useState(true);
    return (
        <div style={{
            position: 'absolute',
            bottom: '20px',
            left: '20px',
            background: 'white',
            borderRadius: '8px',
            boxShadow: '0 4px 15px rgba(0,0,0,0.5)',
            zIndex: 2000,
            transition: 'width 0.3s',
            width: collapsed ? '44px' : '260px',
            overflow: 'hidden',
        }}>
            <div
                onClick={() => setCollapsed(!collapsed)}
                style={{
                    padding: '10px',
                    cursor: 'pointer',
                    background: '#2E7D32',
                    color: 'white',
                    display: 'flex',
                    justifyContent: collapsed ? 'center' : 'space-between',
                    alignItems: 'center',
                }}
            >
                {!collapsed && <span style={{ fontWeight: 'bold', fontSize: '12px' }}>MODIFY SUITE</span>}
                <span>{collapsed ? '✎' : '▼'}</span>
            </div>
            {!collapsed && (
                <div style={{ padding: '14px', maxHeight: '70vh', overflowY: 'auto' }}>
                    <Toggle
                        label="Modify TfL cycle routes"
                        isOn={modifyTflOn}
                        setIsOn={setModifyTflOn}
                        activeColor="#2E7D32"
                    />
                    {modifyTflOn && (
                        <>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
                                <button
                                    type="button"
                                    onClick={() => canUndo && onUndo && onUndo()}
                                    disabled={!canUndo}
                                    title={canUndo ? 'Undo last action this session (Ctrl+Z)' : 'Nothing to undo this session'}
                                    style={{
                                        padding: '6px 10px',
                                        fontSize: '14px',
                                        background: canUndo ? '#f5f5f5' : '#eee',
                                        border: '1px solid #ccc',
                                        borderRadius: '6px',
                                        cursor: canUndo ? 'pointer' : 'not-allowed',
                                        opacity: canUndo ? 1 : 0.7,
                                    }}
                                >
                                    ← Undo
                                </button>
                                <span style={{ fontSize: '10px', color: '#888' }}>Ctrl+Z (this session only)</span>
                            </div>
                            <div style={{ marginTop: '6px', marginBottom: '10px', fontSize: '11px', color: '#555', lineHeight: 1.4 }}>
                                Left click = add segment. Right click = remove segment. Select programme below, then click the map.
                            </div>
                            <div style={{ fontWeight: 'bold', fontSize: '11px', color: '#333', marginBottom: '6px' }}>Programme (tag):</div>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                {['cycleway', 'quietway', 'superhighway'].map((prog) => (
                                    <button
                                        key={prog}
                                        onClick={() => setModifyTflProgramme(prog)}
                                        style={{
                                            padding: '6px 12px',
                                            fontSize: '11px',
                                            fontWeight: modifyTflProgramme === prog ? 'bold' : 'normal',
                                            background: modifyTflProgramme === prog ? TFL_PROGRAMME_COLORS[prog] : '#eee',
                                            color: modifyTflProgramme === prog ? '#fff' : '#333',
                                            border: modifyTflProgramme === prog ? `2px solid ${TFL_PROGRAMME_COLORS[prog]}` : '1px solid #ccc',
                                            borderRadius: '6px',
                                            cursor: 'pointer',
                                        }}
                                    >
                                        {prog === 'cycleway' ? 'Cycleway' : prog === 'quietway' ? 'Quietway' : 'Superhighway'}
                                    </button>
                                ))}
                            </div>
                            <div style={{ marginTop: '10px', fontSize: '10px', color: '#888' }}>
                                Added = yellow; Removed = black. Edits are saved to <code style={{ background: '#f0f0f0', padding: '1px 4px' }}>3_pipeline/tfl_manual_edits.json</code>. Run <code style={{ background: '#f0f0f0', padding: '1px 4px' }}>apply_tfl_manual_edits.py</code> to apply to the graph.
                            </div>
                        </>
                    )}
                </div>
            )}
        </div>
    );
};

// --- MODIFY ATTRACTIONS PANEL (bottom-left, stacked below TfL modify) ---
const ModifyAttractionsPanel = ({
    modifyAttractionOn,
    setModifyAttractionOn,
    attractionType,
    setAttractionType,
    attractionName,
    setAttractionName,
    onCompleteGeometry,
    onUndo,
    canUndo,
    scratchCount,
}) => {
    const [collapsed, setCollapsed] = useState(true);
    return (
        <div style={{
            position: 'absolute',
            bottom: '20px',
            left: '290px',
            background: 'white',
            borderRadius: '8px',
            boxShadow: '0 4px 15px rgba(0,0,0,0.5)',
            zIndex: 1999,
            transition: 'width 0.3s',
            width: collapsed ? '44px' : '280px',
            overflow: 'hidden',
            transform: 'translateY(0)',
        }}>
            <div
                onClick={() => setCollapsed(!collapsed)}
                style={{
                    padding: '10px',
                    cursor: 'pointer',
                    background: '#00796B',
                    color: 'white',
                    display: 'flex',
                    justifyContent: collapsed ? 'center' : 'space-between',
                    alignItems: 'center',
                }}
            >
                {!collapsed && <span style={{ fontWeight: 'bold', fontSize: '12px' }}>MODIFY ATTRACTIONS</span>}
                <span>{collapsed ? '◎' : '▼'}</span>
            </div>
            {!collapsed && (
                <div style={{ padding: '14px', maxHeight: '70vh', overflowY: 'auto' }}>
                    <Toggle
                        label="Modify attractions"
                        isOn={modifyAttractionOn}
                        setIsOn={setModifyAttractionOn}
                        activeColor="#00796B"
                    />
                    {modifyAttractionOn && (
                        <>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
                                <button
                                    type="button"
                                    onClick={() => canUndo && onUndo && onUndo()}
                                    disabled={!canUndo}
                                    title={canUndo ? 'Undo last region (Ctrl+Z)' : 'Nothing to undo'}
                                    style={{
                                        padding: '6px 10px',
                                        fontSize: '14px',
                                        background: canUndo ? '#f5f5f5' : '#eee',
                                        border: '1px solid #ccc',
                                        borderRadius: '6px',
                                        cursor: canUndo ? 'pointer' : 'not-allowed',
                                    }}
                                >
                                    ← Undo
                                </button>
                                <span style={{ fontSize: '10px', color: '#888' }}>Ctrl+Z</span>
                            </div>
                            <div style={{ marginBottom: '8px', fontSize: '11px', color: '#555', lineHeight: 1.4 }}>
                                Park / River: click polygon corners (≥3), then Complete. River uses the drawn box as the tagging zone.
                                Sight: one click saves a 200 m radius. Faint fill = tagging zone. Light green = OSM parks.
                            </div>
                            <div style={{ fontWeight: 'bold', fontSize: '11px', marginBottom: '4px' }}>Name (used for all new regions):</div>
                            <input
                                type="text"
                                value={attractionName}
                                onChange={(e) => setAttractionName(e.target.value)}
                                placeholder="e.g. Hyde Park, Thames, Tower Bridge"
                                style={{ width: '100%', boxSizing: 'border-box', marginBottom: '10px', padding: '6px', fontSize: '12px' }}
                            />
                            <div style={{ fontWeight: 'bold', fontSize: '11px', marginBottom: '6px' }}>Type:</div>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '10px' }}>
                                {['park', 'river', 'sight'].map((t) => (
                                    <button
                                        key={t}
                                        type="button"
                                        onClick={() => setAttractionType(t)}
                                        style={{
                                            padding: '6px 12px',
                                            fontSize: '11px',
                                            fontWeight: attractionType === t ? 'bold' : 'normal',
                                            background: attractionType === t ? ATTRACTION_TYPE_COLORS[t] : '#eee',
                                            color: attractionType === t ? '#fff' : '#333',
                                            border: attractionType === t ? `2px solid ${ATTRACTION_TYPE_COLORS[t]}` : '1px solid #ccc',
                                            borderRadius: '6px',
                                            cursor: 'pointer',
                                        }}
                                    >
                                        {t.charAt(0).toUpperCase() + t.slice(1)}
                                    </button>
                                ))}
                            </div>
                            {(attractionType === 'park' || attractionType === 'river') && (
                                <button
                                    type="button"
                                    onClick={() => onCompleteGeometry && onCompleteGeometry()}
                                    style={{
                                        width: '100%',
                                        padding: '8px',
                                        marginBottom: '10px',
                                        fontSize: '12px',
                                        fontWeight: 'bold',
                                        background: '#E0F2F1',
                                        border: '2px solid #00796B',
                                        borderRadius: '6px',
                                        cursor: 'pointer',
                                    }}
                                >
                                    Complete geometry ({scratchCount} points)
                                </button>
                            )}
                            <div style={{ fontSize: '10px', color: '#888' }}>
                                Saved to <code style={{ background: '#f0f0f0', padding: '1px 4px' }}>attraction_manual_regions.json</code>.
                                Run <code style={{ background: '#f0f0f0', padding: '1px 4px' }}>apply_attraction_manual.py</code> after pipeline.
                            </div>
                        </>
                    )}
                </div>
            )}
        </div>
    );
};

// --- HEATMAP LAYER (map event handler) ---
const HeatmapLayer = ({ isOn, setSegments, setStatus }) => {
    const map = useMapEvents({
        moveend: () => {
            if (!isOn) return;
            fetchData();
        }
    });

    const fetchData = () => {
        const bounds = map.getBounds();
        setStatus("Loading uphill...");

        fetch(`http://127.0.0.1:5001/debug/heatmap?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}`)
            .then(res => res.json())
            .then(data => {
                setSegments(data);
                setStatus(`Uphill: ${data.length} segments`);
            })
            .catch(() => setStatus("Connection Error"));
    };

    useEffect(() => {
        if (isOn) fetchData();
        else setSegments([]);
    }, [isOn]);

    return null;
};

// --- SURFACE LAYER (map event handler) ---
const SurfaceLayer = ({ isOn, includeNoData, setSegments, setLimitReached, setStatus }) => {
    const map = useMapEvents({
        moveend: () => {
            if (!isOn) return;
            fetchData();
        }
    });

    const fetchData = () => {
        const bounds = map.getBounds();
        setStatus("Loading surfaces...");
        const noData = includeNoData ? '1' : '0';
        fetch(`http://127.0.0.1:5001/debug/surfaces?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}&include_no_data=${noData}`)
            .then(res => res.json())
            .then(data => {
                const segs = Array.isArray(data) ? data : (data && data.segments != null ? data.segments : []);
                const limitReached = !Array.isArray(data) && data && Boolean(data.limit_reached);
                setSegments(Array.isArray(segs) ? segs : []);
                if (typeof setLimitReached === 'function') setLimitReached(limitReached);
                const n = Array.isArray(segs) ? segs.length : 0;
                setStatus(limitReached ? `Surfaces: ${n} segments (20k limit — zoom in for more)` : `Surfaces: ${n} segments`);
            })
            .catch(() => setStatus("Connection Error"));
    };

    useEffect(() => {
        if (isOn) fetchData();
        else { setSegments([]); if (typeof setLimitReached === 'function') setLimitReached(false); }
    }, [isOn, includeNoData]);

    return null;
};

// --- UNLIT LAYER (map event handler) ---
const UnlitLayer = ({ isOn, includeUnknown, setSegments, setLimitReached, setStatus }) => {
    const map = useMapEvents({
        moveend: () => {
            if (!isOn) return;
            fetchData();
        }
    });

    const fetchData = () => {
        const bounds = map.getBounds();
        setStatus("Loading unlit...");
        const inc = includeUnknown ? '1' : '0';
        fetch(`http://127.0.0.1:5001/debug/unlit?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}&include_unknown=${inc}`)
            .then(res => res.json())
            .then(data => {
                const segs = Array.isArray(data) ? data : (data && data.segments != null ? data.segments : []);
                setSegments(Array.isArray(segs) ? segs : []);
                if (typeof setLimitReached === 'function') setLimitReached(Boolean(data && data.limit_reached));
                const n = Array.isArray(segs) ? segs.length : 0;
                setStatus(data && data.limit_reached ? `Unlit: ${n} segments (20k limit)` : `Unlit: ${n} segments`);
            })
            .catch(() => setStatus("Connection Error"));
    };

    useEffect(() => {
        if (isOn) fetchData();
        else { setSegments([]); if (typeof setLimitReached === 'function') setLimitReached(false); }
    }, [isOn, includeUnknown]);

    return null;
};

const CYCLEWAY_LAYER_COLORS = { general: '#2E7D32', segregated: '#66BB6A' };

// --- CYCLEWAY LAYER ---
const CyclewayLayer = ({ isOn, layers, setSegmentsByLayer, setStatus }) => {
    const map = useMapEvents({
        moveend: () => {
            if (!isOn) return;
            fetchAll();
        }
    });

    const fetchAll = () => {
        const bounds = map.getBounds();
        const q = `min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}`;
        setStatus("Loading cycleway...");
        const order = ['general', 'segregated'];
        const active = order.filter(l => layers[l]);
        if (active.length === 0) {
            setSegmentsByLayer({});
            setStatus("Cycleway: 0 segments");
            return;
        }
        Promise.all(active.map(layer =>
            fetch(`http://127.0.0.1:5001/debug/cycleway?${q}&layer=${layer}`).then(r => r.json())
        )).then(results => {
            const out = {};
            let total = 0;
            active.forEach((layer, i) => {
                const d = results[i];
                const segs = (d && d.segments) ? d.segments : [];
                out[layer] = segs;
                total += segs.length;
            });
            setSegmentsByLayer(out);
            setStatus(`Cycleway: ${total} segments`);
        }).catch(() => setStatus("Connection Error"));
    };

    useEffect(() => {
        if (isOn) fetchAll();
        else setSegmentsByLayer({});
    }, [isOn, layers.general, layers.segregated]);

    return null;
};

// --- HGV BANNED LAYER ---
const HgvBannedLayer = ({ isOn, setSegments, setStatus }) => {
    const map = useMapEvents({
        moveend: () => {
            if (!isOn) return;
            fetchData();
        }
    });

    const fetchData = () => {
        const bounds = map.getBounds();
        setStatus("Loading HGV banned...");
        fetch(`http://127.0.0.1:5001/debug/hgv_banned?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}`)
            .then(res => res.json())
            .then(data => {
                const segs = (data && data.segments) ? data.segments : [];
                setSegments(segs);
                setStatus(`HGV banned: ${segs.length} segments`);
            })
            .catch(() => setStatus("Connection Error"));
    };

    useEffect(() => {
        if (isOn) fetchData();
        else setSegments([]);
    }, [isOn]);

    return null;
};

// --- GRAPH NETWORK (all physical edges; 15k centre cap) ---
const GRAPH_NETWORK_TYPE_COLORS = {
    // Cycling / pedestrian
    cycleway: '#1976D2',
    footway: '#7B1FA2',
    path: '#7B1FA2',
    pedestrian: '#7B1FA2',
    steps: '#7B1FA2',
    bridleway: '#6A1B9A',
    // Roads
    primary: '#D32F2F',
    secondary: '#F57C00',
    tertiary: '#FBC02D',
    trunk: '#424242',
    motorway: '#212121',
    residential: '#2E7D32',
    living_street: '#388E3C',
    unclassified: '#33691E',
    service: '#5D4037',
    track: '#8D6E63',
};
const getGraphNetworkColor = (highwayType) => {
    const key = String(highwayType || '').toLowerCase();
    return GRAPH_NETWORK_TYPE_COLORS[key] || '#9E9E9E';
};

const GraphNetworkLayer = ({ isOn, setSegments, setLimitReached, setStatus }) => {
    const map = useMapEvents({
        moveend: () => {
            if (!isOn) return;
            fetchData();
        }
    });

    const fetchData = () => {
        const bounds = map.getBounds();
        setStatus("Loading graph network...");
        fetch(`http://127.0.0.1:5001/debug/graph_network?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}`)
            .then(res => res.json())
            .then(data => {
                const segs = (data && data.segments) ? data.segments : [];
                setSegments(Array.isArray(segs) ? segs : []);
                if (typeof setLimitReached === 'function') setLimitReached(Boolean(data && data.limit_reached));
                const n = Array.isArray(segs) ? segs.length : 0;
                setStatus(data && data.limit_reached ? `Graph network: ${n} segments (15k limit — zoom in)` : `Graph network: ${n} segments`);
            })
            .catch(() => setStatus("Connection Error"));
    };

    useEffect(() => {
        if (isOn) fetchData();
        else { setSegments([]); if (typeof setLimitReached === 'function') setLimitReached(false); }
    }, [isOn]);

    return null;
};

// TfL programme -> color (cycleway, quietway, superhighway)
const TFL_PROGRAMME_COLORS = { cycleway: '#2E7D32', quietway: '#1565C0', superhighway: '#E65100' };
const getTflProgrammeColor = (programme) => TFL_PROGRAMME_COLORS[String(programme).toLowerCase()] || '#757575';

// --- TfL ROUTES LAYER ---
const TflRoutesLayer = ({ isOn, setSegments, setStatus }) => {
    const map = useMapEvents({
        moveend: () => {
            if (!isOn) return;
            fetchData();
        }
    });

    const fetchData = () => {
        const bounds = map.getBounds();
        setStatus("Loading TfL routes...");
        fetch(`http://127.0.0.1:5001/debug/tfl_routes?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}`)
            .then(res => res.json())
            .then(data => {
                const segs = (data && data.segments) ? data.segments : [];
                setSegments(segs);
                setStatus(`TfL routes: ${segs.length} segments`);
            })
            .catch(() => setStatus("Connection Error"));
    };

    useEffect(() => {
        if (isOn) fetchData();
        else setSegments([]);
    }, [isOn]);

    return null;
};

// --- ATTRACTION EDGES (is_park / is_river / is_sight) ---
const AttractionsLayer = ({ isOn, layers, parkHoursOn, setSegmentsByKind, setLimitReached, setStatus }) => {
    const map = useMapEvents({
        moveend: () => {
            if (!isOn) return;
            fetchAll();
        }
    });

    const fetchAll = () => {
        const bounds = map.getBounds();
        const q = `min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}`;
        setStatus("Loading attraction edges...");
        const order = ['park', 'river', 'sight'];
        const active = order.filter(k => layers[k]);
        if (active.length === 0) {
            setSegmentsByKind({});
            if (typeof setLimitReached === 'function') setLimitReached(false);
            setStatus("Attraction edges: 0 segments");
            return;
        }
        Promise.all(active.map(kind => {
            const parkHoursParam = (kind === 'park' && parkHoursOn) ? '&park_hours=1' : '';
            return fetch(`http://127.0.0.1:5001/debug/attractions?${q}&layer=${kind}${parkHoursParam}`).then(r => r.json());
        })).then(results => {
            const out = {};
            let total = 0;
            let openCount = 0;
            let closedCount = 0;
            let limitReached = false;
            let parkHoursAt = null;
            active.forEach((kind, i) => {
                const d = results[i];
                const segs = (d && d.segments) ? d.segments : [];
                out[kind] = segs;
                total += segs.length;
                if (d && d.limit_reached) limitReached = true;
                if (kind === 'park' && parkHoursOn) {
                    if (d && d.park_hours_at) parkHoursAt = d.park_hours_at;
                    segs.forEach((seg) => {
                        if (seg.park_open) openCount += 1;
                        else closedCount += 1;
                    });
                }
            });
            setSegmentsByKind(out);
            if (typeof setLimitReached === 'function') setLimitReached(limitReached);
            if (parkHoursOn && layers.park) {
                const atNote = parkHoursAt ? ` @ ${parkHoursAt}` : '';
                setStatus(
                    limitReached
                        ? `Park hours: ${openCount} open, ${closedCount} closed${atNote} (20k limit)`
                        : `Park hours: ${openCount} open, ${closedCount} closed${atNote}`
                );
            } else {
                setStatus(limitReached ? `Attraction edges: ${total} (20k limit)` : `Attraction edges: ${total}`);
            }
        }).catch(() => setStatus("Connection Error"));
    };

    useEffect(() => {
        if (isOn) fetchAll();
        else {
            setSegmentsByKind({});
            if (typeof setLimitReached === 'function') setLimitReached(false);
        }
    }, [isOn, layers.park, layers.river, layers.sight, parkHoursOn]);

    return null;
};

// --- TfL LIVE DISRUPTIONS LAYER ---
const TflDisruptionsLayer = ({ isOn, setSegments, setStatus }) => {
    const map = useMapEvents({
        moveend: () => {
            if (!isOn) return;
            fetchData();
        }
    });

    const fetchData = () => {
        const bounds = map.getBounds();
        setStatus("Loading TfL disruptions...");
        fetch(`http://127.0.0.1:5001/debug/tfl_disruptions?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}`)
            .then(res => res.json())
            .then(data => {
                const segs = (data && data.segments) ? data.segments : [];
                setSegments(segs);
                setStatus(`TfL disruptions: ${segs.length} segments`);
            })
            .catch(() => setStatus("Connection Error"));
    };

    useEffect(() => {
        if (isOn) fetchData();
        else setSegments([]);
    }, [isOn]);

    return null;
};

// --- TfL LIVE DISRUPTIONS RAW (ground truth) LAYER ---
const TflDisruptionsRawLayer = ({ isOn, setPoints, setLines, setPolygons, setStatus }) => {
    const map = useMapEvents({
        moveend: () => {
            if (!isOn) return;
            fetchData();
        }
    });

    const fetchData = () => {
        const bounds = map.getBounds();
        setStatus("Loading TfL ground truth...");
        fetch(`http://127.0.0.1:5001/debug/tfl_disruptions_raw?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}`)
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    setPoints([]); setLines([]); setPolygons([]);
                    setStatus("Error: " + data.error);
                    return;
                }
                setPoints(data.points || []);
                setLines(data.lines || []);
                setPolygons(data.polygons || []);
                const n = (data.points || []).length + (data.lines || []).length + (data.polygons || []).length;
                setStatus(`TfL ground truth: ${n} features`);
            })
            .catch(() => { setPoints([]); setLines([]); setPolygons([]); setStatus("Connection Error"); });
    };

    useEffect(() => {
        if (isOn) fetchData();
        else { setPoints([]); setLines([]); setPolygons([]); }
    }, [isOn]);

    return null;
};

// --- TomTom LIVE DISRUPTIONS LAYER ---
const TomtomDisruptionsLayer = ({ isOn, setSegments, setStatus }) => {
    const map = useMapEvents({
        moveend: () => {
            if (!isOn) return;
            fetchData();
        }
    });

    const fetchData = () => {
        const bounds = map.getBounds();
        setStatus("Loading TomTom disruptions...");
        fetch(`http://127.0.0.1:5001/debug/tomtom_disruptions?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}`)
            .then(res => res.json())
            .then(data => {
                const segs = (data && data.segments) ? data.segments : [];
                setSegments(segs);
                setStatus(`TomTom: ${segs.length} segments`);
            })
            .catch(() => setStatus("Connection Error"));
    };

    useEffect(() => {
        if (isOn) fetchData();
        else setSegments([]);
    }, [isOn]);

    return null;
};

// --- TRAFFIC CALMING POINTS LAYER ---
const TrafficCalmingPointsLayer = ({ isOn, source, setPoints, setStatus }) => {
    const map = useMapEvents({
        moveend: () => {
            if (!isOn) return;
            fetchData();
        }
    });

    const fetchData = () => {
        const bounds = map.getBounds();
        const src = (source && ['way', 'point', 'both'].includes(source)) ? source : 'way';
        setStatus("Loading traffic calming...");
        fetch(`http://127.0.0.1:5001/debug/traffic_calming_points?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}&source=${encodeURIComponent(src)}`)
            .then(res => res.json())
            .then(data => {
                setPoints(Array.isArray(data) ? data : []);
                setStatus(`Traffic calming: ${Array.isArray(data) ? data.length : 0} points`);
            })
            .catch(() => setStatus("Connection Error"));
    };

    useEffect(() => {
        if (isOn) fetchData();
        else setPoints([]);
    }, [isOn, source]);

    return null;
};

// --- JUNCTION POINTS LAYER ---
const JunctionPointsLayer = ({ isOn, setPoints, setStatus }) => {
    const map = useMapEvents({
        moveend: () => {
            if (!isOn) return;
            fetchData();
        }
    });

    const fetchData = () => {
        const bounds = map.getBounds();
        setStatus("Loading junctions...");
        fetch(`http://127.0.0.1:5001/debug/junction_points?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}`)
            .then(res => res.json())
            .then(data => {
                setPoints(Array.isArray(data) ? data : []);
                setStatus(`Junctions: ${Array.isArray(data) ? data.length : 0} points`);
            })
            .catch(() => setStatus("Connection Error"));
    };

    useEffect(() => {
        if (isOn) fetchData();
        else setPoints([]);
    }, [isOn]);

    return null;
};

// --- NODE POINTS LAYER (generic) ---
const NodePointsLayer = ({ isOn, endpoint, statusLabel, setPoints, setStatus }) => {
    const map = useMapEvents({
        moveend: () => {
            if (!isOn) return;
            fetchData();
        }
    });

    const fetchData = () => {
        const bounds = map.getBounds();
        setStatus(`Loading ${statusLabel}...`);
        fetch(`http://127.0.0.1:5001/debug/${endpoint}?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}`)
            .then(res => res.json())
            .then(data => {
                setPoints(Array.isArray(data) ? data : []);
                setStatus(`${statusLabel}: ${Array.isArray(data) ? data.length : 0} points`);
            })
            .catch(() => setStatus("Connection Error"));
    };

    useEffect(() => {
        if (isOn) fetchData();
        else setPoints([]);
    }, [isOn]);

    return null;
};

// --- POINT POPUP (left-click on point-based overlay) ---
const PointPopup = ({ position, type, source, dataSource, details, onClose }) => {
    if (!position) return null;
    const isAccident = source === 'accident';
    let showText = !isAccident && type != null && String(type).trim() !== '';
    let text = showText ? type : null;
    if (source === 'barrier' && details && (details.barrier_confidence != null || details.barrier)) {
        const parts = [details.barrier || type].filter(Boolean);
        if (details.barrier_cluster_label) parts.push(`[${details.barrier_cluster_label}]`);
        if (details.barrier_confidence != null) parts.push(`conf: ${Number(details.barrier_confidence).toFixed(2)}`);
        text = parts.join(' ');
    }
    if (isAccident && !text) return null; // accidents: leave blank
    return (
        <div
            style={{
                position: 'absolute',
                left: position.x,
                top: position.y,
                background: 'white',
                padding: '6px 10px',
                borderRadius: '6px',
                boxShadow: '0 2px 10px rgba(0,0,0,0.3)',
                zIndex: 2001,
                fontSize: '12px',
                fontWeight: '500',
                pointerEvents: 'auto',
                border: '1px solid #ddd',
            }}
            onClick={(ev) => { ev.stopPropagation(); onClose(); }}
        >
            {text}
        </div>
    );
};

// --- MAP EVENTS (inspector right-click, point left-click) ---
const CLICK_RADIUS_DEG = 0.00025; // ~25m at London
function findNearestPoint(lat, lon, points, getLatLon) {
    let best = null, bestD = CLICK_RADIUS_DEG * CLICK_RADIUS_DEG;
    for (let i = 0; i < points.length; i++) {
        const p = points[i];
        const plat = getLatLon(p)[0], plon = getLatLon(p)[1];
        const d = (plat - lat) ** 2 + (plon - lon) ** 2;
        if (d < bestD) { bestD = d; best = p; }
    }
    return best;
}

const MapEvents = ({
    inspectorData, setInspectorData, setInspectorGeo, setInspectorPos,
    pointPopup, setPointPopup,
    tflDisruptionsOn,
    tflDisruptionDetail, setTflDisruptionDetail,
    tomtomDisruptionsOn,
    tomtomDisruptionDetail, setTomtomDisruptionDetail,
    accidentsOn, accidents,
    junctionOn, junctionPoints,
    barriersOn, barrierPoints,
    trafficSignalsOn, trafficSignalsPoints,
    miniRoundaboutOn, miniRoundaboutPoints,
    crossingOn, crossingPoints,
    giveWayOn, giveWayPoints,
    stopOn, stopPoints,
    modifyTflOn,
    modifyTflProgramme,
    setTflEditsAdded,
    setTflEditsRemoved,
    pushTflSessionUndo,
    modifyAttractionOn,
    attractionType,
    setAttractionScratchPoints,
    attractionName,
    onAttractionSightClick,
    onAttractionScratchClick,
}) => {
    const map = useMapEvents({
        click(e) {
            if (modifyAttractionOn) {
                setPointPopup(null);
                setTflDisruptionDetail(null);
                setTomtomDisruptionDetail(null);
                const lat = e.latlng.lat;
                const lon = e.latlng.lng;
                if (attractionType === 'sight') {
                    if (onAttractionSightClick) onAttractionSightClick(lat, lon);
                } else if (onAttractionScratchClick) {
                    onAttractionScratchClick(lat, lon);
                }
                return;
            }
            if (modifyTflOn) {
                setPointPopup(null);
                setTflDisruptionDetail(null);
                setTomtomDisruptionDetail(null);
                const lat = e.latlng.lat, lon = e.latlng.lng;
                fetch('http://127.0.0.1:5001/modify/tfl_add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lat, lon, programme: modifyTflProgramme }),
                })
                    .then((r) => r.json())
                    .then((d) => {
                        if (d.error) return;
                        setTflEditsAdded((prev) => [...prev, { source: d.source, target: d.target, programme: d.programme, route: d.route, geometry: d.geometry }]);
                        if (pushTflSessionUndo) pushTflSessionUndo({ type: 'add', source: d.source, target: d.target, programme: d.programme, route: d.route });
                    });
                return;
            }
            if (inspectorData) {
                setInspectorData(null);
                setInspectorGeo(null);
            }
            setPointPopup(null);
            const lat = e.latlng.lat, lon = e.latlng.lng;
            // Left-click on TfL disruption (zone, line, or point with slightly larger margin): show full TfL payload
            if (tflDisruptionsOn) {
                fetch(`http://127.0.0.1:5001/debug/tfl_disruption_at?lat=${lat}&lon=${lon}&tolerance=0.00025`)
                    .then((r) => r.json())
                    .then((data) => {
                        if (data.disruptions && data.disruptions.length > 0) {
                            setTflDisruptionDetail({
                                disruptions: data.disruptions,
                                position: { x: e.originalEvent.clientX, y: e.originalEvent.clientY },
                            });
                            setPointPopup(null);
                        } else {
                            setTflDisruptionDetail(null);
                        }
                    })
                    .catch(() => setTflDisruptionDetail(null));
            }
            if (tomtomDisruptionsOn) {
                fetch(`http://127.0.0.1:5001/debug/tomtom_disruption_at?lat=${lat}&lon=${lon}&tolerance=0.00025`)
                    .then((r) => r.json())
                    .then((data) => {
                        if (data.disruptions && data.disruptions.length > 0) {
                            setTomtomDisruptionDetail({
                                disruptions: data.disruptions,
                                position: { x: e.originalEvent.clientX, y: e.originalEvent.clientY },
                            });
                            setPointPopup(null);
                        } else {
                            setTomtomDisruptionDetail(null);
                        }
                    })
                    .catch(() => setTomtomDisruptionDetail(null));
            }
            const candidates = [];
            if (junctionOn && Array.isArray(junctionPoints)?.length) {
                const p = findNearestPoint(lat, lon, junctionPoints, x => [x.lat, x.lon]);
                if (p) candidates.push({ dist: (p.lat - lat) ** 2 + (p.lon - lon) ** 2, type: p.type, source: 'junction', pos: e.originalEvent });
            }
            if (barriersOn && Array.isArray(barrierPoints)?.length) {
                const p = findNearestPoint(lat, lon, barrierPoints, x => [x.lat, x.lon]);
                if (p) candidates.push({ dist: (p.lat - lat) ** 2 + (p.lon - lon) ** 2, type: p.type || (p.details && p.details.barrier) || 'barrier', source: 'barrier', details: p.details, pos: e.originalEvent });
            }
            if (trafficSignalsOn && Array.isArray(trafficSignalsPoints)?.length) {
                const p = findNearestPoint(lat, lon, trafficSignalsPoints, x => [x.lat, x.lon]);
                if (p) candidates.push({ dist: (p.lat - lat) ** 2 + (p.lon - lon) ** 2, type: 'Traffic signals', source: 'node', pos: e.originalEvent });
            }
            if (miniRoundaboutOn && Array.isArray(miniRoundaboutPoints)?.length) {
                const p = findNearestPoint(lat, lon, miniRoundaboutPoints, x => [x.lat, x.lon]);
                if (p) candidates.push({ dist: (p.lat - lat) ** 2 + (p.lon - lon) ** 2, type: 'Mini roundabout', source: 'node', pos: e.originalEvent });
            }
            if (crossingOn && Array.isArray(crossingPoints)?.length) {
                const p = findNearestPoint(lat, lon, crossingPoints, x => [x.lat, x.lon]);
                if (p) candidates.push({ dist: (p.lat - lat) ** 2 + (p.lon - lon) ** 2, type: 'Crossing', source: 'node', pos: e.originalEvent });
            }
            if (giveWayOn && Array.isArray(giveWayPoints)?.length) {
                const p = findNearestPoint(lat, lon, giveWayPoints, x => [x.lat, x.lon]);
                if (p) candidates.push({ dist: (p.lat - lat) ** 2 + (p.lon - lon) ** 2, type: 'Give way', source: 'node', pos: e.originalEvent });
            }
            if (stopOn && Array.isArray(stopPoints)?.length) {
                const p = findNearestPoint(lat, lon, stopPoints, x => [x.lat, x.lon]);
                if (p) candidates.push({ dist: (p.lat - lat) ** 2 + (p.lon - lon) ** 2, type: 'Stop', source: 'node', pos: e.originalEvent });
            }
            if (accidentsOn && Array.isArray(accidents)?.length) {
                const nearest = findNearestPoint(lat, lon, accidents, a => [a[0], a[1]]);
                if (nearest) {
                    const d = (nearest[0] - lat) ** 2 + (nearest[1] - lon) ** 2;
                    candidates.push({ dist: d, type: '', source: 'accident', pos: e.originalEvent });
                }
            }
            if (candidates.length) {
                candidates.sort((a, b) => a.dist - b.dist);
                const c = candidates[0];
                setPointPopup({ x: c.pos.clientX, y: c.pos.clientY, type: c.type, source: c.source, dataSource: c.dataSource, details: c.details });
            }
        },
        contextmenu(e) {
            e.originalEvent.preventDefault();
            setPointPopup(null);
            if (setTflDisruptionDetail) setTflDisruptionDetail(null);
            if (setTomtomDisruptionDetail) setTomtomDisruptionDetail(null);
            if (modifyAttractionOn) {
                return;
            }
            if (modifyTflOn) {
                const lat = e.latlng.lat, lon = e.latlng.lng;
                fetch('http://127.0.0.1:5001/modify/tfl_remove', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lat, lon }),
                })
                    .then((r) => r.json())
                    .then((d) => {
                        if (d.error) return;
                        setTflEditsRemoved((prev) => [...prev, { source: d.source, target: d.target, geometry: d.geometry }]);
                        if (pushTflSessionUndo) pushTflSessionUndo({ type: 'remove', source: d.source, target: d.target });
                        if (pushTflSessionUndo) pushTflSessionUndo({ type: 'remove', source: d.source, target: d.target });
                    });
                return;
            }
            fetch(`http://127.0.0.1:5001/inspect?lat=${e.latlng.lat}&lon=${e.latlng.lng}`)
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
};

// --- MAIN APP ---
function App() {
    const [heatmapOn, setHeatmapOn] = useState(false);
    const [heatmapSegments, setHeatmapSegments] = useState([]);
    const [accidentsOn, setAccidentsOn] = useState(false);
    const [accidents, setAccidents] = useState([]);
    const [surfacesOn, setSurfacesOn] = useState(false);
    const [surfaceNoDataOn, setSurfaceNoDataOn] = useState(true);
    const [surfaceLimitReached, setSurfaceLimitReached] = useState(false);
    const [surfaceSegments, setSurfaceSegments] = useState([]);
    const [unlitOn, setUnlitOn] = useState(false);
    const [unlitNoDataOn, setUnlitNoDataOn] = useState(true);
    const [unlitLimitReached, setUnlitLimitReached] = useState(false);
    const [unlitSegments, setUnlitSegments] = useState([]);
    const [cyclewayOn, setCyclewayOn] = useState(false);
    const [cyclewayGeneralOn, setCyclewayGeneralOn] = useState(true);
    const [cyclewaySegregatedOn, setCyclewaySegregatedOn] = useState(false);
    const [cyclewaySegmentsByLayer, setCyclewaySegmentsByLayer] = useState({});
    const [hgvBannedOn, setHgvBannedOn] = useState(false);
    const [hgvBannedSegments, setHgvBannedSegments] = useState([]);
    const [graphNetworkOn, setGraphNetworkOn] = useState(false);
    const [graphNetworkLimitReached, setGraphNetworkLimitReached] = useState(false);
    const [graphNetworkSegments, setGraphNetworkSegments] = useState([]);
    const [tflRoutesOn, setTflRoutesOn] = useState(false);
    const [tflRoutesSegments, setTflRoutesSegments] = useState([]);
    const [attractionsOn, setAttractionsOn] = useState(false);
    const [attractionParkOn, setAttractionParkOn] = useState(true);
    const [attractionRiverOn, setAttractionRiverOn] = useState(true);
    const [attractionSightOn, setAttractionSightOn] = useState(true);
    const [attractionParkHoursOn, setAttractionParkHoursOn] = useState(false);
    const [attractionLimitReached, setAttractionLimitReached] = useState(false);
    const [attractionSegmentsByKind, setAttractionSegmentsByKind] = useState({});
    const [tflDisruptionsOn, setTflDisruptionsOn] = useState(false);
    const [tflDisruptionSegments, setTflDisruptionSegments] = useState([]);
    const [tflDisruptionStatus, setTflDisruptionStatus] = useState('');
    const [tomtomDisruptionsOn, setTomtomDisruptionsOn] = useState(false);
    const [tomtomDisruptionSegments, setTomtomDisruptionSegments] = useState([]);
    const [tomtomDisruptionStatus, setTomtomDisruptionStatus] = useState('');
    const [tflGroundTruthOn, setTflGroundTruthOn] = useState(false);
    const [tflDisruptionDetail, setTflDisruptionDetail] = useState(null); // { disruptions: [...], position: { x, y } } when left-click on disruption
    const [tomtomDisruptionDetail, setTomtomDisruptionDetail] = useState(null); // same for TomTom left-click
    const [tflRawPoints, setTflRawPoints] = useState([]);
    const [tflRawLines, setTflRawLines] = useState([]);
    const [tflRawPolygons, setTflRawPolygons] = useState([]);
    const [trafficCalmingOn, setTrafficCalmingOn] = useState(false);
    const [trafficCalmingPoints, setTrafficCalmingPoints] = useState([]);
    const [calmingSource, setCalmingSource] = useState('way'); // 'way' | 'point' | 'both'
    const [junctionOn, setJunctionOn] = useState(false);
    const [junctionPoints, setJunctionPoints] = useState([]);
    const [barriersOn, setBarriersOn] = useState(false);
    const [barrierPoints, setBarrierPoints] = useState([]);
    const [trafficSignalsOn, setTrafficSignalsOn] = useState(false);
    const [trafficSignalsPoints, setTrafficSignalsPoints] = useState([]);
    const [miniRoundaboutOn, setMiniRoundaboutOn] = useState(false);
    const [miniRoundaboutPoints, setMiniRoundaboutPoints] = useState([]);
    const [crossingOn, setCrossingOn] = useState(false);
    const [crossingPoints, setCrossingPoints] = useState([]);
    const [giveWayOn, setGiveWayOn] = useState(false);
    const [giveWayPoints, setGiveWayPoints] = useState([]);
    const [stopOn, setStopOn] = useState(false);
    const [stopPoints, setStopPoints] = useState([]);
    const [status, setStatus] = useState("Debug Mode Ready");
    const [pointPopup, setPointPopup] = useState(null);

    // Inspector State
    const [inspectorData, setInspectorData] = useState(null);
    const [inspectorPos, setInspectorPos] = useState(null);
    const [inspectorGeo, setInspectorGeo] = useState(null);

    // Modify suite: manual TfL edits (bottom-left)
    const [modifyTflOn, setModifyTflOn] = useState(false);
    const [modifyTflProgramme, setModifyTflProgramme] = useState('cycleway');
    const [tflEditsAdded, setTflEditsAdded] = useState([]);
    const [tflEditsRemoved, setTflEditsRemoved] = useState([]);
    // Undo only for current session (since mode was turned on): stack of { type: 'add'|'remove', ... }
    const [tflSessionUndoStack, setTflSessionUndoStack] = useState([]);

    const [modifyAttractionOn, setModifyAttractionOn] = useState(false);
    const [attractionType, setAttractionType] = useState('park');
    const [attractionName, setAttractionName] = useState('');
    const [attractionScratchPoints, setAttractionScratchPoints] = useState([]);
    const [attractionManualRegions, setAttractionManualRegions] = useState([]);
    const [osmParkPolygons, setOsmParkPolygons] = useState([]);
    const [attractionScratchZonePositions, setAttractionScratchZonePositions] = useState([]);
    const [attractionSessionUndoStack, setAttractionSessionUndoStack] = useState([]);

    const setModifyTflOnExclusive = (on) => {
        if (on) setModifyAttractionOn(false);
        setModifyTflOn(on);
    };
    const setModifyAttractionOnExclusive = (on) => {
        if (on) setModifyTflOn(false);
        setModifyAttractionOn(on);
    };

    const getSegmentColor = (grade) => {
        if (grade >= 0.40) return '#800080';
        if (grade > 0.075) return '#FF0000';
        if (grade > 0.033) return '#FFD700';
        return null;
    };

    // Fetch accidents when toggle is turned on
    useEffect(() => {
        if (accidentsOn && accidents.length === 0) {
            setStatus("Loading accidents...");
            fetch('http://127.0.0.1:5001/accidents')
                .then(res => res.json())
                .then(data => {
                    if (Array.isArray(data)) {
                        setAccidents(data);
                        setStatus(`Loaded ${data.length} accidents`);
                    }
                })
                .catch(() => setStatus("Error loading accidents"));
        }
    }, [accidentsOn]);

    // Reset modify overlays and session undo stack when activating or deactivating
    useEffect(() => {
        if (modifyTflOn) {
            setTflEditsAdded([]);
            setTflEditsRemoved([]);
            setTflSessionUndoStack([]);
            setStatus('Modify TfL: left click add, right click remove');
        } else {
            setTflEditsAdded([]);
            setTflEditsRemoved([]);
            setTflSessionUndoStack([]);
        }
    }, [modifyTflOn]);

    useEffect(() => {
        if (modifyAttractionOn || attractionsOn) {
            fetch('http://127.0.0.1:5001/modify/attraction_regions')
                .then((r) => r.json())
                .then((d) => setAttractionManualRegions(d.regions || []))
                .catch(() => setAttractionManualRegions([]));
        } else {
            setAttractionManualRegions([]);
        }
        if (modifyAttractionOn) {
            setAttractionScratchPoints([]);
            setAttractionSessionUndoStack([]);
            setAttractionScratchZonePositions([]);
            setStatus('Modify attractions: park/river = draw polygon (≥3 clicks), Complete; sight = one click');
            fetch('http://127.0.0.1:5001/modify/osm_park_polygons')
                .then((r) => r.json())
                .then((d) => setOsmParkPolygons(d.polygons || []))
                .catch(() => setOsmParkPolygons([]));
        } else {
            setAttractionScratchPoints([]);
            setAttractionSessionUndoStack([]);
            setAttractionScratchZonePositions([]);
            setOsmParkPolygons([]);
        }
    }, [modifyAttractionOn, attractionsOn]);

    useEffect(() => {
        if (!modifyAttractionOn) {
            setAttractionScratchZonePositions([]);
            return;
        }
        const pts = attractionScratchPoints;
        if ((attractionType === 'park' || attractionType === 'river') && pts.length >= 3) {
            setAttractionScratchZonePositions([[...pts, pts[0]]]);
            return;
        }
        setAttractionScratchZonePositions([]);
    }, [modifyAttractionOn, attractionType, attractionScratchPoints]);

    useEffect(() => {
        if (!modifyAttractionOn) return;
        setAttractionScratchPoints([]);
    }, [attractionType, modifyAttractionOn]);

    const postAttractionRegion = (body) => {
        fetch('http://127.0.0.1:5001/modify/attraction_add_region', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        })
            .then((r) => r.json())
            .then((d) => {
                if (d.error) return;
                const reg = d.region;
                if (reg) {
                    setAttractionManualRegions((prev) => [...prev, reg]);
                    if (reg.id) setAttractionSessionUndoStack((prev) => [...prev, { type: 'add', id: reg.id }]);
                }
                setAttractionScratchPoints([]);
            });
    };

    const handleAttractionSightClick = (lat, lon) => {
        postAttractionRegion({
            type: 'sight',
            name: attractionName,
            radius_m: 200,
            geometry: { type: 'Point', coordinates: [lon, lat] },
        });
    };

    const handleAttractionScratchClick = (lat, lon) => {
        setAttractionScratchPoints((prev) => [...prev, [lat, lon]]);
    };

    const handleAttractionCompleteGeometry = () => {
        const pts = attractionScratchPoints;
        if (attractionType !== 'park' && attractionType !== 'river') return;
        if (pts.length < 3) return;
        const ring = pts.map(([la, lo]) => [lo, la]);
        if (ring[0][0] !== ring[ring.length - 1][0] || ring[0][1] !== ring[ring.length - 1][1]) {
            ring.push(ring[0]);
        }
        postAttractionRegion({
            type: attractionType,
            name: attractionName,
            geometry: { type: 'Polygon', coordinates: [ring] },
        });
    };

    const handleAttractionUndo = () => {
        if (attractionSessionUndoStack.length === 0) return;
        const last = attractionSessionUndoStack[attractionSessionUndoStack.length - 1];
        setAttractionSessionUndoStack((prev) => prev.slice(0, -1));
        if (last.type === 'add' && last.id) {
            setAttractionManualRegions((prev) => prev.filter((r) => r.id !== last.id));
        }
        fetch('http://127.0.0.1:5001/modify/attraction_undo', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
            .then((r) => r.json())
            .then((d) => {
                if (d.regions) setAttractionManualRegions(d.regions);
            })
            .catch(() => {});
    };

    // Undo: only for current session; pop from session stack, update overlay, then call backend so file stays in sync
    const handleTflUndo = () => {
        if (tflSessionUndoStack.length === 0) return;
        const last = tflSessionUndoStack[tflSessionUndoStack.length - 1];
        if (last.type === 'add') {
            setTflEditsAdded((prev) => prev.filter((s) => !(s.source === last.source && s.target === last.target && s.programme === last.programme && s.route === last.route)));
        } else {
            setTflEditsRemoved((prev) => prev.filter((s) => !(s.source === last.source && s.target === last.target)));
        }
        setTflSessionUndoStack((prev) => prev.slice(0, -1));
        fetch('http://127.0.0.1:5001/modify/tfl_undo', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
            .catch(() => {});
    };

    const handleRefreshTfl = () => {
        setTflDisruptionStatus('Fetching...');
        fetch('http://127.0.0.1:5001/admin/update_tfl', { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                if (d.ok) {
                    setTflDisruptionStatus(`${d.count} disruptions matched`);
                } else {
                    setTflDisruptionStatus(`Error: ${d.message}`);
                }
            })
            .catch(() => setTflDisruptionStatus('Connection error'));
    };

    const handleRefreshTomtom = () => {
        setTomtomDisruptionStatus('Fetching...');
        fetch('http://127.0.0.1:5001/admin/update_tomtom', { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                if (d.ok) {
                    setTomtomDisruptionStatus(`${d.count} incidents matched`);
                } else {
                    setTomtomDisruptionStatus(`Error: ${d.message}`);
                }
            })
            .catch(() => setTomtomDisruptionStatus('Connection error'));
    };

    // Ctrl+Z / Cmd+Z to undo last modify TfL action (current session only)
    useEffect(() => {
        if (!modifyTflOn) return;
        const handler = (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
                e.preventDefault();
                if (tflSessionUndoStack.length > 0) handleTflUndo();
            }
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, [modifyTflOn, tflSessionUndoStack.length]);

    useEffect(() => {
        if (!modifyAttractionOn) return;
        const handler = (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
                e.preventDefault();
                if (attractionSessionUndoStack.length > 0) handleAttractionUndo();
            }
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, [modifyAttractionOn, attractionSessionUndoStack.length]);

    const modifySuiteActive = modifyTflOn || modifyAttractionOn;
    const anyOverlayOn = heatmapOn || accidentsOn || surfacesOn || unlitOn || cyclewayOn || hgvBannedOn || graphNetworkOn || tflRoutesOn || attractionsOn || tflDisruptionsOn || tomtomDisruptionsOn || trafficCalmingOn || junctionOn ||
        barriersOn || trafficSignalsOn || miniRoundaboutOn || crossingOn || giveWayOn || stopOn || modifySuiteActive;
    const tileFilter = anyOverlayOn ? 'grayscale(100%) contrast(90%) brightness(110%)' : 'none';

    return (
        <div style={{ height: "100vh", position: "relative", fontFamily: "Segoe UI, Arial, sans-serif" }}>
            <style>{`.leaflet-tile { filter: ${tileFilter} !important; }`}</style>

            {/* HEADER */}
            <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: "40px", background: "#444", color: "white", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
                <span style={{ fontWeight: "bold" }}>London Cycle Maps // DEBUGGER</span>
                <span style={{ marginLeft: "15px", fontSize: "12px", color: "#ccc" }}>| {status}</span>
            </div>

            {/* DEBUG PANEL (collapsed when Modify TfL is on) */}
            <DebugPanel
                heatmapOn={heatmapOn} setHeatmapOn={setHeatmapOn}
                accidentsOn={accidentsOn} setAccidentsOn={setAccidentsOn}
                surfacesOn={surfacesOn} setSurfacesOn={setSurfacesOn}
                surfaceNoDataOn={surfaceNoDataOn} setSurfaceNoDataOn={setSurfaceNoDataOn}
                surfaceLimitReached={surfaceLimitReached}
                unlitOn={unlitOn} setUnlitOn={setUnlitOn}
                unlitNoDataOn={unlitNoDataOn} setUnlitNoDataOn={setUnlitNoDataOn}
                unlitLimitReached={unlitLimitReached}
                cyclewayOn={cyclewayOn} setCyclewayOn={setCyclewayOn}
                cyclewayGeneralOn={cyclewayGeneralOn} setCyclewayGeneralOn={setCyclewayGeneralOn}
                cyclewaySegregatedOn={cyclewaySegregatedOn} setCyclewaySegregatedOn={setCyclewaySegregatedOn}
                hgvBannedOn={hgvBannedOn} setHgvBannedOn={setHgvBannedOn}
                graphNetworkOn={graphNetworkOn} setGraphNetworkOn={setGraphNetworkOn}
                graphNetworkLimitReached={graphNetworkLimitReached}
                tflRoutesOn={tflRoutesOn} setTflRoutesOn={setTflRoutesOn}
                attractionsOn={attractionsOn} setAttractionsOn={setAttractionsOn}
                attractionParkOn={attractionParkOn} setAttractionParkOn={setAttractionParkOn}
                attractionRiverOn={attractionRiverOn} setAttractionRiverOn={setAttractionRiverOn}
                attractionSightOn={attractionSightOn} setAttractionSightOn={setAttractionSightOn}
                attractionParkHoursOn={attractionParkHoursOn} setAttractionParkHoursOn={setAttractionParkHoursOn}
                attractionLimitReached={attractionLimitReached}
                tflDisruptionsOn={tflDisruptionsOn} setTflDisruptionsOn={setTflDisruptionsOn}
                onRefreshTfl={handleRefreshTfl} tflDisruptionStatus={tflDisruptionStatus}
                tomtomDisruptionsOn={tomtomDisruptionsOn} setTomtomDisruptionsOn={setTomtomDisruptionsOn}
                onRefreshTomtom={handleRefreshTomtom} tomtomDisruptionStatus={tomtomDisruptionStatus}
                tflGroundTruthOn={tflGroundTruthOn} setTflGroundTruthOn={setTflGroundTruthOn}
                trafficCalmingOn={trafficCalmingOn} setTrafficCalmingOn={setTrafficCalmingOn}
                calmingSource={calmingSource} setCalmingSource={setCalmingSource}
                junctionOn={junctionOn} setJunctionOn={setJunctionOn}
                barriersOn={barriersOn} setBarriersOn={setBarriersOn}
                trafficSignalsOn={trafficSignalsOn} setTrafficSignalsOn={setTrafficSignalsOn}
                miniRoundaboutOn={miniRoundaboutOn} setMiniRoundaboutOn={setMiniRoundaboutOn}
                crossingOn={crossingOn} setCrossingOn={setCrossingOn}
                giveWayOn={giveWayOn} setGiveWayOn={setGiveWayOn}
                stopOn={stopOn} setStopOn={setStopOn}
                forceCollapsed={modifySuiteActive}
            />

            {/* MODIFY SUITE (bottom-left) */}
            <ModifyPanel
                modifyTflOn={modifyTflOn}
                setModifyTflOn={setModifyTflOnExclusive}
                modifyTflProgramme={modifyTflProgramme}
                setModifyTflProgramme={setModifyTflProgramme}
                onUndo={modifyTflOn ? handleTflUndo : undefined}
                canUndo={modifyTflOn && tflSessionUndoStack.length > 0}
            />
            <ModifyAttractionsPanel
                modifyAttractionOn={modifyAttractionOn}
                setModifyAttractionOn={setModifyAttractionOnExclusive}
                attractionType={attractionType}
                setAttractionType={setAttractionType}
                attractionName={attractionName}
                setAttractionName={setAttractionName}
                onCompleteGeometry={handleAttractionCompleteGeometry}
                onUndo={modifyAttractionOn ? handleAttractionUndo : undefined}
                canUndo={modifyAttractionOn && attractionSessionUndoStack.length > 0}
                scratchCount={attractionScratchPoints.length}
            />

            {/* INSPECTOR WINDOW */}
            {inspectorData && inspectorPos && !modifyAttractionOn && (
                <InspectorWindow
                    data={inspectorData}
                    position={inspectorPos}
                    onClose={() => { setInspectorData(null); setInspectorGeo(null); }}
                />
            )}
            {pointPopup && (
                <PointPopup
                    position={{ x: pointPopup.x, y: pointPopup.y }}
                    type={pointPopup.type}
                    source={pointPopup.source}
                    dataSource={pointPopup.dataSource}
                    details={pointPopup.details}
                    onClose={() => setPointPopup(null)}
                />
            )}
            {tflDisruptionDetail && (
                <TflDisruptionDetailWindow
                    disruptions={tflDisruptionDetail.disruptions}
                    position={tflDisruptionDetail.position}
                    onClose={() => setTflDisruptionDetail(null)}
                />
            )}
            {tomtomDisruptionDetail && (
                <TomtomDisruptionDetailWindow
                    disruptions={tomtomDisruptionDetail.disruptions}
                    position={tomtomDisruptionDetail.position}
                    onClose={() => setTomtomDisruptionDetail(null)}
                />
            )}

            {/* MAP */}
            <MapContainer
                center={[51.505, -0.09]}
                zoom={13}
                preferCanvas={true}
                style={{ height: "100%", width: "100%", background: "#222" }}
            >
                <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; OpenStreetMap' />

                <HeatmapLayer isOn={heatmapOn} setSegments={setHeatmapSegments} setStatus={setStatus} />
                <SurfaceLayer isOn={surfacesOn} includeNoData={surfaceNoDataOn} setSegments={setSurfaceSegments} setLimitReached={setSurfaceLimitReached} setStatus={setStatus} />
                <UnlitLayer isOn={unlitOn} includeUnknown={unlitNoDataOn} setSegments={setUnlitSegments} setLimitReached={setUnlitLimitReached} setStatus={setStatus} />
                <CyclewayLayer isOn={cyclewayOn} layers={{ general: cyclewayGeneralOn, segregated: cyclewaySegregatedOn }} setSegmentsByLayer={setCyclewaySegmentsByLayer} setStatus={setStatus} />
                <HgvBannedLayer isOn={hgvBannedOn} setSegments={setHgvBannedSegments} setStatus={setStatus} />
                <GraphNetworkLayer isOn={graphNetworkOn} setSegments={setGraphNetworkSegments} setLimitReached={setGraphNetworkLimitReached} setStatus={setStatus} />
                <TflRoutesLayer isOn={tflRoutesOn || modifyTflOn} setSegments={setTflRoutesSegments} setStatus={setStatus} />
                <AttractionsLayer
                    isOn={attractionsOn}
                    layers={{ park: attractionParkOn, river: attractionRiverOn, sight: attractionSightOn }}
                    parkHoursOn={attractionParkHoursOn}
                    setSegmentsByKind={setAttractionSegmentsByKind}
                    setLimitReached={setAttractionLimitReached}
                    setStatus={setStatus}
                />
                <TflDisruptionsLayer isOn={tflDisruptionsOn} setSegments={setTflDisruptionSegments} setStatus={setStatus} />
                <TflDisruptionsRawLayer isOn={tflDisruptionsOn && tflGroundTruthOn} setPoints={setTflRawPoints} setLines={setTflRawLines} setPolygons={setTflRawPolygons} setStatus={setStatus} />
                <TomtomDisruptionsLayer isOn={tomtomDisruptionsOn} setSegments={setTomtomDisruptionSegments} setStatus={setTomtomDisruptionStatus} />
                <TrafficCalmingPointsLayer isOn={trafficCalmingOn} source={calmingSource} setPoints={setTrafficCalmingPoints} setStatus={setStatus} />
                <JunctionPointsLayer isOn={junctionOn} setPoints={setJunctionPoints} setStatus={setStatus} />
                <NodePointsLayer isOn={barriersOn} endpoint="barrier_points" statusLabel="Barriers" setPoints={setBarrierPoints} setStatus={setStatus} />
                <NodePointsLayer isOn={trafficSignalsOn} endpoint="traffic_signals_points" statusLabel="Traffic signals" setPoints={setTrafficSignalsPoints} setStatus={setStatus} />
                <NodePointsLayer isOn={miniRoundaboutOn} endpoint="mini_roundabout_points" statusLabel="Mini roundabouts" setPoints={setMiniRoundaboutPoints} setStatus={setStatus} />
                <NodePointsLayer isOn={crossingOn} endpoint="crossing_points" statusLabel="Crossing" setPoints={setCrossingPoints} setStatus={setStatus} />
                <NodePointsLayer isOn={giveWayOn} endpoint="give_way_points" statusLabel="Give way" setPoints={setGiveWayPoints} setStatus={setStatus} />
                <NodePointsLayer isOn={stopOn} endpoint="stop_points" statusLabel="Stop" setPoints={setStopPoints} setStatus={setStatus} />
                <MapEvents
                    inspectorData={inspectorData}
                    setInspectorData={setInspectorData}
                    setInspectorGeo={setInspectorGeo}
                    setInspectorPos={setInspectorPos}
                    pointPopup={pointPopup}
                    setPointPopup={setPointPopup}
                    tflDisruptionsOn={tflDisruptionsOn}
                    tflDisruptionDetail={tflDisruptionDetail}
                    setTflDisruptionDetail={setTflDisruptionDetail}
                    tomtomDisruptionsOn={tomtomDisruptionsOn}
                    tomtomDisruptionDetail={tomtomDisruptionDetail}
                    setTomtomDisruptionDetail={setTomtomDisruptionDetail}
                    accidentsOn={accidentsOn}
                    accidents={accidents}
                    junctionOn={junctionOn}
                    junctionPoints={junctionPoints}
                    barriersOn={barriersOn}
                    barrierPoints={barrierPoints}
                    trafficSignalsOn={trafficSignalsOn}
                    trafficSignalsPoints={trafficSignalsPoints}
                    miniRoundaboutOn={miniRoundaboutOn}
                    miniRoundaboutPoints={miniRoundaboutPoints}
                    crossingOn={crossingOn}
                    crossingPoints={crossingPoints}
                    giveWayOn={giveWayOn}
                    giveWayPoints={giveWayPoints}
                    stopOn={stopOn}
                    stopPoints={stopPoints}
                    modifyTflOn={modifyTflOn}
                    modifyTflProgramme={modifyTflProgramme}
                    setTflEditsAdded={setTflEditsAdded}
                    setTflEditsRemoved={setTflEditsRemoved}
                    pushTflSessionUndo={modifyTflOn ? (op) => setTflSessionUndoStack((prev) => [...prev, op]) : undefined}
                    modifyAttractionOn={modifyAttractionOn}
                    attractionType={attractionType}
                    setAttractionScratchPoints={setAttractionScratchPoints}
                    attractionName={attractionName}
                    onAttractionSightClick={handleAttractionSightClick}
                    onAttractionScratchClick={handleAttractionScratchClick}
                />

                {/* OSM park polygons (algorithm-tagged areas) while modifying attractions */}
                {modifyAttractionOn && osmParkPolygons.map((poly, idx) => (
                    <Polygon
                        key={`osm-park-${idx}`}
                        positions={poly.positions}
                        pathOptions={{ color: '#81C784', fillColor: '#A5D6A7', fillOpacity: 0.15, weight: 1 }}
                    />
                ))}

                {/* Manual attraction tagging zones (same geometry as apply_attraction_manual) */}
                {(modifyAttractionOn || attractionsOn) && attractionManualRegions.map((reg) => (
                    <React.Fragment key={`man-${reg.id}`}>
                        {(reg.zone_positions || []).map((ring, zi) => (
                            <Polygon
                                key={`man-${reg.id}-zone-${zi}`}
                                positions={ring}
                                pathOptions={attractionZonePathOptions(reg.type)}
                            />
                        ))}
                        {reg.type === 'sight' && reg.positions?.[0]?.length === 2 && (
                            <CircleMarker
                                key={`man-${reg.id}-pt`}
                                center={reg.positions[0]}
                                radius={4}
                                pathOptions={{
                                    color: ATTRACTION_TYPE_COLORS.sight,
                                    fillColor: '#fff',
                                    fillOpacity: 1,
                                    weight: 2,
                                }}
                            />
                        )}
                    </React.Fragment>
                ))}

                {/* Scratch tagging zone preview while drawing */}
                {modifyAttractionOn && attractionScratchZonePositions.map((ring, idx) => (
                    <Polygon
                        key={`scratch-zone-${idx}`}
                        positions={ring}
                        pathOptions={attractionZonePathOptions(attractionType, { fillOpacity: 0.12, weight: 1, lineOpacity: 0.65 })}
                    />
                ))}

                {/* Scratch points while drawing park/river */}
                {modifyAttractionOn && attractionType !== 'sight' && attractionScratchPoints.map((pt, idx) => (
                    <CircleMarker
                        key={`scratch-${idx}`}
                        center={pt}
                        radius={5}
                        pathOptions={{ color: '#FF6F00', fillColor: '#FFB74D', fillOpacity: 0.9, weight: 2 }}
                    />
                ))}
                {modifyAttractionOn && attractionType !== 'sight' && attractionScratchPoints.length >= 2 && (
                    <Polyline
                        positions={attractionScratchPoints}
                        color="#0277BD"
                        weight={3}
                        opacity={0.9}
                        dashArray="6 4"
                    />
                )}
                {modifyAttractionOn && attractionType !== 'sight' && attractionScratchPoints.length >= 3 && (
                    <Polyline
                        positions={[...attractionScratchPoints, attractionScratchPoints[0]]}
                        color={ATTRACTION_TYPE_COLORS[attractionType] || '#0277BD'}
                        weight={2}
                        opacity={0.7}
                    />
                )}

                {/* INSPECTOR RED OVERLAY */}
                {inspectorGeo && !modifyAttractionOn && (
                    <Polyline positions={inspectorGeo} color="red" weight={6} opacity={0.8} />
                )}

                {/* ELEVATION HEATMAP */}
                {heatmapOn && heatmapSegments.map((seg) => (
                    <Polyline
                        key={seg.id}
                        positions={seg.p}
                        color={getSegmentColor(seg.g)}
                        weight={3}
                        opacity={0.8}
                    />
                ))}

                {/* SURFACE HEATMAP (filter no_data by subtoggle) */}
                {surfacesOn && surfaceSegments
                    .filter(seg => surfaceNoDataOn || seg.t !== 'no_data')
                    .map((seg) => (
                        <Polyline
                            key={seg.id}
                            positions={seg.p}
                            color={getSurfaceColor(seg)}
                            weight={3}
                            opacity={0.85}
                        />
                    ))}

                {/* UNLIT HEATMAP (filter unknown by subtoggle) */}
                {unlitOn && unlitSegments
                    .filter(seg => unlitNoDataOn || seg.t === 'no')
                    .map((seg) => (
                        <Polyline
                            key={seg.id}
                            positions={seg.p}
                            color={getUnlitColor(seg.t)}
                            weight={3}
                            opacity={0.7}
                        />
                    ))}

                {/* CYCLEWAY (per layer) */}
                {cyclewayOn && ['general', 'segregated'].map(layer => {
                    const on = layer === 'general' ? cyclewayGeneralOn : cyclewaySegregatedOn;
                    const segs = cyclewaySegmentsByLayer[layer] || [];
                    if (!on || !segs.length) return null;
                    const color = CYCLEWAY_LAYER_COLORS[layer] || '#2E7D32';
                    return <React.Fragment key={layer}>{segs.map((seg) => (
                        <Polyline key={seg.id} positions={seg.p} color={color} weight={3} opacity={0.8} />
                    ))}</React.Fragment>;
                })}

                {/* HGV BANNED */}
                {hgvBannedOn && hgvBannedSegments.map((seg) => (
                    <Polyline key={seg.id} positions={seg.p} color="#BF360C" weight={3} opacity={0.8} />
                ))}

                {/* GRAPH NETWORK */}
                {graphNetworkOn && graphNetworkSegments.map((seg) => (
                    <Polyline key={seg.id} positions={seg.p} color={getGraphNetworkColor(seg.h)} weight={2} opacity={0.75} />
                ))}

                {/* TfL CYCLE ROUTES (color by programme) */}
                {(tflRoutesOn || modifyTflOn) && tflRoutesSegments.map((seg) => (
                    <Polyline key={seg.id} positions={seg.p} color={getTflProgrammeColor(seg.programme)} weight={3} opacity={0.85} />
                ))}

                {/* ATTRACTION EDGES (park / river / sight) */}
                {attractionsOn && ['park', 'river', 'sight'].map((kind) => {
                    const segs = attractionSegmentsByKind[kind] || [];
                    const useParkHours = kind === 'park' && attractionParkHoursOn && attractionParkOn;
                    const color = ATTRACTION_TYPE_COLORS[kind] || '#00796B';
                    return (
                        <React.Fragment key={`attr-${kind}`}>
                            {segs.map((seg) => {
                                const segColor = useParkHours
                                    ? (seg.park_open ? PARK_HOURS_OPEN_COLOR : PARK_HOURS_CLOSED_COLOR)
                                    : color;
                                return (
                                    <Polyline key={`${kind}-${seg.id}`} positions={seg.p} color={segColor} weight={4} opacity={0.85} />
                                );
                            })}
                        </React.Fragment>
                    );
                })}

                {/* MODIFY: added (yellow) and removed (black) */}
                {modifyTflOn && tflEditsAdded.map((seg, idx) => (
                    <Polyline key={`add-${seg.source}-${seg.target}-${idx}`} positions={seg.geometry || []} color="#FFEB3B" weight={5} opacity={0.95} />
                ))}
                {modifyTflOn && tflEditsRemoved.map((seg, idx) => (
                    <Polyline key={`rem-${seg.source}-${seg.target}-${idx}`} positions={seg.geometry || []} color="#212121" weight={5} opacity={0.9} />
                ))}

                {/* TfL LIVE DISRUPTIONS (color by type) */}
                {tflDisruptionsOn && tflDisruptionSegments.map((seg) => (
                    <Polyline key={seg.id} positions={seg.p} color={getTflDisruptionColor(seg.type)} weight={4} opacity={0.9} />
                ))}

                {/* TomTom LIVE DISRUPTIONS (cluster colors; environmental = dashed blue) */}
                {tomtomDisruptionsOn && tomtomDisruptionSegments.map((seg) => (
                    <Polyline
                        key={seg.id}
                        positions={seg.p}
                        color={getTomtomDisruptionColor(seg.type)}
                        weight={4}
                        opacity={0.9}
                        pathOptions={seg.type === 'environmental' ? { dashArray: '5, 5' } : undefined}
                    />
                ))}

                {/* TfL GROUND TRUTH (raw points, lines, polygons from API) */}
                {tflDisruptionsOn && tflGroundTruthOn && (
                    <>
                        {tflRawPoints.map((f, idx) => (
                            <CircleMarker key={`raw-pt-${idx}`} center={f.coordinates} radius={6} pathOptions={{ color: '#9C27B0', fillColor: '#9C27B0', fillOpacity: 0.7, weight: 2 }} />
                        ))}
                        {tflRawLines.map((f, idx) => (
                            <Polyline key={`raw-line-${idx}`} positions={f.coordinates} color="#7B1FA2" weight={3} opacity={0.85} dashArray="4 4" />
                        ))}
                        {tflRawPolygons.map((f, idx) => (
                            <Polygon key={`raw-poly-${idx}`} positions={f.coordinates} pathOptions={{ color: '#5E35B1', fillColor: '#5E35B1', fillOpacity: 0.2, weight: 2 }} />
                        ))}
                    </>
                )}

                {/* TRAFFIC CALMING POINTS (color by type) */}
                {trafficCalmingOn && trafficCalmingPoints.map((p, idx) => (
                    <CircleMarker key={`tc-${idx}`} center={[p.lat, p.lon]} radius={4} pathOptions={{ color: getTrafficCalmingColor(p.type), fillColor: getTrafficCalmingColor(p.type), fillOpacity: 0.9, weight: 1 }} />
                ))}

                {/* JUNCTION POINTS (edge; color by type) */}
                {junctionOn && junctionPoints.map((p, idx) => (
                    <CircleMarker key={`jn-${idx}`} center={[p.lat, p.lon]} radius={4} pathOptions={{ color: getJunctionColor(p.type), fillColor: getJunctionColor(p.type), fillOpacity: 0.9, weight: 1 }} />
                ))}

                {/* NODE: BARRIERS (colour by routing cluster) */}
                {barriersOn && barrierPoints.map((p, idx) => (
                    <CircleMarker key={`bar-${idx}`} center={[p.lat, p.lon]} radius={3.5} pathOptions={{ color: getBarrierColor(p), fillColor: getBarrierColor(p), fillOpacity: 0.9, weight: 1 }} />
                ))}
                {/* NODE: TRAFFIC SIGNALS, MINI ROUNDABOUT, CROSSING, GIVE WAY, STOP */}
                {trafficSignalsOn && trafficSignalsPoints.map((p, idx) => (
                    <CircleMarker key={`ts-${idx}`} center={[p.lat, p.lon]} radius={3} pathOptions={{ color: '#D32F2F', fillColor: '#D32F2F', fillOpacity: 0.9, weight: 1 }} />
                ))}
                {miniRoundaboutOn && miniRoundaboutPoints.map((p, idx) => (
                    <CircleMarker key={`mr-${idx}`} center={[p.lat, p.lon]} radius={3} pathOptions={{ color: '#7B1FA2', fillColor: '#7B1FA2', fillOpacity: 0.9, weight: 1 }} />
                ))}
                {crossingOn && crossingPoints.map((p, idx) => (
                    <CircleMarker key={`cr-${idx}`} center={[p.lat, p.lon]} radius={3} pathOptions={{ color: '#1976D2', fillColor: '#1976D2', fillOpacity: 0.9, weight: 1 }} />
                ))}
                {giveWayOn && giveWayPoints.map((p, idx) => (
                    <CircleMarker key={`gw-${idx}`} center={[p.lat, p.lon]} radius={3} pathOptions={{ color: '#F57C00', fillColor: '#F57C00', fillOpacity: 0.9, weight: 1 }} />
                ))}
                {stopOn && stopPoints.map((p, idx) => (
                    <CircleMarker key={`st-${idx}`} center={[p.lat, p.lon]} radius={3} pathOptions={{ color: '#E64A19', fillColor: '#E64A19', fillOpacity: 0.9, weight: 1 }} />
                ))}

                {/* ACCIDENT MARKERS */}
                {accidentsOn && accidents.map((pos, idx) => (
                    <CircleMarker key={idx} center={pos} radius={3} pathOptions={{ color: 'transparent', fillColor: '#ff4444', fillOpacity: 0.8 }} />
                ))}
            </MapContainer>
        </div>
    );
}

export default App;

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Source, Layer, Marker, useMap } from 'react-map-gl/mapbox';
import { TriangleAlert } from 'lucide-react';
import { typedChunksToGeoJSON, pathToLineGeoJSON, pathMidLngLat } from '../../map/coords';
import {
  OVERLAY_KIND_META,
  OVERLAY_MODE_META,
  TRAFFIC_OVERLAY,
  chunksForMode,
  trafficChunks,
  formatOverlayLength,
  formatOverlayHoverDetail,
} from './overlayModes';
import { formatElevation } from '../units';

const EMPTY_FC = { type: 'FeatureCollection', features: [] };

/** Match pink optimized route stroke (RouteLayers CasedLineSource). */
const ROUTE_CORE_WIDTH = 5;
const ROUTE_CASING_WIDTH = 13;

function kindColorExpr() {
  const cases = [];
  Object.entries(OVERLAY_KIND_META).forEach(([kind, meta]) => {
    cases.push(['==', ['get', 'kind'], kind], meta.color);
  });
  return ['case', ...cases, TRAFFIC_OVERLAY.hub];
}

function hoverStats(props, kind, units = 'metric') {
  const len = formatOverlayLength(Number(props.length_m) || 0, units);
  if (kind === 'steep') {
    const elev = formatElevation(Number(props.elev_gain_m) || 0, units);
    const gain = Number(props.elev_gain_m) || 0;
    return gain > 0 ? `${len} · +${elev}` : len;
  }
  return len;
}

function TrafficJamMarkers({ runs, units = 'metric' }) {
  const markers = useMemo(() => {
    return (runs || []).map((run, i) => {
      const mid = pathMidLngLat(run.path);
      if (!mid) return null;
      return {
        key: run.run_id || `jam-${i}`,
        lng: mid[0],
        lat: mid[1],
        category: run.category || '',
        length_m: run.length_m,
      };
    }).filter(Boolean);
  }, [runs]);

  return markers.map((m) => (
    <Marker key={m.key} longitude={m.lng} latitude={m.lat} anchor="center">
      <div
        title={`${formatOverlayHoverDetail('traffic', { category: m.category })} · ${formatOverlayLength(m.length_m, units)}`}
        style={{
          width: 22,
          height: 22,
          borderRadius: 999,
          background: '#fff',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 1px 4px rgba(0,0,0,0.28)',
          pointerEvents: 'none',
        }}
      >
        <TriangleAlert size={13} color={TRAFFIC_OVERLAY.hub} strokeWidth={2.5} aria-hidden />
      </div>
    </Marker>
  ));
}

function OverlayHoverChip({ hover }) {
  if (!hover) return null;
  return (
    <div
      className="overlay-hover-chip"
      style={{
        position: 'absolute',
        left: hover.x + 14,
        top: hover.y + 14,
        zIndex: 5,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 10px',
        borderRadius: 999,
        background: 'rgba(255,255,255,0.96)',
        border: '1px solid #e4e4e7',
        boxShadow: '0 4px 14px rgba(16,24,40,0.16)',
        fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
        fontSize: 12,
        fontWeight: 650,
        color: '#27272a',
        pointerEvents: 'none',
        whiteSpace: 'nowrap',
        animation: 'overlay-hover-in 140ms cubic-bezier(0.23, 1, 0.32, 1)',
      }}
    >
      <span
        style={{
          width: 10,
          height: 10,
          borderRadius: 3,
          background: hover.color,
          flexShrink: 0,
        }}
      />
      <span>{hover.detail}</span>
      <span style={{ color: '#71717a', fontWeight: 550 }}>{hover.stats}</span>
    </div>
  );
}

/** Chunks matching an island hover — by run ids when present, else by kind. */
function externalHoverChunks(safest, extHover) {
  if (!safest || !extHover?.kind) return [];
  const typedKey = extHover.modeId === 'traffic'
    ? TRAFFIC_OVERLAY.typedKey
    : OVERLAY_MODE_META[extHover.modeId]?.typedKey;
  const pool = (typedKey && safest[typedKey]) || [];
  if (extHover.runIds?.length) {
    const wanted = new Set(extHover.runIds);
    return pool.filter((c) => wanted.has(c.run_id));
  }
  return pool.filter((c) => c.kind === extHover.kind);
}

/**
 * v2 overlays: typed mode runs + always-on traffic + hover highlight.
 * `externalHover` mirrors island hover onto the map (segment casing +
 * scrubber probe); `onHoverChange` reports map hover back to the island.
 */
export default function V2OverlayLayers({
  safest,
  modeId,
  prefix = 'v2',
  units = 'metric',
  externalHover = null,
  onHoverChange,
}) {
  const maps = useMap();
  const map = maps.main || maps.current;
  const [hover, setHover] = useState(null);
  const emittedRef = useRef(null);
  const onHoverChangeRef = useRef(onHoverChange);
  onHoverChangeRef.current = onHoverChange;

  const modeChunks = useMemo(() => chunksForMode(safest, modeId), [safest, modeId]);
  const jamChunks = useMemo(() => trafficChunks(safest), [safest]);
  const modeFc = useMemo(() => typedChunksToGeoJSON(modeChunks), [modeChunks]);
  const jamFc = useMemo(() => typedChunksToGeoJSON(jamChunks), [jamChunks]);

  const highlightFc = useMemo(() => {
    if (!hover?.path) return EMPTY_FC;
    return pathToLineGeoJSON(hover.path, { run_id: hover.runId });
  }, [hover]);

  const externalChunks = useMemo(
    () => externalHoverChunks(safest, externalHover),
    [safest, externalHover],
  );
  const externalFc = useMemo(
    () => (externalChunks.length ? typedChunksToGeoJSON(externalChunks) : EMPTY_FC),
    [externalChunks],
  );
  const externalColor = externalHover?.kind
    ? (OVERLAY_KIND_META[externalHover.kind]?.color || TRAFFIC_OVERLAY.hub)
    : TRAFFIC_OVERLAY.hub;

  /** Report map hover to the island only when the segment identity changes. */
  const emitHover = React.useCallback((next) => {
    const key = next ? `${next.modeId}|${next.kind}|${next.runId}` : null;
    if (emittedRef.current === key) return;
    emittedRef.current = key;
    onHoverChangeRef.current?.(next);
  }, []);

  const modeLayerId = `${prefix}-mode-line`;
  const jamLayerId = `${prefix}-jam-line`;
  const hiCaseId = `${prefix}-hi-case`;
  const hiLineId = `${prefix}-hi-line`;

  useEffect(() => {
    if (!map) return undefined;
    const onMove = (e) => {
      const ids = [modeLayerId, jamLayerId].filter((id) => map.getLayer(id));
      if (!ids.length) {
        setHover(null);
        return;
      }
      const feats = map.queryRenderedFeatures(e.point, { layers: ids });
      const f = feats?.[0];
      if (!f) {
        setHover(null);
        emitHover(null);
        map.getCanvas().style.cursor = '';
        return;
      }
      const kind = f.properties?.kind || '';
      const meta = OVERLAY_KIND_META[kind] || { label: kind, color: TRAFFIC_OVERLAY.hub };
      const runId = f.properties?.run_id || '';
      const pool = kind === 'traffic' ? jamChunks : modeChunks;
      const run = pool.find((c) => c.run_id === runId) || null;
      const props = {
        ...f.properties,
        length_m: run?.length_m ?? f.properties?.length_m,
        elev_gain_m: run?.elev_gain_m ?? f.properties?.elev_gain_m,
        name: run?.name || f.properties?.name,
        label: run?.label || f.properties?.label,
        surface: run?.surface || f.properties?.surface,
        category: run?.category || f.properties?.category,
      };
      setHover({
        x: e.point.x,
        y: e.point.y,
        kind,
        color: meta.color,
        detail: formatOverlayHoverDetail(kind, props),
        stats: hoverStats(props, kind, units),
        runId,
        path: run?.path || null,
      });
      emitHover({
        source: 'map',
        modeId: kind === 'traffic' ? 'traffic' : modeId,
        kind,
        runId,
      });
      map.getCanvas().style.cursor = 'pointer';
    };
    const onLeave = () => {
      setHover(null);
      emitHover(null);
      map.getCanvas().style.cursor = '';
    };
    map.on('mousemove', onMove);
    map.getCanvas().addEventListener('mouseleave', onLeave);
    return () => {
      map.off('mousemove', onMove);
      map.getCanvas().removeEventListener('mouseleave', onLeave);
    };
  }, [map, modeLayerId, jamLayerId, modeChunks, jamChunks, units, modeId, emitHover]);

  if (!safest) return null;

  return (
    <>
      {modeId && modeChunks.length > 0 && (
        <Source id={`${prefix}-mode`} type="geojson" data={modeFc}>
          <Layer
            id={modeLayerId}
            type="line"
            paint={{
              'line-color': kindColorExpr(),
              'line-width': ROUTE_CORE_WIDTH,
              'line-opacity': 0.95,
              'line-emissive-strength': 1,
            }}
            layout={{ 'line-join': 'round', 'line-cap': 'round' }}
          />
        </Source>
      )}
      {jamChunks.length > 0 && (
        <>
          <Source id={`${prefix}-jam`} type="geojson" data={jamFc}>
            <Layer
              id={jamLayerId}
              type="line"
              paint={{
                'line-color': TRAFFIC_OVERLAY.hub,
                'line-width': ROUTE_CORE_WIDTH,
                'line-opacity': 0.95,
                'line-emissive-strength': 1,
              }}
              layout={{ 'line-join': 'round', 'line-cap': 'round' }}
            />
          </Source>
          <TrafficJamMarkers runs={jamChunks} units={units} />
        </>
      )}
      {hover?.path && (
        <Source id={`${prefix}-hi`} type="geojson" data={highlightFc}>
          <Layer
            id={hiCaseId}
            type="line"
            paint={{
              'line-color': '#ffffff',
              'line-width': ROUTE_CASING_WIDTH,
              'line-opacity': 0.92,
              'line-emissive-strength': 1,
            }}
            layout={{ 'line-join': 'round', 'line-cap': 'round' }}
          />
          <Layer
            id={hiLineId}
            type="line"
            paint={{
              'line-color': hover.color,
              'line-width': ROUTE_CORE_WIDTH,
              'line-opacity': 1,
              'line-emissive-strength': 1,
            }}
            layout={{ 'line-join': 'round', 'line-cap': 'round' }}
          />
        </Source>
      )}
      {externalChunks.length > 0 && (
        <Source id={`${prefix}-xhi`} type="geojson" data={externalFc}>
          <Layer
            id={`${prefix}-xhi-case`}
            type="line"
            paint={{
              'line-color': '#ffffff',
              'line-width': ROUTE_CASING_WIDTH,
              'line-opacity': 0.92,
              'line-emissive-strength': 1,
            }}
            layout={{ 'line-join': 'round', 'line-cap': 'round' }}
          />
          <Layer
            id={`${prefix}-xhi-line`}
            type="line"
            paint={{
              'line-color': externalColor,
              'line-width': ROUTE_CORE_WIDTH,
              'line-opacity': 1,
              'line-emissive-strength': 1,
            }}
            layout={{ 'line-join': 'round', 'line-cap': 'round' }}
          />
        </Source>
      )}
      {externalHover?.point && (
        <Marker
          longitude={externalHover.point[0]}
          latitude={externalHover.point[1]}
          anchor="center"
        >
          <div
            style={{
              width: 16,
              height: 16,
              borderRadius: 999,
              background: '#ffffff',
              border: '3px solid #FF0061',
              boxShadow: '0 1px 6px rgba(0,0,0,0.35)',
              pointerEvents: 'none',
            }}
          />
        </Marker>
      )}
      <OverlayHoverChip hover={hover} />
    </>
  );
}

import { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { CircleLayer, LineLayer, MarkerView, ShapeSource } from '@rnmapbox/maps';
import { TriangleAlert } from 'lucide-react-native';
import { pathToLineCoords, type LatLon } from '../lib/coords';
import { brand } from '../theme/tokens';
import {
  OVERLAY_KIND_META,
  OVERLAY_MODE_META,
  TRAFFIC_OVERLAY,
  chunksForMode,
  formatOverlayHoverDetail,
  formatOverlayLength,
  trafficChunks,
} from './overlayModes';
import type { RouteHover } from './routeHover';
import { LINE_EMISSIVE } from './styles';

/** Match pink optimized route stroke (web ROUTE_CORE_WIDTH). */
export const ROUTE_CORE_WIDTH = 5;
export const ROUTE_CASING_WIDTH = 13;
/** Generous GL hit target — MarkerView Pressables are unreliable on Android. */
const OVERLAY_HITBOX = { width: 52, height: 52 };

/** Route line layer id — overlays stack above this (not above markers). */
export const SAFEST_LINE_LAYER_ID = 'safest-line';

type Chunk = {
  path?: number[][];
  kind?: string;
  length_m?: number;
  elev_gain_m?: number;
  run_id?: string;
  label?: string;
  name?: string;
  surface?: string;
  category?: string;
};

export type OverlayTapInfo = {
  kind: string;
  color: string;
  detail: string;
  stats: string;
  runId?: string;
  path?: number[][] | null;
  /** Route-anchored chip position [lng, lat]. */
  coordinate?: [number, number] | null;
};

type Props = {
  safest: Record<string, unknown> | null;
  overlayMode: string | null;
  /** Island → map highlight + scrub probe (web externalHover). */
  externalHover?: RouteHover | null;
  /** Map segment tap → detail chip + island sync. */
  onSegmentTap?: (info: OverlayTapInfo | null) => void;
  activeTap?: OverlayTapInfo | null;
  /** LineLayer id of the pink route core — overlays paint above it. */
  aboveRouteLayerID?: string;
};

function hoverStats(props: Record<string, unknown>, kind: string) {
  const len = formatOverlayLength(Number(props.length_m) || 0);
  if (kind === 'steep') {
    const gain = Number(props.elev_gain_m) || 0;
    if (gain > 0) return `${len} · +${Math.round(gain)} m`;
  }
  return len;
}

function pathMidLngLat(path?: number[][] | null): [number, number] | null {
  const coords = pathToLineCoords(path as LatLon[] | undefined);
  if (!coords?.length) return null;
  return coords[Math.floor(coords.length / 2)] || null;
}

function typedChunksToGeoJSON(chunks: Chunk[]) {
  const features: GeoJSON.Feature[] = [];
  (chunks || []).forEach((chunk, i) => {
    const coords = pathToLineCoords(chunk?.path);
    if (!coords) return;
    features.push({
      type: 'Feature',
      properties: {
        i,
        kind: chunk.kind || '',
        length_m: Number(chunk.length_m) || 0,
        elev_gain_m: Number(chunk.elev_gain_m) || 0,
        run_id: chunk.run_id || `r-${i}`,
        label: chunk.label || chunk.name || '',
        name: chunk.name || '',
        surface: chunk.surface || '',
        category: chunk.category || '',
      },
      geometry: { type: 'LineString', coordinates: coords },
    });
  });
  return { type: 'FeatureCollection' as const, features };
}

/** Chunks matching an island hover — by run ids when present, else by kind. */
function externalHoverChunks(safest: Record<string, unknown> | null, extHover: RouteHover | null | undefined) {
  if (!safest || !extHover?.kind) return [] as Chunk[];
  const typedKey = extHover.modeId === 'traffic'
    ? TRAFFIC_OVERLAY.typedKey
    : OVERLAY_MODE_META[extHover.modeId || '']?.typedKey;
  const pool = (typedKey && (safest[typedKey] as Chunk[])) || [];
  if (extHover.runIds?.length) {
    const wanted = new Set(extHover.runIds.filter(Boolean));
    return pool.filter((c) => wanted.has(c.run_id));
  }
  if (extHover.runId) {
    return pool.filter((c) => c.run_id === extHover.runId);
  }
  return pool.filter((c) => c.kind === extHover.kind);
}

function tapInfoForRun(run: Chunk): OverlayTapInfo {
  const kind = run.kind || 'traffic';
  const meta = OVERLAY_KIND_META[kind] || { label: kind, color: TRAFFIC_OVERLAY.hub };
  const merged = {
    length_m: run.length_m,
    elev_gain_m: run.elev_gain_m,
    name: run.name,
    label: run.label,
    surface: run.surface,
    category: run.category,
  };
  const path = run.path || null;
  return {
    kind,
    color: meta.color,
    detail: formatOverlayHoverDetail(kind, merged),
    stats: hoverStats(merged, kind),
    runId: run.run_id,
    path,
    coordinate: pathMidLngLat(path),
  };
}

function TrafficJamMarkers({
  runs,
}: {
  runs: Chunk[];
}) {
  const markers = useMemo(() => {
    return (runs || [])
      .map((run, i) => {
        const mid = pathMidLngLat(run.path);
        if (!mid) return null;
        return {
          key: run.run_id || `jam-${i}`,
          coordinate: mid,
        };
      })
      .filter(Boolean) as { key: string; coordinate: [number, number] }[];
  }, [runs]);

  // Visual only — taps go through ShapeSource hit layers (Android MarkerView
  // Pressables race the map and miss intermittently).
  return (
    <>
      {markers.map((m) => (
        <MarkerView
          key={m.key}
          coordinate={m.coordinate}
          anchor={{ x: 0.5, y: 0.5 }}
          allowOverlap
          allowOverlapWithPuck
          pointerEvents="none"
        >
          <View style={styles.jam} collapsable={false} pointerEvents="none">
            <TriangleAlert size={13} color={TRAFFIC_OVERLAY.hub} strokeWidth={2.5} />
          </View>
        </MarkerView>
      ))}
    </>
  );
}

/** GL hit targets at jam midpoints — reliable on Android (unlike MarkerView Pressable). */
function TrafficJamHitSource({
  runs,
  onPress,
}: {
  runs: Chunk[];
  onPress?: (info: OverlayTapInfo) => void;
}) {
  const fc = useMemo(() => {
    const features: GeoJSON.Feature[] = [];
    (runs || []).forEach((run, i) => {
      const mid = pathMidLngLat(run.path);
      if (!mid) return;
      features.push({
        type: 'Feature',
        properties: {
          run_id: run.run_id || `r-${i}`,
          i,
        },
        geometry: { type: 'Point', coordinates: mid },
      });
    });
    return { type: 'FeatureCollection' as const, features };
  }, [runs]);

  if (!fc.features.length) return null;

  return (
    <ShapeSource
      id="overlay-traffic-hits"
      shape={fc}
      hitbox={{ width: 56, height: 56 }}
      onPress={(event) => {
        const f = event.features?.[0];
        if (!f || !onPress) return;
        const runId = String((f.properties as { run_id?: string } | null)?.run_id || '');
        const run = runs.find((c) => c.run_id === runId)
          || runs[Number((f.properties as { i?: number } | null)?.i)]
          || null;
        if (!run) return;
        onPress(tapInfoForRun({ ...run, kind: 'traffic' }));
      }}
    >
      <CircleLayer
        id="overlay-traffic-hits-circle"
        style={{
          circleRadius: 22,
          circleColor: '#000000',
          circleOpacity: 0,
          circlePitchAlignment: 'map',
          circlePitchScale: 'map',
        }}
      />
    </ShapeSource>
  );
}

/** Route-anchored detail chip (web hover chip, stuck to segment mid). */
export function OverlayTapChip({ tap }: { tap: OverlayTapInfo | null }) {
  const coord = tap?.coordinate || pathMidLngLat(tap?.path);
  if (!tap || !coord) return null;
  return (
    <MarkerView
      coordinate={coord}
      // Anchor must stay in [0,1] — float the chip above via padding, not y>1.
      anchor={{ x: 0.5, y: 1 }}
      allowOverlap
      allowOverlapWithPuck
      pointerEvents="none"
    >
      <View style={styles.chipLift} collapsable={false} pointerEvents="none">
        <View style={styles.chip} collapsable={false} pointerEvents="none">
          <View style={[styles.swatch, { backgroundColor: tap.color }]} />
          <Text style={styles.chipDetail} numberOfLines={1}>
            {tap.detail}
          </Text>
          <Text style={styles.chipStats} numberOfLines={1}>
            {tap.stats}
          </Text>
        </View>
      </View>
    </MarkerView>
  );
}

/**
 * Paint active overlay: mode → traffic → map-hi → island-hi → probe
 * (web V2OverlayLayers paint order). Markers stay as MarkerViews above GL.
 */
export function RouteOverlayLayers({
  safest,
  overlayMode,
  externalHover = null,
  onSegmentTap,
  activeTap,
  aboveRouteLayerID = SAFEST_LINE_LAYER_ID,
}: Props) {
  const modeChunks = useMemo(() => {
    if (!safest || !overlayMode) return [];
    return chunksForMode(safest, overlayMode) as Chunk[];
  }, [safest, overlayMode]);

  const jamChunks = useMemo(
    () => (safest ? (trafficChunks(safest) as Chunk[]) : []),
    [safest],
  );

  const modeFc = useMemo(() => typedChunksToGeoJSON(modeChunks), [modeChunks]);
  const jamFc = useMemo(() => typedChunksToGeoJSON(jamChunks), [jamChunks]);

  const highlightFc = useMemo(() => {
    if (!activeTap?.path || activeTap.path.length < 2) {
      return { type: 'FeatureCollection' as const, features: [] };
    }
    const coords = pathToLineCoords(activeTap.path as LatLon[]);
    if (!coords) return { type: 'FeatureCollection' as const, features: [] };
    return {
      type: 'FeatureCollection' as const,
      features: [{
        type: 'Feature' as const,
        properties: { kind: activeTap.kind },
        geometry: { type: 'LineString' as const, coordinates: coords },
      }],
    };
  }, [activeTap]);

  const externalChunks = useMemo(
    () => externalHoverChunks(safest, externalHover),
    [safest, externalHover],
  );
  const externalFc = useMemo(
    () => (externalChunks.length ? typedChunksToGeoJSON(externalChunks) : { type: 'FeatureCollection' as const, features: [] }),
    [externalChunks],
  );
  const externalColor = externalHover?.kind
    ? (OVERLAY_KIND_META[externalHover.kind]?.color || TRAFFIC_OVERLAY.hub)
    : TRAFFIC_OVERLAY.hub;

  const probeFc = useMemo(() => {
    if (!externalHover?.point) {
      return { type: 'FeatureCollection' as const, features: [] };
    }
    return {
      type: 'FeatureCollection' as const,
      features: [{
        type: 'Feature' as const,
        properties: {},
        geometry: { type: 'Point' as const, coordinates: externalHover.point },
      }],
    };
  }, [externalHover?.point]);

  const kindColorExpr = useMemo(() => {
    const cases: unknown[] = [];
    Object.entries(OVERLAY_KIND_META).forEach(([kind, meta]) => {
      cases.push(['==', ['get', 'kind'], kind], meta.color);
    });
    return ['case', ...cases, TRAFFIC_OVERLAY.hub] as unknown as string;
  }, []);

  const handlePress = (
    pool: Chunk[],
    modeId: string,
    event: { features: GeoJSON.Feature[] },
  ) => {
    const f = event.features?.[0];
    if (!f || !onSegmentTap) return;
    const props = (f.properties || {}) as Record<string, unknown>;
    const kind = String(props.kind || '');
    const meta = OVERLAY_KIND_META[kind] || { label: kind, color: TRAFFIC_OVERLAY.hub };
    const runId = String(props.run_id || '');
    const run = pool.find((c) => c.run_id === runId) || null;
    const merged = {
      ...props,
      length_m: run?.length_m ?? props.length_m,
      elev_gain_m: run?.elev_gain_m ?? props.elev_gain_m,
      name: run?.name || props.name,
      label: run?.label || props.label,
      surface: run?.surface || props.surface,
      category: run?.category || props.category,
    };
    const path = run?.path || null;
    onSegmentTap({
      kind,
      color: meta.color,
      detail: formatOverlayHoverDetail(kind, merged),
      stats: hoverStats(merged, kind),
      runId,
      path,
      coordinate: pathMidLngLat(path),
    });
    void modeId;
  };

  if (!safest) return null;

  // Stack: route (external) → mode → traffic → highlights → probe. Markers are View overlays on top.
  const modeAbove = aboveRouteLayerID;
  const trafficAbove = overlayMode && modeFc.features.length > 0
    ? 'overlay-mode-line'
    : aboveRouteLayerID;
  const hiAbove = jamFc.features.length > 0 ? 'overlay-traffic-line' : trafficAbove;
  const xhiAbove = highlightFc.features.length > 0 && activeTap ? 'overlay-hi-line' : hiAbove;

  return (
    <>
      {/* Mode under traffic — web paint order */}
      {overlayMode && modeFc.features.length > 0 && (
        <ShapeSource
          id="overlay-mode"
          shape={modeFc}
          hitbox={OVERLAY_HITBOX}
          onPress={(e) => handlePress(modeChunks, overlayMode, e)}
        >
          <LineLayer
            id="overlay-mode-line"
            aboveLayerID={modeAbove}
            style={{
              lineColor: kindColorExpr as unknown as string,
              lineWidth: ROUTE_CORE_WIDTH,
              lineOpacity: 0.95,
              lineCap: 'round',
              lineJoin: 'round',
              ...LINE_EMISSIVE,
            }}
          />
        </ShapeSource>
      )}

      {jamFc.features.length > 0 && (
        <ShapeSource
          id="overlay-traffic"
          shape={jamFc}
          hitbox={OVERLAY_HITBOX}
          onPress={(e) => handlePress(jamChunks, 'traffic', e)}
        >
          <LineLayer
            id="overlay-traffic-line"
            aboveLayerID={trafficAbove}
            style={{
              lineColor: TRAFFIC_OVERLAY.hub,
              lineWidth: ROUTE_CORE_WIDTH,
              lineOpacity: 0.95,
              lineCap: 'round',
              lineJoin: 'round',
              ...LINE_EMISSIVE,
            }}
          />
        </ShapeSource>
      )}

      {highlightFc.features.length > 0 && activeTap && (
        <ShapeSource id="overlay-hi" shape={highlightFc}>
          <LineLayer
            id="overlay-hi-casing"
            aboveLayerID={hiAbove}
            style={{
              lineColor: '#ffffff',
              lineWidth: ROUTE_CASING_WIDTH,
              lineOpacity: 0.92,
              lineCap: 'round',
              lineJoin: 'round',
              ...LINE_EMISSIVE,
            }}
          />
          <LineLayer
            id="overlay-hi-line"
            aboveLayerID="overlay-hi-casing"
            style={{
              lineColor: activeTap.color,
              lineWidth: ROUTE_CORE_WIDTH,
              lineOpacity: 1,
              lineCap: 'round',
              lineJoin: 'round',
              ...LINE_EMISSIVE,
            }}
          />
        </ShapeSource>
      )}

      {externalFc.features.length > 0 && (
        <ShapeSource id="overlay-xhi" shape={externalFc}>
          <LineLayer
            id="overlay-xhi-casing"
            aboveLayerID={xhiAbove}
            style={{
              lineColor: '#ffffff',
              lineWidth: ROUTE_CASING_WIDTH,
              lineOpacity: 0.92,
              lineCap: 'round',
              lineJoin: 'round',
              ...LINE_EMISSIVE,
            }}
          />
          <LineLayer
            id="overlay-xhi-line"
            aboveLayerID="overlay-xhi-casing"
            style={{
              lineColor: externalColor,
              lineWidth: ROUTE_CORE_WIDTH,
              lineOpacity: 1,
              lineCap: 'round',
              lineJoin: 'round',
              ...LINE_EMISSIVE,
            }}
          />
        </ShapeSource>
      )}

      {probeFc.features.length > 0 && (
        <ShapeSource id="overlay-probe" shape={probeFc}>
          <CircleLayer
            id="overlay-probe-dot"
            aboveLayerID={externalFc.features.length > 0 ? 'overlay-xhi-line' : xhiAbove}
            style={{
              circleRadius: 7,
              circleColor: '#ffffff',
              circleStrokeWidth: 3,
              circleStrokeColor: brand.fuchsia,
              circlePitchAlignment: 'map',
              circlePitchScale: 'map',
            }}
          />
        </ShapeSource>
      )}

      <TrafficJamHitSource
        runs={jamChunks}
        onPress={(info) => onSegmentTap?.(info)}
      />
      <TrafficJamMarkers runs={jamChunks} />
      <OverlayTapChip tap={activeTap ?? null} />
    </>
  );
}

const styles = StyleSheet.create({
  jam: {
    width: 28,
    height: 28,
    borderRadius: 999,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.28,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
    elevation: 3,
  },
  /** Lifts chip above the route point without illegal MarkerView anchors. */
  chipLift: {
    paddingBottom: 14,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 999,
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderWidth: 1,
    borderColor: '#e4e4e7',
    shadowColor: '#000',
    shadowOpacity: 0.16,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 8,
    maxWidth: 260,
  },
  swatch: {
    width: 10,
    height: 10,
    borderRadius: 3,
    flexShrink: 0,
  },
  chipDetail: {
    fontSize: 12,
    fontWeight: '600',
    color: '#27272a',
    flexShrink: 1,
  },
  chipStats: {
    fontSize: 12,
    fontWeight: '500',
    color: '#71717a',
    flexShrink: 0,
  },
});

import { pathToLineCoords } from '../lib/coords';
import { OVERLAY_KIND_META, TRAFFIC_OVERLAY } from '../map/overlayModes';

const EMPTY_FC = JSON.stringify({ type: 'FeatureCollection', features: [] });

type Chunk = {
  path?: number[][];
  kind?: string;
  run_id?: string;
};

/** Tuned nav line as a GeoJSON string for the native route layer. */
export function routeLineJson(path: number[][] | null | undefined): string {
  const coords = pathToLineCoords(path);
  if (!coords) return EMPTY_FC;
  return JSON.stringify({
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: {},
        geometry: { type: 'LineString', coordinates: coords },
      },
    ],
  });
}

/**
 * Overlay segments for the native map. Colour travels on the feature so nav
 * paints exactly what the planning map painted.
 */
export function overlayLineJson(
  chunks: Chunk[] | null | undefined,
  fallbackColor: string,
): string {
  const features = (chunks || [])
    .map((chunk, i) => {
      const coords = pathToLineCoords(chunk.path);
      if (!coords) return null;
      const color = OVERLAY_KIND_META[chunk.kind || '']?.color || fallbackColor;
      return {
        type: 'Feature' as const,
        properties: { color, run_id: chunk.run_id || `r-${i}` },
        geometry: { type: 'LineString' as const, coordinates: coords },
      };
    })
    .filter(Boolean);
  if (!features.length) return EMPTY_FC;
  return JSON.stringify({ type: 'FeatureCollection', features });
}

export function trafficLineJson(safest: Record<string, unknown> | null | undefined): string {
  const chunks = safest?.[TRAFFIC_OVERLAY.typedKey];
  return overlayLineJson(Array.isArray(chunks) ? chunks : [], TRAFFIC_OVERLAY.hub);
}

export function cyclewayLineJson(safest: Record<string, unknown> | null | undefined): string {
  const chunks = safest?.cycle_typed;
  return overlayLineJson(
    Array.isArray(chunks) ? chunks : [],
    OVERLAY_KIND_META.segregated.color,
  );
}

/** Initial camera bearing — first two points of the route. */
export function initialBearing(path: number[][] | null | undefined): number {
  if (!path || path.length < 2) return 0;
  const [lat1, lon1] = path[0];
  const [lat2, lon2] = path[1];
  const toRad = Math.PI / 180;
  const φ1 = lat1 * toRad;
  const φ2 = lat2 * toRad;
  const Δλ = (lon2 - lon1) * toRad;
  const y = Math.sin(Δλ) * Math.cos(φ2);
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
  const deg = (Math.atan2(y, x) * 180) / Math.PI;
  return (deg + 360) % 360;
}

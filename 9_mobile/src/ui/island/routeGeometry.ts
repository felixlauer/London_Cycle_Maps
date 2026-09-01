/**
 * Distance-along-route mapping for the island (web routeGeometry.js).
 * Route path format is [[lat, lon], ...].
 */

const EARTH_R = 6371000;

export function haversineM(a: number[], b: number[]) {
  const [lat1, lon1] = a;
  const [lat2, lon2] = b;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const s1 = Math.sin(dLat / 2) ** 2
    + Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180)
    * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_R * Math.asin(Math.min(1, Math.sqrt(s1)));
}

function pointKey(lat: number, lon: number) {
  return `${lat.toFixed(5)},${lon.toFixed(5)}`;
}

export type DistanceIndex = {
  points: number[][];
  cum: number[];
  totalM: number;
  nearestDist: (lat: number, lon: number) => number;
};

export function buildDistanceIndex(path: number[][] | null | undefined): DistanceIndex {
  const pts = path || [];
  const cum = new Array(pts.length).fill(0);
  const keyToDist = new Map<string, number>();
  for (let i = 0; i < pts.length; i += 1) {
    if (i > 0) cum[i] = cum[i - 1] + haversineM(pts[i - 1], pts[i]);
    const key = pointKey(pts[i][0], pts[i][1]);
    if (!keyToDist.has(key)) keyToDist.set(key, cum[i]);
  }
  const totalM = pts.length ? cum[cum.length - 1] : 0;

  const nearestDist = (lat: number, lon: number) => {
    const exact = keyToDist.get(pointKey(lat, lon));
    if (exact != null) return exact;
    let best = 0;
    let bestD = Infinity;
    for (let i = 0; i < pts.length; i += 1) {
      const d = haversineM(pts[i], [lat, lon]);
      if (d < bestD) {
        bestD = d;
        best = cum[i];
      }
    }
    return best;
  };

  return { points: pts, cum, totalM, nearestDist };
}

export function chunkSpan(
  chunk: { path?: number[][]; length_m?: number },
  index: DistanceIndex,
) {
  if (!chunk?.path?.length || !index) return null;
  const [lat, lon] = chunk.path[0];
  const d0 = index.nearestDist(lat, lon);
  const len = Number(chunk.length_m) || 0;
  return { d0, d1: Math.min(index.totalM, d0 + len) };
}

export type RouteSlice = {
  d0: number;
  d1: number;
  kind: string;
  runId?: string;
  runIds: (string | undefined)[];
};

export function buildSlices(
  chunks: { path?: number[][]; length_m?: number; kind?: string; run_id?: string }[],
  index: DistanceIndex,
  { minFrac = 0.015, minM = 40 } = {},
): RouteSlice[] {
  if (!chunks?.length || !index?.totalM) return [];
  const minW = Math.max(minM, index.totalM * minFrac);
  const raw = chunks
    .map((c) => {
      const span = chunkSpan(c, index);
      if (!span || !c.kind) return null;
      return { ...span, kind: c.kind, runId: c.run_id };
    })
    .filter(Boolean) as { d0: number; d1: number; kind: string; runId?: string }[];

  raw.sort((a, b) => a.d0 - b.d0);

  const merged: RouteSlice[] = [];
  raw.forEach((s) => {
    const prev = merged[merged.length - 1];
    if (prev && prev.kind === s.kind && s.d0 - prev.d1 < minW * 0.5) {
      prev.d1 = Math.max(prev.d1, s.d1);
      prev.runIds.push(s.runId);
    } else {
      merged.push({ ...s, runIds: [s.runId] });
    }
  });

  return merged.map((s) => {
    let { d0, d1 } = s;
    if (d1 - d0 < minW) {
      const c = (d0 + d1) / 2;
      d0 = Math.max(0, c - minW / 2);
      d1 = Math.min(index.totalM, c + minW / 2);
    }
    return { ...s, d0, d1 };
  });
}

/** Interpolated [lng, lat] at distance d along the route (web lngLatAtDistance). */
export function lngLatAtDistance(index: DistanceIndex | null | undefined, d: number): [number, number] | null {
  if (!index?.points?.length || !index.cum?.length) return null;
  const { points, cum, totalM } = index;
  const target = Math.max(0, Math.min(totalM, d));
  let lo = 0;
  let hi = cum.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (cum[mid] < target) lo = mid + 1;
    else hi = mid;
  }
  const i = Math.max(1, lo);
  const span = cum[i] - cum[i - 1] || 1;
  const t = (target - cum[i - 1]) / span;
  const lat = points[i - 1][0] + (points[i][0] - points[i - 1][0]) * t;
  const lon = points[i - 1][1] + (points[i][1] - points[i - 1][1]) * t;
  return [lon, lat];
}

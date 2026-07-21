/**
 * Distance-along-route mapping for the island: typed chunks and node
 * highlights → x-axis spans, and scrubber distance → map coordinate.
 * Route path format is [[lat, lon], ...] (app convention).
 */

const EARTH_R = 6371000;

export function haversineM(a, b) {
  const [lat1, lon1] = a;
  const [lat2, lon2] = b;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const s1 = Math.sin(dLat / 2) ** 2
    + Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180)
    * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_R * Math.asin(Math.min(1, Math.sqrt(s1)));
}

function pointKey(lat, lon) {
  return `${lat.toFixed(5)},${lon.toFixed(5)}`;
}

/**
 * Cumulative-distance index over the route polyline.
 * keyToDist: rounded "lat,lon" → distance from start (first hit wins).
 */
export function buildDistanceIndex(path) {
  const pts = path || [];
  const cum = new Array(pts.length).fill(0);
  const keyToDist = new Map();
  for (let i = 0; i < pts.length; i += 1) {
    if (i > 0) cum[i] = cum[i - 1] + haversineM(pts[i - 1], pts[i]);
    const key = pointKey(pts[i][0], pts[i][1]);
    if (!keyToDist.has(key)) keyToDist.set(key, cum[i]);
  }
  const totalM = pts.length ? cum[cum.length - 1] : 0;

  const nearestDist = (lat, lon) => {
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

  return { points: pts, cum, totalM, keyToDist, nearestDist };
}

/** Distance-along span { d0, d1 } for a typed chunk. */
export function chunkSpan(chunk, index) {
  if (!chunk?.path?.length || !index) return null;
  const [lat, lon] = chunk.path[0];
  const d0 = index.nearestDist(lat, lon);
  const len = Number(chunk.length_m) || 0;
  return { d0, d1: Math.min(index.totalM, d0 + len) };
}

/** Interpolated [lng, lat] at distance d along the route. */
export function lngLatAtDistance(index, d) {
  const { points, cum, totalM } = index || {};
  if (!points?.length) return null;
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

/**
 * Chunks → x-axis slices with a minimum visible width.
 * Adjacent same-kind runs merge first, then short slices are widened
 * around their centre — avoids many hairline slivers for 15 m runs.
 */
export function buildSlices(chunks, index, { minFrac = 0.015, minM = 40 } = {}) {
  if (!chunks?.length || !index?.totalM) return [];
  const minW = Math.max(minM, index.totalM * minFrac);
  const raw = chunks
    .map((c) => {
      const span = chunkSpan(c, index);
      if (!span) return null;
      return { ...span, kind: c.kind, runId: c.run_id, chunk: c };
    })
    .filter(Boolean)
    .sort((a, b) => a.d0 - b.d0);

  // Merge same-kind slices that touch or overlap after widening.
  const merged = [];
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

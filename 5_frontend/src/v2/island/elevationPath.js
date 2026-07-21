/**
 * Smooth SVG paths from the backend elevation_profile
 * ([{ d_m, elev_m }, ...]). Precision is secondary to a flowing line:
 * moving-average smoothing + Catmull-Rom → cubic beziers.
 */

function movingAverage(values, window) {
  if (window <= 1) return values.slice();
  const half = Math.floor(window / 2);
  return values.map((_, i) => {
    let sum = 0;
    let n = 0;
    for (let j = i - half; j <= i + half; j += 1) {
      if (j >= 0 && j < values.length) {
        sum += values[j];
        n += 1;
      }
    }
    return sum / n;
  });
}

/**
 * Scale profile into pixel points.
 * Returns { points: [[x,y],...], xForD, yForE, dMax, eMin, eMax } or null.
 */
export function scaleProfile(profile, {
  width,
  height,
  padX = 0,
  padTop = 4,
  padBottom = 2,
  smoothWindow = 5,
} = {}) {
  const samples = (profile || []).filter(
    (p) => Number.isFinite(Number(p?.d_m)) && Number.isFinite(Number(p?.elev_m)),
  );
  if (samples.length < 2 || !width || !height) return null;

  const ds = samples.map((p) => Number(p.d_m));
  const es = movingAverage(samples.map((p) => Number(p.elev_m)), smoothWindow);
  const dMax = ds[ds.length - 1] || 1;
  let eMin = Math.min(...es);
  let eMax = Math.max(...es);
  if (eMax - eMin < 8) {
    // Flat route — keep a gentle band instead of a jittery full-height line.
    const mid = (eMax + eMin) / 2;
    eMin = mid - 4;
    eMax = mid + 4;
  }

  const innerW = width - padX * 2;
  const innerH = height - padTop - padBottom;
  const xForD = (d) => padX + (Math.max(0, Math.min(dMax, d)) / dMax) * innerW;
  const yForE = (e) => padTop + (1 - (e - eMin) / (eMax - eMin)) * innerH;
  const points = ds.map((d, i) => [xForD(d), yForE(es[i])]);
  return { points, xForD, yForE, dMax, eMin, eMax };
}

/** Catmull-Rom spline through points → SVG path "M … C …". */
export function smoothLinePath(points) {
  if (!points || points.length < 2) return '';
  const p = points;
  let d = `M ${p[0][0].toFixed(2)} ${p[0][1].toFixed(2)}`;
  for (let i = 0; i < p.length - 1; i += 1) {
    const p0 = p[i - 1] || p[i];
    const p1 = p[i];
    const p2 = p[i + 1];
    const p3 = p[i + 2] || p2;
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C ${c1x.toFixed(2)} ${c1y.toFixed(2)}, ${c2x.toFixed(2)} ${c2y.toFixed(2)}, ${p2[0].toFixed(2)} ${p2[1].toFixed(2)}`;
  }
  return d;
}

/** Line path closed down to the baseline for the gradient area fill. */
export function areaPathFromLine(linePath, points, height) {
  if (!linePath || !points?.length) return '';
  const first = points[0];
  const last = points[points.length - 1];
  return `${linePath} L ${last[0].toFixed(2)} ${height} L ${first[0].toFixed(2)} ${height} Z`;
}

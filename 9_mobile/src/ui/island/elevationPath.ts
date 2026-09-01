/** Smooth SVG paths from elevation_profile ([{ d_m, elev_m }, ...]). */

function movingAverage(values: number[], window: number) {
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

export function scaleProfile(
  profile: { d_m?: number; elev_m?: number }[] | null | undefined,
  {
    width,
    height,
    padX = 0,
    padLeft,
    padRight,
    padTop = 4,
    padBottom = 2,
    smoothWindow = 5,
  }: {
    width: number;
    height: number;
    padX?: number;
    padLeft?: number;
    padRight?: number;
    padTop?: number;
    padBottom?: number;
    smoothWindow?: number;
  },
) {
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
    const mid = (eMax + eMin) / 2;
    eMin = mid - 4;
    eMax = mid + 4;
  }

  const left = padLeft != null ? padLeft : padX;
  const right = padRight != null ? padRight : padX;
  const innerW = width - left - right;
  const innerH = height - padTop - padBottom;
  const xForD = (d: number) => left + (Math.max(0, Math.min(dMax, d)) / dMax) * innerW;
  const yForE = (e: number) => padTop + (1 - (e - eMin) / (eMax - eMin)) * innerH;
  const points = ds.map((d, i) => [xForD(d), yForE(es[i])] as [number, number]);
  return { points, dMax, eMin, eMax, xForD, yForE, padLeft: left, padRight: right };
}

export function smoothLinePath(points: [number, number][]) {
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

export function areaPathFromLine(linePath: string, points: [number, number][], height: number) {
  if (!linePath || !points.length) return '';
  const first = points[0];
  const last = points[points.length - 1];
  return `${linePath} L ${last[0].toFixed(2)} ${height} L ${first[0].toFixed(2)} ${height} Z`;
}

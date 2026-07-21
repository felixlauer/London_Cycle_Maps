import React, { useMemo } from 'react';
import { scaleProfile, smoothLinePath, areaPathFromLine } from './elevationPath';

/** Elevation accent — violet (matches hills / elevation language). */
export const ELEVATION_ACCENT = '#8717BF';

/**
 * Collapsed-slot elevation micro-chart: accent stroke with a glow,
 * gradient area fading to transparent, no axes.
 */
export default function ElevationSparkline({
  profile,
  width = 128,
  height = 48,
  accent = ELEVATION_ACCENT,
  gradientId = 'island-spark-grad',
}) {
  const geo = useMemo(
    () => scaleProfile(profile, { width, height, padX: 2, padTop: 5, padBottom: 3 }),
    [profile, width, height],
  );
  if (!geo) return <div className="island-slot__empty">—</div>;

  const line = smoothLinePath(geo.points);
  const area = areaPathFromLine(line, geo.points, height);

  return (
    <svg
      className="island-spark"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={accent} stopOpacity="0.28" />
          <stop offset="100%" stopColor={accent} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradientId})`} stroke="none" />
      <path
        d={line}
        fill="none"
        stroke={accent}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="island-glow-stroke"
        style={{ color: accent }}
      />
    </svg>
  );
}

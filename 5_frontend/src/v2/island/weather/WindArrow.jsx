import React from 'react';
import { WIND_ARROW_COLORS, windArrowRotateDeg } from './weatherMap';

/**
 * Dual-tone wind arrow from cursor-arrow-4200.svg geometry.
 * Default tip is NE (+45°); rotate(wind_from - 45) faces wind-FROM.
 */
export default function WindArrow({ windFromDeg = 0, band = 'moderate', size = 36 }) {
  const colors = WIND_ARROW_COLORS[band] || WIND_ARROW_COLORS.moderate;
  const rotate = windArrowRotateDeg(windFromDeg);

  return (
    <svg
      className="island-weather__arrow"
      width={size}
      height={size}
      viewBox="0 0 256 256"
      aria-hidden
      style={{
        '--wind-fill-a': colors.a,
        '--wind-fill-b': colors.b,
        transform: `rotate(${rotate}deg)`,
      }}
    >
      <g transform="translate(1.4065934065934016 1.4065934065934016) scale(2.81 2.81)">
        <path
          fill="var(--wind-fill-a)"
          d="M 89.404 0.596 c -0.559 -0.559 -1.433 -0.801 -2.288 -0.391 L 1.504 41.248 c -1.821 0.873 -2.044 3.364 -0.362 4.041 l 25.589 10.293 c 1.751 0.704 3.32 1.75 4.628 3.058 C 52.293 43.882 71.426 23.911 89.404 0.596 z"
        />
        <path
          fill="var(--wind-fill-b)"
          d="M 89.404 0.596 c 0.559 0.559 0.801 1.433 0.391 2.288 L 48.752 88.496 c -0.873 1.821 -3.364 2.044 -4.041 0.362 L 34.417 63.269 c -0.704 -1.751 -1.75 -3.32 -3.058 -4.628 L 89.404 0.596 z"
        />
      </g>
    </svg>
  );
}

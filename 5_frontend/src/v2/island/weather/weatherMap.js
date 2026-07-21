/**
 * WMO weather_code → Meteocons fill slug + short label.
 * Day/night variants where Bas provides them.
 */
import clearDay from '@meteocons/svg-static/fill/clear-day.svg';
import clearNight from '@meteocons/svg-static/fill/clear-night.svg';
import partlyCloudyDay from '@meteocons/svg-static/fill/partly-cloudy-day.svg';
import partlyCloudyNight from '@meteocons/svg-static/fill/partly-cloudy-night.svg';
import overcast from '@meteocons/svg-static/fill/overcast.svg';
import fog from '@meteocons/svg-static/fill/fog.svg';
import drizzle from '@meteocons/svg-static/fill/drizzle.svg';
import rain from '@meteocons/svg-static/fill/rain.svg';
import snow from '@meteocons/svg-static/fill/snow.svg';
import thunderstorms from '@meteocons/svg-static/fill/thunderstorms.svg';
import hail from '@meteocons/svg-static/fill/hail.svg';
import cloudy from '@meteocons/svg-static/fill/cloudy.svg';

/** Calm / no-wind — Bas windsock-calm (green cue). */
export { default as windsockCalm } from '@meteocons/svg-static/fill/windsock-calm.svg';
/** Plain thermometer (no °C mark) — sits as the unit glyph beside the temp. */
export { default as thermometer } from '@meteocons/svg-static/fill/thermometer.svg';
export { default as thermometerColder } from '@meteocons/svg-static/fill/thermometer-colder.svg';
export { default as thermometerWarmer } from '@meteocons/svg-static/fill/thermometer-warmer.svg';

const DAY_NIGHT = {
  clear: { day: clearDay, night: clearNight, labelDay: 'Clear', labelNight: 'Clear' },
  partly: {
    day: partlyCloudyDay,
    night: partlyCloudyNight,
    labelDay: 'Partly cloudy',
    labelNight: 'Partly cloudy',
  },
  fog: { day: fog, night: fog, labelDay: 'Fog', labelNight: 'Fog' },
};

/**
 * @param {number|null|undefined} code WMO weather_code
 * @param {boolean} isDay
 * @returns {{ src: string, label: string }}
 */
export function wmoToMeteocon(code, isDay = true) {
  const c = Number(code);
  const day = Boolean(isDay);

  const dn = (key) => {
    const e = DAY_NIGHT[key];
    return {
      src: day ? e.day : e.night,
      label: day ? e.labelDay : e.labelNight,
    };
  };

  if (c === 0) return dn('clear');
  if (c === 1) {
    return {
      src: day ? clearDay : clearNight,
      label: 'Mostly clear',
    };
  }
  if (c === 2) return dn('partly');
  if (c === 3) return { src: overcast, label: 'Overcast' };
  if (c === 45 || c === 48) return dn('fog');
  if (c === 51 || c === 53 || c === 55 || c === 56 || c === 57) {
    return { src: drizzle, label: 'Drizzle' };
  }
  if (c === 61 || c === 63 || c === 65 || c === 66 || c === 67) {
    return { src: rain, label: c >= 65 ? 'Heavy rain' : 'Rain' };
  }
  if (c === 71 || c === 73 || c === 75 || c === 77) {
    return { src: snow, label: 'Snow' };
  }
  if (c === 80 || c === 81 || c === 82) {
    return { src: rain, label: 'Showers' };
  }
  if (c === 85 || c === 86) {
    return { src: snow, label: 'Snow showers' };
  }
  if (c === 95) return { src: thunderstorms, label: 'Thunderstorm' };
  if (c === 96 || c === 99) return { src: hail, label: 'Thunder + hail' };

  return { src: cloudy, label: 'Cloudy' };
}

const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];

/** 8-point compass from meteorological wind-from degrees. */
export function compassFromDeg(deg) {
  const d = ((Number(deg) % 360) + 360) % 360;
  const i = Math.round(d / 45) % 8;
  return COMPASS[i];
}

/**
 * CSS rotate for cursor-arrow-4200.svg.
 * Default tip is +45° (NE). Tip points wind-FROM: rotate(wind_from - 45).
 */
export function windArrowRotateDeg(windFromDeg) {
  return Number(windFromDeg) - 45;
}

export const WIND_CALM_MS = 1.5;
export const WIND_EXTREME_MS = 10;
export const TEMP_COLD_C = 5;
export const TEMP_HOT_C = 28;

/**
 * @param {number|null|undefined} ms
 * @returns {{ band: 'calm'|'moderate'|'extreme', label: string }}
 */
export function classifyWind(ms) {
  const v = Number(ms);
  if (!Number.isFinite(v) || v < WIND_CALM_MS) {
    return { band: 'calm', label: 'No wind' };
  }
  if (v > WIND_EXTREME_MS) {
    return { band: 'extreme', label: 'Strong wind' };
  }
  return { band: 'moderate', label: 'Moderate wind' };
}

/**
 * @param {number|null|undefined} c
 * @returns {{ warn: null|'cold'|'hot', thermometer: 'plain'|'colder'|'warmer', warningLabel: string|null }}
 */
export function classifyTemp(c) {
  const t = Number(c);
  if (!Number.isFinite(t)) {
    return { warn: null, thermometer: 'plain', warningLabel: null };
  }
  if (t <= TEMP_COLD_C) {
    return { warn: 'cold', thermometer: 'colder', warningLabel: 'Very cold' };
  }
  if (t >= TEMP_HOT_C) {
    return { warn: 'hot', thermometer: 'warmer', warningLabel: 'Very hot' };
  }
  return { warn: null, thermometer: 'plain', warningLabel: null };
}

/**
 * UV caption under the temp hero. Night / zero → "No UV".
 * @param {number|null|undefined} uv
 * @param {boolean} isDay
 */
export function formatUvCaption(uv, isDay = true) {
  if (!isDay) return 'No UV';
  const v = Number(uv);
  if (!Number.isFinite(v) || v <= 0) return 'No UV';
  const rounded = Math.round(v * 10) / 10;
  const display = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
  return `UV ${display}`;
}

/** Dual-tone pairs for WindArrow (fill-a, fill-b). */
export const WIND_ARROW_COLORS = {
  calm: { a: '#1f9a80', b: '#26b99a' },
  moderate: { a: '#3d8bc9', b: '#4D9DE0' },
  extreme: { a: '#d97804', b: '#F18805' },
};

/**
 * Single extreme-weather warning for the expanded island.
 * Priority (first match wins): thunderstorm → black ice → heavy snow →
 * violent rain → dense fog → strong wind → heat.
 */
import thunderstorms from '@meteocons/svg-static/fill/thunderstorms.svg';
import thunderstormsHail from '@meteocons/svg-static/fill/thunderstorms-hail.svg';
import sleet from '@meteocons/svg-static/fill/sleet.svg';
import extremeSnow from '@meteocons/svg-static/fill/extreme-snow.svg';
import extremeRain from '@meteocons/svg-static/fill/extreme-rain.svg';
import extremeFog from '@meteocons/svg-static/fill/extreme-fog.svg';
import wind from '@meteocons/svg-static/fill/wind.svg';
import thermometerSun from '@meteocons/svg-static/fill/thermometer-sun.svg';

import { compassFromDeg, formatUvCaption, WIND_EXTREME_MS, TEMP_HOT_C } from './weatherMap';

const THUNDER = new Set([95, 96, 99]);
const THUNDER_HAIL = new Set([96, 99]);
const BLACK_ICE = new Set([56, 57, 66, 67]);
const HEAVY_SNOW = new Set([75, 86]);
const VIOLENT_RAIN = new Set([65, 82]);
const DENSE_FOG = new Set([45, 48]);

function windDetail(speedMs, dirDeg) {
  const speed = `${Math.round(Number(speedMs))} m/s`;
  if (!Number.isFinite(Number(dirDeg))) return speed;
  return `${speed} · ${compassFromDeg(dirDeg)}`;
}

function tempPhrase(tempC) {
  const t = Number(tempC);
  if (!Number.isFinite(t)) return null;
  return `${Math.round(t)}°C`;
}

/**
 * @typedef {object} ExtremeWarning
 * @property {string} kind
 * @property {string} iconSrc
 * @property {string} title — condition headline (large)
 * @property {string} detail — supporting line (smaller)
 * @property {string} action — rider recommendation
 */

/**
 * @param {object|null|undefined} weather
 * @returns {ExtremeWarning | null}
 */
export function resolveExtremeWarning(weather) {
  if (!weather) return null;

  const code = Number(weather.weather_code);

  if (Number.isFinite(code) && THUNDER.has(code)) {
    const hail = THUNDER_HAIL.has(code);
    return {
      kind: 'thunderstorm',
      iconSrc: hail ? thunderstormsHail : thunderstorms,
      title: hail ? 'Thunder + hail' : 'Thunderstorm',
      detail: hail
        ? 'Hail and lightning in the area'
        : 'Lightning and heavy showers nearby',
      action: hail
        ? 'Stop and find cover immediately'
        : 'Seek shelter and avoid open routes',
    };
  }

  if (Number.isFinite(code) && BLACK_ICE.has(code)) {
    const temp = tempPhrase(weather.temp_c);
    return {
      kind: 'blackIce',
      iconSrc: sleet,
      title: 'Black ice risk',
      detail: temp
        ? `Freezing rain · surfaces may be icy (${temp})`
        : 'Freezing rain · surfaces may be icy',
      action: 'Brake early and avoid sharp turns',
    };
  }

  if (Number.isFinite(code) && HEAVY_SNOW.has(code)) {
    const temp = tempPhrase(weather.temp_c);
    return {
      kind: 'heavySnow',
      iconSrc: extremeSnow,
      title: 'Heavy snow',
      detail: temp
        ? `Accumulating snow on route (${temp})`
        : 'Accumulating snow on route',
      action: 'Lower speed and use lights',
    };
  }

  if (Number.isFinite(code) && VIOLENT_RAIN.has(code)) {
    return {
      kind: 'violentRain',
      iconSrc: extremeRain,
      title: 'Violent rain',
      detail: 'Very heavy rainfall expected',
      action: 'Use lights and allow extra braking distance',
    };
  }

  if (Number.isFinite(code) && DENSE_FOG.has(code)) {
    return {
      kind: 'denseFog',
      iconSrc: extremeFog,
      title: 'Dense fog',
      detail: 'Visibility highly reduced (< 200 m)',
      action: 'Use lights and reduce speed',
    };
  }

  const windMs = Number(weather.wind_speed_ms);
  if (Number.isFinite(windMs) && windMs > WIND_EXTREME_MS) {
    return {
      kind: 'strongWind',
      iconSrc: wind,
      title: 'Strong wind',
      detail: windDetail(windMs, weather.wind_dir_deg),
      action: 'Grip handlebars and watch for gusts',
    };
  }

  const temp = Number(weather.temp_c);
  const isDay = Boolean(weather.is_day);
  if (isDay && Number.isFinite(temp) && temp >= TEMP_HOT_C) {
    const uv = formatUvCaption(weather.uv_index, true);
    return {
      kind: 'heat',
      iconSrc: thermometerSun,
      title: 'Extreme heat',
      detail: `${Math.round(temp)}°C · ${uv}`,
      action: 'Carry water and plan shade breaks',
    };
  }

  return null;
}

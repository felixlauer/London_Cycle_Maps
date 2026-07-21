/**
 * Display units — backend stays in metres; convert only for UI strings.
 */
export const UNITS_STORAGE_KEY = 'tuned_ui_units';

export function readStoredUnits() {
  try {
    const v = localStorage.getItem(UNITS_STORAGE_KEY);
    if (v === 'imperial' || v === 'metric') return v;
  } catch {
    /* ignore */
  }
  return 'metric';
}

export function writeStoredUnits(units) {
  try {
    localStorage.setItem(UNITS_STORAGE_KEY, units);
  } catch {
    /* ignore */
  }
}

/** @param {number} metres @param {'metric'|'imperial'} units */
export function formatDistance(metres, units = 'metric') {
  const m = Number(metres) || 0;
  if (units === 'imperial') {
    const miles = m / 1609.344;
    if (miles < 0.1) {
      const ft = Math.round(m / 0.3048);
      return `${ft} ft`;
    }
    return `${miles < 10 ? miles.toFixed(1) : Math.round(miles)} mi`;
  }
  if (m < 1000) return `${Math.round(m)} m`;
  const km = m / 1000;
  return `${km < 10 ? km.toFixed(1) : Math.round(km)} km`;
}

/** @param {number} metres @param {'metric'|'imperial'} units */
export function formatElevation(metres, units = 'metric') {
  const m = Number(metres) || 0;
  if (units === 'imperial') {
    return `${Math.round(m / 0.3048)} ft`;
  }
  return `${Math.round(m)} m`;
}

/**
 * Display units — backend stays in metres; convert only for UI strings.
 * Prefs persist via SecureStore (same keys as web localStorage).
 */
import * as SecureStore from 'expo-secure-store';

export const UNITS_STORAGE_KEY = 'tuned_ui_units';
export type UnitsPref = 'metric' | 'imperial';

let memoryUnits: UnitsPref | null = null;

export async function loadStoredUnits(): Promise<UnitsPref> {
  if (memoryUnits) return memoryUnits;
  try {
    const v = await SecureStore.getItemAsync(UNITS_STORAGE_KEY);
    if (v === 'imperial' || v === 'metric') {
      memoryUnits = v;
      return v;
    }
  } catch {
    /* ignore */
  }
  memoryUnits = 'metric';
  return 'metric';
}

export function peekUnits(): UnitsPref {
  return memoryUnits || 'metric';
}

export async function writeStoredUnits(units: UnitsPref): Promise<void> {
  memoryUnits = units;
  try {
    await SecureStore.setItemAsync(UNITS_STORAGE_KEY, units);
  } catch {
    /* ignore */
  }
}

export function formatDistance(metres: number, units: UnitsPref = 'metric'): string {
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

export function formatElevation(metres: number, units: UnitsPref = 'metric'): string {
  const m = Number(metres) || 0;
  if (units === 'imperial') {
    return `${Math.round(m / 0.3048)} ft`;
  }
  return `${Math.round(m)} m`;
}

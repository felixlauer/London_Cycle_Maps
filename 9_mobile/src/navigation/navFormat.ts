export type Units = 'metric' | 'imperial';

/**
 * Maneuver countdown — coarse steps far out, exact metres when the turn is close.
 * Mirrors how Google reads: "600 m", "250 m", "80 m", "now".
 */
export function formatManeuverDistance(metres: number, units: Units = 'metric'): string {
  const m = Math.max(0, Number(metres) || 0);
  if (units === 'imperial') {
    const feet = m / 0.3048;
    if (feet < 50) return 'Now';
    if (feet < 1000) return `${Math.round(feet / 10) * 10} ft`;
    const miles = m / 1609.344;
    return `${miles < 10 ? miles.toFixed(1) : Math.round(miles)} mi`;
  }
  if (m < 15) return 'Now';
  if (m < 100) return `${Math.round(m / 10) * 10} m`;
  if (m < 1000) return `${Math.round(m / 50) * 50} m`;
  return `${(m / 1000).toFixed(1)} km`;
}

export function formatRemainingDistance(metres: number, units: Units = 'metric'): {
  value: string;
  unit: string;
} {
  const m = Math.max(0, Number(metres) || 0);
  if (units === 'imperial') {
    const miles = m / 1609.344;
    if (miles < 0.1) return { value: String(Math.round(m / 0.3048)), unit: 'ft' };
    return { value: miles < 10 ? miles.toFixed(1) : String(Math.round(miles)), unit: 'mi' };
  }
  if (m < 1000) return { value: String(Math.round(m)), unit: 'm' };
  return { value: (m / 1000).toFixed(1), unit: 'km' };
}

export function formatRemainingDuration(seconds: number): { value: string; unit: string } {
  const s = Math.max(0, Number(seconds) || 0);
  const mins = Math.round(s / 60);
  if (mins < 60) return { value: String(Math.max(1, mins)), unit: 'min' };
  const hours = Math.floor(mins / 60);
  const rest = mins % 60;
  return { value: rest ? `${hours}:${String(rest).padStart(2, '0')}` : String(hours), unit: rest ? 'h' : 'hr' };
}

export function formatEta(seconds: number, now: Date = new Date()): string {
  const s = Math.max(0, Number(seconds) || 0);
  const eta = new Date(now.getTime() + s * 1000);
  const hh = String(eta.getHours()).padStart(2, '0');
  const mm = String(eta.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

/** Step-list distance ("in 240 m") — always the step's own length. */
export function formatStepDistance(metres: number, units: Units = 'metric'): string {
  const m = Math.max(0, Number(metres) || 0);
  if (units === 'imperial') {
    const feet = m / 0.3048;
    if (feet < 1000) return `${Math.round(feet / 10) * 10} ft`;
    return `${(m / 1609.344).toFixed(1)} mi`;
  }
  if (m < 1000) return `${Math.round(m)} m`;
  return `${(m / 1000).toFixed(1)} km`;
}

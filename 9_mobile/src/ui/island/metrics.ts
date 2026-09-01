/** Big-number metric formatting for the Dynamic Island. */

export function formatDurationParts(durationMin: number | undefined | null) {
  const mins = Math.max(0, Math.round(Number(durationMin) || 0));
  if (mins < 60) {
    return { value: String(mins), unit: 'min' };
  }
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return { value: `${h}:${String(m).padStart(2, '0')}`, unit: 'h' };
}

export function formatDistanceParts(metres: number | undefined | null, units: 'metric' | 'imperial' = 'metric') {
  const m = Number(metres) || 0;
  if (units === 'imperial') {
    const miles = m / 1609.344;
    if (miles < 0.1) {
      return { value: String(Math.round(m / 0.3048)), unit: 'ft' };
    }
    return { value: miles < 10 ? miles.toFixed(1) : String(Math.round(miles)), unit: 'mi' };
  }
  if (m < 1000) return { value: String(Math.round(m)), unit: 'm' };
  const km = m / 1000;
  return { value: km < 10 ? km.toFixed(1) : String(Math.round(km)), unit: 'km' };
}

export function tripLengthM(stats?: { length_m?: number; distance_m?: number } | null) {
  if (!stats) return 0;
  return Number(stats.length_m ?? stats.distance_m) || 0;
}

/** Split walk labels for Santander metrics (web formatWalkParts). */
export function formatWalkParts(
  durationMin: number | null | undefined,
  distanceM: number | null | undefined,
  units: 'metric' | 'imperial' = 'metric',
) {
  const mins = Number(durationMin);
  const dist = Number(distanceM);
  const hasMin = Number.isFinite(mins) && mins > 0;
  const hasDist = Number.isFinite(dist) && dist > 0;
  if (!hasMin && !hasDist) return null;

  let distanceLabel: string | null = null;
  if (hasDist) {
    if (units === 'imperial') {
      const miles = dist / 1609.344;
      distanceLabel = miles < 0.1
        ? `${Math.round(dist / 0.3048)} ft`
        : `${miles < 10 ? miles.toFixed(1) : Math.round(miles)} mi`;
    } else if (dist < 1000) {
      distanceLabel = `${Math.round(dist)} m`;
    } else {
      distanceLabel = `${(dist / 1000).toFixed(1)} km`;
    }
  }

  return {
    time: hasMin ? `+ ${Math.max(1, Math.round(mins))} min walk` : null,
    distance: distanceLabel ? `+ ${distanceLabel} walk` : null,
  };
}

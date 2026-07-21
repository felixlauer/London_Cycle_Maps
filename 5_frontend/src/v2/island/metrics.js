/** Big-number metric formatting for the Dynamic Island. */

/** duration_min → { value, unit } — "34" min or "1:14" h. */
export function formatDurationParts(durationMin) {
  const mins = Math.max(0, Math.round(Number(durationMin) || 0));
  if (mins < 60) {
    return { value: String(mins), unit: 'min' };
  }
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return { value: `${h}:${String(m).padStart(2, '0')}`, unit: 'h' };
}

/** length_m → { value, unit } respecting units preference. */
export function formatDistanceParts(metres, units = 'metric') {
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

/** Signed comparison vs shortest, e.g. "+4 min vs shortest". */
export function formatTimeDelta(safestMin, fastestMin) {
  const a = Number(safestMin);
  const b = Number(fastestMin);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  const delta = Math.round(a - b);
  if (delta === 0) return 'same as shortest';
  const sign = delta > 0 ? '+' : '−';
  return `${sign}${Math.abs(delta)} min vs shortest`;
}

/** Signed distance comparison vs shortest. */
export function formatDistanceDelta(safestM, fastestM, units = 'metric') {
  const a = Number(safestM);
  const b = Number(fastestM);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  const deltaM = a - b;
  if (Math.abs(deltaM) < 25) return 'same as shortest';
  const sign = deltaM > 0 ? '+' : '−';
  const abs = Math.abs(deltaM);
  if (units === 'imperial') {
    const miles = abs / 1609.344;
    if (miles < 0.1) return `${sign}${Math.round(abs / 0.3048)} ft vs shortest`;
    return `${sign}${miles.toFixed(1)} mi vs shortest`;
  }
  if (abs < 1000) return `${sign}${Math.round(abs)} m vs shortest`;
  return `${sign}${(abs / 1000).toFixed(1)} km vs shortest`;
}

/** Split walk labels for Santander metrics: time above duration, distance above length. */
export function formatWalkParts(durationMin, distanceM, units = 'metric') {
  const mins = Number(durationMin);
  const dist = Number(distanceM);
  const hasMin = Number.isFinite(mins) && mins > 0;
  const hasDist = Number.isFinite(dist) && dist > 0;
  if (!hasMin && !hasDist) return null;

  let distanceLabel = null;
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

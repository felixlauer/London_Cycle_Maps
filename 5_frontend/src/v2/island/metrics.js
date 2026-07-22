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

const COMPARE_LABEL = {
  shortest: 'shortest',
  'non-tuned': 'non-tuned route',
};

function compareSuffix(compare = 'shortest') {
  return COMPARE_LABEL[compare] || COMPARE_LABEL.shortest;
}

function signedDelta(sign, magnitude, compare) {
  const vs = compareSuffix(compare);
  if (compare === 'non-tuned') {
    return `${sign} ${magnitude} vs ${vs}`;
  }
  return `${sign}${magnitude} vs ${vs}`;
}

/** Signed comparison vs fastest route — desktop: "vs shortest"; mobile expanded: "vs non-tuned route". */
export function formatTimeDelta(safestMin, fastestMin, { compare = 'shortest' } = {}) {
  const a = Number(safestMin);
  const b = Number(fastestMin);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  const delta = Math.round(a - b);
  const vs = compareSuffix(compare);
  if (delta === 0) return `same as ${vs}`;
  const sign = delta > 0 ? '+' : '−';
  return signedDelta(sign, `${Math.abs(delta)} min`, compare);
}

/** Signed distance comparison vs fastest route. */
export function formatDistanceDelta(safestM, fastestM, units = 'metric', { compare = 'shortest' } = {}) {
  const a = Number(safestM);
  const b = Number(fastestM);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  const deltaM = a - b;
  const vs = compareSuffix(compare);
  if (Math.abs(deltaM) < 25) return `same as ${vs}`;
  const sign = deltaM > 0 ? '+' : '−';
  const abs = Math.abs(deltaM);
  if (units === 'imperial') {
    const miles = abs / 1609.344;
    if (miles < 0.1) {
      return signedDelta(sign, `${Math.round(abs / 0.3048)} ft`, compare);
    }
    return signedDelta(sign, `${miles.toFixed(1)} mi`, compare);
  }
  if (abs < 1000) return signedDelta(sign, `${Math.round(abs)} m`, compare);
  return signedDelta(sign, `${(abs / 1000).toFixed(1)} km`, compare);
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

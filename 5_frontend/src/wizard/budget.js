/**
 * Budget helpers: estimated detour minutes per slider value, derived from
 * preset_config.json anchors (independent single-weight sweep data).
 *
 * Totals are a linear-sum approximation - weights interact, so the UI always
 * labels them "Estimated detour" (see plan review notes).
 */

export const EPSILON = 0.0001;

/** Linear interpolation of anchor minute costs at an arbitrary slider value. */
export function interpMinutes(anchors, value, bikeType) {
  if (!anchors?.length) return 0;
  const minutesAt = (a) => a.minutes_by_bike?.[bikeType] ?? 0;
  if (value <= anchors[0].value) return minutesAt(anchors[0]);
  for (let i = 0; i < anchors.length - 1; i += 1) {
    const lo = anchors[i];
    const hi = anchors[i + 1];
    if (value <= hi.value) {
      const span = hi.value - lo.value;
      const t = span > 0 ? (value - lo.value) / span : 0;
      return minutesAt(lo) + t * (minutesAt(hi) - minutesAt(lo));
    }
  }
  return minutesAt(anchors[anchors.length - 1]);
}

/** Estimated detour minutes for one slider at the given value. */
export function sliderMinutes(sliderCfg, value, bikeType) {
  if (!sliderCfg || value <= EPSILON) return 0;
  return interpMinutes(sliderCfg.anchors, value, bikeType);
}

/** Linear-sum estimate across all sliders (rounded to 0.5 min). */
export function totalMinutes(sliders, weights, bikeType) {
  let total = 0;
  Object.entries(sliders || {}).forEach(([key, cfg]) => {
    total += sliderMinutes(cfg, weights[key] ?? 0, bikeType);
  });
  return roundHalf(total);
}

export function roundHalf(n) {
  return Math.round(n * 2) / 2;
}

/** Metric change label for an anchor ("~46% fewer signals" / "+12 pts segregated"). */
export function metricChangeLabel(sliderCfg, anchor) {
  if (!anchor || !anchor.metric_change_pct) return '';
  const v = anchor.metric_change_pct;
  if (sliderCfg.metric_direction === 'decrease') {
    return `~${Math.round(v)}% less`;
  }
  return `+${Math.round(v)} pts`;
}

/** Conflict warnings whose trigger conditions the current weights satisfy. */
export function activeConflictWarnings(warnings, weights) {
  return (warnings || []).filter((cw) => {
    const trigger = cw.trigger || {};
    const keys = Object.keys(trigger);
    if (!keys.length) return false;
    return keys.every((key) => {
      const cond = trigger[key];
      const val = weights[key] ?? 0;
      if (cond.gte !== undefined && !(val >= cond.gte)) return false;
      if (cond.lt !== undefined && !(val < cond.lt)) return false;
      return true;
    });
  });
}

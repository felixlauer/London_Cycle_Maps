/**
 * Budget helpers — port of web wizard/budget.js.
 * Estimated detour minutes from preset_config slider anchors.
 */

export const EPSILON = 0.0001;

export type SliderAnchor = {
  value: number;
  minutes_by_bike?: Record<string, number>;
  metric_change_pct?: number;
};

export type SliderCfg = {
  label?: string;
  question?: string;
  help?: string;
  cap?: number;
  target_metric?: string;
  metric_direction?: 'decrease' | 'increase' | string;
  anchors?: SliderAnchor[];
};

/** Linear interpolation of anchor minute costs at an arbitrary slider value. */
export function interpMinutes(
  anchors: SliderAnchor[] | undefined,
  value: number,
  bikeType: string,
): number {
  if (!anchors?.length) return 0;
  const minutesAt = (a: SliderAnchor) => a.minutes_by_bike?.[bikeType] ?? 0;
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

export function sliderMinutes(
  sliderCfg: SliderCfg | undefined,
  value: number,
  bikeType: string,
): number {
  if (!sliderCfg || value <= EPSILON) return 0;
  return interpMinutes(sliderCfg.anchors, value, bikeType);
}

export function roundHalf(n: number): number {
  return Math.round(n * 2) / 2;
}

/** Linear-sum estimate across all sliders (rounded to 0.5 min). */
export function totalMinutes(
  sliders: Record<string, SliderCfg> | undefined,
  weights: Record<string, number>,
  bikeType: string,
): number {
  let total = 0;
  Object.entries(sliders || {}).forEach(([key, cfg]) => {
    total += sliderMinutes(cfg, weights[key] ?? 0, bikeType);
  });
  return roundHalf(total);
}

export function metricChangeLabel(
  sliderCfg: SliderCfg,
  anchor: SliderAnchor,
): string {
  if (!anchor || anchor.metric_change_pct == null) return '';
  const v = anchor.metric_change_pct;
  if (sliderCfg.metric_direction === 'decrease') {
    return `~${Math.round(v)}% less`;
  }
  return `+${Math.round(v)} pts`;
}

type ConflictWarning = {
  trigger?: Record<string, { gte?: number; lt?: number }>;
  weights?: string[];
  winner?: string;
  warning?: string;
};

export function activeConflictWarnings(
  warnings: ConflictWarning[] | undefined,
  weights: Record<string, number>,
): ConflictWarning[] {
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

/**
 * Fast-only time-saving estimates — port of web wizard/fastSavings.js.
 * UI framing only; does not affect routing.
 */

import {
  EPSILON,
  roundHalf,
  sliderMinutes,
  totalMinutes,
  type SliderCfg,
} from './budget';

export const FAST_BASELINES: Record<string, number> = {
  signal_count: 71.09,
  junction_count: 26.45,
  calming_count: 15.36,
  barrier_penalty_count: 6.36,
  elevation_gain: 75.64,
};

export const FAST_SECONDS_PER_UNIT: Record<string, number> = {
  signal_count: 7.5,
  junction_count: 10,
  calming_count: 4,
  barrier_penalty_count: 20,
  elevation_gain: 2.58,
};

export const FAST_SECONDS_PER_PCT_POINT: Record<string, number> = {
  green_pct: 4,
  vehicular_free_pct: 8,
  tfl_cycleway_pct: 3,
  speed_stress_pct: 0,
  accidents: 0,
};

export const FAST_SLIDER_QUESTIONS: Record<string, string> = {
  signal_weight: 'Hunt harder for fewer traffic lights to save time?',
  junction_weight: 'Hunt harder for fewer stop-and-go junctions?',
  hill_weight: 'Prefer flatter ground even if the path wiggles?',
  calming_weight: 'Avoid speed bumps that break your rhythm?',
  barrier_weight: 'Avoid gates and squeeze points that force a stop?',
  vehicular_free_weight: 'Favour segregated paths you can ride faster on?',
  tfl_cycleway_weight: 'Stick to signed TfL corridors for smoother flow?',
  green_weight: 'Use parks and riverside paths when they keep you rolling?',
  speed_weight: 'Avoid roads with fast motor traffic? (comfort — little clock-time effect)',
  risk_weight: 'Prefer safer corridors? (safety — not counted as time saved)',
};

export const FAST_SLIDER_NOTES: Record<string, string> = {
  green_weight:
    'Scenic pulls can still help when they replace stop-start streets; the estimate is modest.',
  speed_weight:
    'Left on so you can tune comfort. It does not add to estimated time saved.',
  risk_weight:
    'Left on so you can tune safety. It does not add to estimated time saved.',
};

function interpMetricPct(anchors: SliderCfg['anchors'], value: number): number {
  if (!anchors?.length) return 0;
  const pctAt = (a: NonNullable<SliderCfg['anchors']>[number]) => a.metric_change_pct ?? 0;
  if (value <= anchors[0].value) return pctAt(anchors[0]);
  for (let i = 0; i < anchors.length - 1; i += 1) {
    const lo = anchors[i];
    const hi = anchors[i + 1];
    if (value <= hi.value) {
      const span = hi.value - lo.value;
      const t = span > 0 ? (value - lo.value) / span : 0;
      return pctAt(lo) + t * (pctAt(hi) - pctAt(lo));
    }
  }
  return pctAt(anchors[anchors.length - 1]);
}

export function sliderSaveMinutes(
  sliderCfg: SliderCfg | undefined,
  value: number,
): number {
  if (!sliderCfg || value <= EPSILON) return 0;
  const metric = sliderCfg.target_metric || '';
  const pct = interpMetricPct(sliderCfg.anchors, value);
  if (pct <= 0) return 0;

  if (metric in FAST_BASELINES && sliderCfg.metric_direction === 'decrease') {
    const avoided = FAST_BASELINES[metric] * (pct / 100);
    const seconds = avoided * (FAST_SECONDS_PER_UNIT[metric] ?? 0);
    return seconds / 60;
  }

  if (metric in FAST_SECONDS_PER_PCT_POINT) {
    return (pct * FAST_SECONDS_PER_PCT_POINT[metric]) / 60;
  }

  return 0;
}

export function totalSaveMinutes(
  sliders: Record<string, SliderCfg> | undefined,
  weights: Record<string, number>,
  { hillDisabled = false }: { hillDisabled?: boolean } = {},
): number {
  let total = 0;
  Object.entries(sliders || {}).forEach(([key, cfg]) => {
    if (key === 'hill_weight' && hillDisabled) return;
    total += sliderSaveMinutes(cfg, weights[key] ?? 0);
  });
  return roundHalf(total);
}

export function seedFastBudget(
  sliders: Record<string, SliderCfg> | undefined,
  weights: Record<string, number>,
  bikeRules: Record<string, unknown> = {},
): number {
  const used = totalSaveMinutes(sliders, weights, {
    hillDisabled: Boolean(bikeRules.hill_weight_epsilon),
  });
  return Math.max(5, Math.ceil(used || 5));
}

export function totalDistanceCostMinutes(
  sliders: Record<string, SliderCfg> | undefined,
  weights: Record<string, number>,
  bikeType: string,
): number {
  return totalMinutes(sliders, weights, bikeType);
}

export function sliderDistanceCostMinutes(
  sliderCfg: SliderCfg | undefined,
  value: number,
  bikeType: string,
): number {
  return sliderMinutes(sliderCfg, value, bikeType);
}

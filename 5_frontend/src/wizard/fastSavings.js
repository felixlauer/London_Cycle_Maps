/**
 * Fast-only time-saving estimates for the v2 profile wizard (Model A).
 *
 * save_min ≈ improvement(metric) × seconds_per_unit / 60
 *
 * Count baselines: mean @ multiplier 0.0 from
 * `6_verification/parameter_sweeps/2026-06-19` (11 routes, 12.61 km mean).
 * Signal seconds: aligned with app.SIGNAL_WAIT_SECONDS / PENALTY_SECONDS (7.5s
 * hybrid ~15% trip-share) — not raw 25s or literature 18–19s/intersection.
 *
 * Does not affect routing; UI framing only (same honesty class as detour budget).
 */

import { EPSILON, roundHalf, sliderMinutes, totalMinutes } from './budget';

/**
 * Absolute baseline units at multiplier 0.0 on the 11 verification routes
 * (mean length 12.61 km). Source: `6_verification/parameter_sweeps/2026-06-19`
 * — each metric taken from that weight’s own sweep JSON `@ multiplier 0.0`.
 */
export const FAST_BASELINES = {
  signal_count: 71.09,
  junction_count: 26.45,
  calming_count: 15.36,
  barrier_penalty_count: 6.36,
  elevation_gain: 75.64, // metres climb
};

/**
 * Seconds per avoided unit.
 *
 * signal_count: 7.5s per signal-cluster *entry* — aligned with
 * `app.SIGNAL_WAIT_SECONDS` and `route_time_estimate.PENALTY_SECONDS.signal`
 * (Phase 1 remodel; hybrid ~15% trip-share). Literature ~18–19s is per
 * signalised intersection; entries after clustering track that better than raw OSM nodes.
 */
export const FAST_SECONDS_PER_UNIT = {
  signal_count: 7.5,
  junction_count: 10,
  calming_count: 4,
  barrier_penalty_count: 20,
  elevation_gain: 2.58, // per m gain — Miotti & Hellweg SSRN 5050670 (std bike; ebike 1.54 in backend)
};

/**
 * For increase / share metrics, metric_change_pct is percentage-points of route
 * composition. Convert with seconds saved per percentage-point.
 */
export const FAST_SECONDS_PER_PCT_POINT = {
  green_pct: 4, // park/river stretches: fewer interruptions (modest)
  vehicular_free_pct: 8, // help text: faster on segregated paths
  tfl_cycleway_pct: 3, // milder flow / fewer decisions
  speed_stress_pct: 0, // quieter roads often slower — not a time hunt
  accidents: 0, // safety, not clock time
};

/** Per-slider copy when Fast is selected (overrides detour-framed questions). */
export const FAST_SLIDER_QUESTIONS = {
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

/** Short notes under sliders that contribute little/zero to the savings bar. */
export const FAST_SLIDER_NOTES = {
  green_weight:
    'Scenic pulls can still help when they replace stop-start streets; the estimate is modest.',
  speed_weight:
    'Left on so you can tune comfort. It does not add to estimated time saved.',
  risk_weight:
    'Left on so you can tune safety. It does not add to estimated time saved.',
};

function interpMetricPct(anchors, value) {
  if (!anchors?.length) return 0;
  const pctAt = (a) => a.metric_change_pct ?? 0;
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

/**
 * Estimated minutes saved for one Fast slider at the given weight.
 * Returns 0 for unmapped / non-time metrics.
 */
export function sliderSaveMinutes(sliderCfg, value) {
  if (!sliderCfg || value <= EPSILON) return 0;
  const metric = sliderCfg.target_metric;
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

/** Linear-sum Fast savings across sliders (0.5 min rounding). */
export function totalSaveMinutes(sliders, weights, { hillDisabled = false } = {}) {
  let total = 0;
  Object.entries(sliders || {}).forEach(([key, cfg]) => {
    if (key === 'hill_weight' && hillDisabled) return;
    total += sliderSaveMinutes(cfg, weights[key] ?? 0);
  });
  return roundHalf(total);
}

/** Seed the Fast time-saving goal from current weights. */
export function seedFastBudget(sliders, weights, bikeRules = {}) {
  const used = totalSaveMinutes(sliders, weights, {
    hillDisabled: !!bikeRules.hill_weight_epsilon,
  });
  return Math.max(5, Math.ceil(used || 5));
}

/** Existing detour linear-sum — muted secondary “distance cost” on Fast. */
export function totalDistanceCostMinutes(sliders, weights, bikeType) {
  return totalMinutes(sliders, weights, bikeType);
}

export function sliderDistanceCostMinutes(sliderCfg, value, bikeType) {
  return sliderMinutes(sliderCfg, value, bikeType);
}

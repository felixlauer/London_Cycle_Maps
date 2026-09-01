import { sumChunkLengthM, trafficChunks } from '../../map/overlayModes';
import { modeKindAggregates } from './modeData';

const POWER_BIKES = new Set(['ebike', 'cargo']);

export const BAR_CHART_BUDGET = 8;
export const MAX_BAR_CHARTS = 3;

function overlayDonutMode(overlayMode: string | null) {
  if (!overlayMode || overlayMode === 'hills') return 'cycle';
  return overlayMode;
}

export function profileWantsLight(profile: { toggles?: { light_night?: boolean }; weights?: { light_weight?: number } } | null) {
  if (!profile) return false;
  if (profile.toggles?.light_night) return true;
  return Number(profile.weights?.light_weight || 0) > 0;
}

function barKindCount(safest: Record<string, unknown> | null | undefined, modeId: string) {
  return modeKindAggregates(safest, modeId)?.kinds?.length || 0;
}

export function resolveBarModes(
  safest: Record<string, unknown> | null | undefined,
  barA: string,
  barB: string | null,
  {
    hasTraffic = false,
    wantsLight = false,
    hasRough = false,
    maxCharts = MAX_BAR_CHARTS,
    budget = BAR_CHART_BUDGET,
  } = {},
) {
  const bars = [barA, barB].filter(Boolean) as string[];
  let used = bars.reduce((n, m) => n + barKindCount(safest, m), 0);
  const chartCap = Math.max(1, maxCharts);
  const barBudget = Math.max(1, budget);

  while (bars.length > 1 && used > barBudget) {
    const dropped = bars.pop()!;
    used -= barKindCount(safest, dropped);
  }
  if (bars.length > chartCap) {
    bars.length = chartCap;
    used = bars.reduce((n, m) => n + barKindCount(safest, m), 0);
  }

  const candidates: string[] = [];
  const push = (m: string) => {
    if (m && !bars.includes(m) && !candidates.includes(m)) candidates.push(m);
  };
  if (hasTraffic) push('traffic');
  if (wantsLight) push('light');
  push('cycle');
  push('green');
  if (hasRough) push('surface');
  push('hills');
  push('light');
  push('surface');

  for (const m of candidates) {
    if (bars.length >= chartCap) break;
    const n = barKindCount(safest, m);
    if (n <= 0) continue;
    if (used + n > barBudget) continue;
    bars.push(m);
    used += n;
  }
  return bars;
}

export function resolveIslandSlots({
  safest,
  overlayMode,
  bikeType = 'standard',
  isDarkOutside = false,
  profile = null,
  maxBarCharts = MAX_BAR_CHARTS,
  barBudget = BAR_CHART_BUDGET,
}: {
  safest: Record<string, unknown> | null | undefined;
  overlayMode: string | null;
  bikeType?: string;
  isDarkOutside?: boolean;
  profile?: { toggles?: { light_night?: boolean }; weights?: { light_weight?: number } } | null;
  maxBarCharts?: number;
  barBudget?: number;
}) {
  const hasTraffic = sumChunkLengthM(trafficChunks(safest as Record<string, unknown>)) > 0;
  const wantsLight = isDarkOutside && profileWantsLight(profile);
  const isPowerBike = POWER_BIKES.has(bikeType);
  const isRoad = bikeType === 'road';
  const stats = (safest?.stats || {}) as { rough_pct?: number };
  const hasRough = Number(stats.rough_pct || 0) > 0;
  const overlayDonut = overlayDonutMode(overlayMode);

  let right: string;
  if (hasTraffic) right = 'traffic';
  else if (wantsLight) right = 'light';
  else right = overlayDonut;

  let left: string | null = null;
  if (right === 'traffic' || right === 'light') {
    if (overlayMode === 'hills') {
      left = null;
    } else if (overlayDonut !== right) {
      left = overlayDonut;
    }
  }
  if (left == null && overlayMode !== 'hills') {
    if (isPowerBike) {
      if (right !== 'cycle') left = 'cycle';
      else left = 'green';
    } else if (isRoad && hasRough && right !== 'surface') {
      left = 'surface';
    }
  }

  const leftSlot = left != null
    ? { type: 'donut' as const, modeId: left }
    : { type: 'elevation' as const };
  const rightSlot = { type: 'donut' as const, modeId: right };

  const barA = right;
  let barB: string | null = left;
  if (barB == null || barB === barA) {
    barB = barA !== 'cycle' ? 'cycle' : 'green';
  }

  const bars = resolveBarModes(safest, barA, barB, {
    hasTraffic,
    wantsLight,
    hasRough,
    maxCharts: maxBarCharts,
    budget: barBudget,
  });

  return {
    left: leftSlot,
    right: rightSlot,
    bars,
    hasTraffic,
    wantsLight,
  };
}

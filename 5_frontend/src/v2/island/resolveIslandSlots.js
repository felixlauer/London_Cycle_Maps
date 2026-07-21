/**
 * Dynamic Island content resolution (locked plan 2026-07-18 + polish).
 *
 * Collapsed pill = 2 metric cells + 2 content slots (left / right).
 * Slot content: { type: 'elevation' } or { type: 'donut', modeId }.
 *
 * Expanded bars: 2 always, 3rd when bar-count budget allows (~8 bars
 * comfortable: e.g. 4 + 3 + 1).
 */
import { sumChunkLengthM, trafficChunks } from '../map/overlayModes';
import { modeKindAggregates } from './modeData';

const POWER_BIKES = new Set(['ebike', 'cargo']);

/** Comfortable max bars across all charts in the expanded right column. */
export const BAR_CHART_BUDGET = 8;
export const MAX_BAR_CHARTS = 3;

function overlayDonutMode(overlayMode) {
  if (!overlayMode || overlayMode === 'hills') return 'cycle';
  return overlayMode;
}

/** Profile wants illuminated roads at night (toggle or non-zero weight). */
export function profileWantsLight(profile) {
  if (!profile) return false;
  if (profile.toggles?.light_night) return true;
  return Number(profile.weights?.light_weight || 0) > 0;
}

function barKindCount(safest, modeId) {
  return modeKindAggregates(safest, modeId)?.kinds?.length || 0;
}

/**
 * Primary + secondary bars (locked), then fill up to MAX_BAR_CHARTS
 * while staying within BAR_CHART_BUDGET.
 */
export function resolveBarModes(safest, barA, barB, {
  hasTraffic = false,
  wantsLight = false,
  hasRough = false,
} = {}) {
  const bars = [barA, barB].filter(Boolean);
  let used = bars.reduce((n, m) => n + barKindCount(safest, m), 0);

  const candidates = [];
  const push = (m) => {
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
    if (bars.length >= MAX_BAR_CHARTS) break;
    const n = barKindCount(safest, m);
    if (n <= 0) continue;
    if (used + n > BAR_CHART_BUDGET) continue;
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
}) {
  const hasTraffic = sumChunkLengthM(trafficChunks(safest)) > 0;
  const wantsLight = isDarkOutside && profileWantsLight(profile);
  const isPowerBike = POWER_BIKES.has(bikeType);
  const isRoad = bikeType === 'road';
  const hasRough = Number(safest?.stats?.rough_pct || 0) > 0;
  const overlayDonut = overlayDonutMode(overlayMode);

  // —— Right slot (always a donut) ——
  let right;
  if (hasTraffic) right = 'traffic';
  else if (wantsLight) right = 'light';
  else right = overlayDonut;

  // —— Left slot ——
  // Hills has no donut — it is the elevation sparkline. When traffic/light
  // occupy the right slot, follow the overlay for left; hills → chart.
  let left = null;
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
      else if (right !== 'green') left = 'green';
    } else if (isRoad && hasRough && right !== 'surface') {
      left = 'surface';
    }
  }

  const leftSlot = left != null
    ? { type: 'donut', modeId: left }
    : { type: 'elevation' };
  const rightSlot = { type: 'donut', modeId: right };

  // —— Expanded bar charts ——
  const barA = right;
  let barB = left;
  if (barB == null || barB === barA) {
    barB = barA !== 'cycle' ? 'cycle' : 'green';
  }

  const bars = resolveBarModes(safest, barA, barB, {
    hasTraffic,
    wantsLight,
    hasRough,
  });

  return {
    left: leftSlot,
    right: rightSlot,
    bars,
    hasTraffic,
    wantsLight,
  };
}

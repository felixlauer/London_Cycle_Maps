import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * Compact top latch for multi-leg switching — chevrons + "1 / 2" only.
 * Used on collapsed and expanded island (all breakpoints).
 */
export default function IslandLegLatch({
  legCount,
  activeLegIndex,
  onChangeLeg,
}) {
  if (legCount <= 1) return null;

  const go = (next) => {
    const clamped = Math.max(0, Math.min(legCount - 1, next));
    if (clamped === activeLegIndex) return;
    onChangeLeg?.(clamped);
  };

  return (
    <div className="island-leg-latch" role="group" aria-label="Route segments">
      <button
        type="button"
        className="island-leg-latch__arrow"
        disabled={activeLegIndex <= 0}
        onClick={(e) => {
          e.stopPropagation();
          go(activeLegIndex - 1);
        }}
        aria-label="Previous segment"
      >
        <ChevronLeft size={14} strokeWidth={2.4} aria-hidden />
      </button>
      <span className="island-leg-latch__count" aria-live="polite">
        {activeLegIndex + 1}
        <span className="island-leg-latch__sep"> / </span>
        {legCount}
      </span>
      <button
        type="button"
        className="island-leg-latch__arrow"
        disabled={activeLegIndex >= legCount - 1}
        onClick={(e) => {
          e.stopPropagation();
          go(activeLegIndex + 1);
        }}
        aria-label="Next segment"
      >
        <ChevronRight size={14} strokeWidth={2.4} aria-hidden />
      </button>
    </div>
  );
}

/** @deprecated alias — keep imports working during migration */
export function IslandLegPager(props) {
  return <IslandLegLatch {...props} />;
}

/** Point names for leg labels: Start / Via 1… / End */
export function legPointNames(viaCount = 0) {
  const vias = Array.from({ length: viaCount }, (_, i) => `Via ${i + 1}`);
  return ['Start', ...vias, 'End'];
}

export function formatLegLabel(activeLegIndex, legCount, viaCount = 0) {
  const names = legPointNames(viaCount);
  const from = names[activeLegIndex] || `Leg ${activeLegIndex + 1}`;
  const to = names[activeLegIndex + 1] || 'End';
  return `Leg ${activeLegIndex + 1}/${legCount} · ${from} → ${to}`;
}

export function formatCollapsedLegParts(activeLegIndex, legCount, viaCount = 0) {
  const names = legPointNames(viaCount);
  const from = names[activeLegIndex] || 'Start';
  const to = names[activeLegIndex + 1] || 'End';
  return {
    viewing: `Viewing ${from} → ${to}`,
    part: `part ${activeLegIndex + 1}/${legCount}`,
  };
}

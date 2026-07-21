import React, { useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * Compact multi-leg pager — shell language (not legacy legAnalysis.css).
 * Bare chevrons + label; dots at bottom; optional swipe on the body.
 */
export default function IslandLegPager({
  legCount,
  activeLegIndex,
  onChangeLeg,
  legLabel,
  children,
}) {
  const touchStartX = useRef(null);
  const [slideDir, setSlideDir] = useState(0);

  if (legCount <= 1) {
    return (
      <div className="island-leg-pager island-leg-pager--single">
        <div className="island-leg-pager__body">{children}</div>
      </div>
    );
  }

  const go = (next) => {
    const clamped = Math.max(0, Math.min(legCount - 1, next));
    if (clamped === activeLegIndex) return;
    setSlideDir(clamped > activeLegIndex ? 1 : -1);
    onChangeLeg?.(clamped);
  };

  return (
    <div className="island-leg-pager">
      <div className="island-leg-pager__nav">
        <button
          type="button"
          className="island-leg-pager__arrow"
          disabled={activeLegIndex <= 0}
          onClick={() => go(activeLegIndex - 1)}
          aria-label="Previous leg"
        >
          <ChevronLeft size={16} strokeWidth={2.2} aria-hidden />
        </button>
        <div className="island-leg-pager__label">{legLabel}</div>
        <button
          type="button"
          className="island-leg-pager__arrow"
          disabled={activeLegIndex >= legCount - 1}
          onClick={() => go(activeLegIndex + 1)}
          aria-label="Next leg"
        >
          <ChevronRight size={16} strokeWidth={2.2} aria-hidden />
        </button>
      </div>
      <div
        key={activeLegIndex}
        className={`island-leg-pager__body${slideDir >= 0 ? ' is-next' : ' is-prev'}`}
        onTouchStart={(e) => {
          touchStartX.current = e.changedTouches[0].clientX;
        }}
        onTouchEnd={(e) => {
          if (touchStartX.current == null) return;
          const dx = e.changedTouches[0].clientX - touchStartX.current;
          touchStartX.current = null;
          if (Math.abs(dx) < 40) return;
          if (dx < 0) go(activeLegIndex + 1);
          else go(activeLegIndex - 1);
        }}
      >
        {children}
      </div>
      <div className="island-leg-pager__dots" role="tablist" aria-label="Route parts">
        {Array.from({ length: legCount }, (_, i) => (
          <button
            key={i}
            type="button"
            role="tab"
            aria-selected={i === activeLegIndex}
            className={`island-leg-pager__dot${i === activeLegIndex ? ' is-active' : ''}`}
            aria-label={`Show part ${i + 1}`}
            onClick={() => go(i)}
          />
        ))}
      </div>
    </div>
  );
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

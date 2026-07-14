/**
 * Swipeable / arrow-paged analysis for multi-leg routes.
 * content = React node for the active leg's stats body.
 */
import React, { useRef, useState } from 'react';
import './legAnalysis.css';

export default function LegAnalysisPager({
  legCount,
  activeLegIndex,
  onChangeLeg,
  legLabel,
  children,
}) {
  const touchStartX = useRef(null);
  const [slideDir, setSlideDir] = useState(0); // -1 left, 1 right for CSS hint

  if (legCount <= 1) {
    return children;
  }

  const go = (next) => {
    const clamped = Math.max(0, Math.min(legCount - 1, next));
    if (clamped === activeLegIndex) return;
    setSlideDir(clamped > activeLegIndex ? 1 : -1);
    onChangeLeg(clamped);
  };

  const onTouchStart = (e) => {
    touchStartX.current = e.changedTouches[0].clientX;
  };
  const onTouchEnd = (e) => {
    if (touchStartX.current == null) return;
    const dx = e.changedTouches[0].clientX - touchStartX.current;
    touchStartX.current = null;
    if (Math.abs(dx) < 40) return;
    if (dx < 0) go(activeLegIndex + 1);
    else go(activeLegIndex - 1);
  };

  return (
    <div
      className="leg-pager"
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      <div className="leg-pager__nav">
        <button
          type="button"
          className="leg-pager__arrow"
          disabled={activeLegIndex <= 0}
          onClick={() => go(activeLegIndex - 1)}
          aria-label="Previous leg"
        >
          ‹
        </button>
        <div className="leg-pager__label">{legLabel}</div>
        <button
          type="button"
          className="leg-pager__arrow"
          disabled={activeLegIndex >= legCount - 1}
          onClick={() => go(activeLegIndex + 1)}
          aria-label="Next leg"
        >
          ›
        </button>
      </div>
      <div
        key={activeLegIndex}
        className={`leg-pager__body${slideDir >= 0 ? ' slide-left' : ' slide-right'}`}
      >
        {children}
      </div>
      <div className="leg-pager__dots" aria-hidden>
        {Array.from({ length: legCount }, (_, i) => (
          <button
            key={i}
            type="button"
            className={`leg-pager__dot${i === activeLegIndex ? ' is-active' : ''}`}
            onClick={() => go(i)}
            aria-label={`Leg ${i + 1}`}
          />
        ))}
      </div>
    </div>
  );
}

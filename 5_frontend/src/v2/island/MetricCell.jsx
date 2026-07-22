import React from 'react';

/** Bold number + baseline unit + small comparison line. */
export default function MetricCell({ parts, delta, ariaLabel, twoLineDelta = false }) {
  let deltaPrimary = delta;
  let deltaSecondary = null;
  if (twoLineDelta && typeof delta === 'string' && delta.includes(' vs ')) {
    const idx = delta.indexOf(' vs ');
    deltaPrimary = delta.slice(0, idx);
    deltaSecondary = delta.slice(idx + 1); // "vs shortest"
  }

  return (
    <div className={`island-metric${twoLineDelta ? ' is-two-line' : ''}`} aria-label={ariaLabel}>
      <div className="island-metric__row">
        <span className="island-metric__value">{parts.value}</span>
        <span className="island-metric__unit">{parts.unit}</span>
      </div>
      {deltaPrimary && (
        <span className="island-metric__delta">
          {deltaPrimary}
          {deltaSecondary && (
            <>
              <br />
              {deltaSecondary}
            </>
          )}
        </span>
      )}
    </div>
  );
}

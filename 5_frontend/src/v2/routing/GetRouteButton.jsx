import React from 'react';
import { useLongRouteButtonLabel } from './useLongRouteButtonLabel';

/**
 * Primary route commit control — short "Calculating" for hops under 10 km;
 * staged verb copy + dot pulse for longer routes (v1 threshold, no overlay).
 */
export default function GetRouteButton({
  start,
  end,
  isCalculating,
  canGetRoute,
  onClick,
}) {
  const copy = useLongRouteButtonLabel(isCalculating, start, end);
  const disabled = !canGetRoute || isCalculating;

  return (
    <button
      type="button"
      className={`rc-get-route${disabled ? ' is-disabled' : ''}${isCalculating ? ' is-busy' : ''}`}
      aria-disabled={disabled}
      aria-busy={isCalculating}
      aria-live={isCalculating ? 'polite' : undefined}
      aria-label={isCalculating ? copy.ariaLabel : 'Get route'}
      onClick={onClick}
    >
      <span
        className={`rc-get-route__label${copy.textVisible ? ' is-visible' : ' is-hidden'}`}
        aria-hidden={isCalculating}
      >
        {copy.label}
      </span>
      {copy.showDots && (
        <span className="rc-get-route__dots" aria-hidden>
          <span className="rc-get-route__dot">.</span>
          <span className="rc-get-route__dot">.</span>
          <span className="rc-get-route__dot">.</span>
        </span>
      )}
    </button>
  );
}

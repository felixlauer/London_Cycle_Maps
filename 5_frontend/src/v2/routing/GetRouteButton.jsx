import React from 'react';
import { Diamond, CornerUpRight } from 'lucide-react';
import { useLongRouteButtonLabel } from './useLongRouteButtonLabel';

/**
 * Primary route commit control.
 * variant="full" — desktop text button.
 * variant="icon" — mobile vertical pill with Diamond + CornerUpRight.
 */
export default function GetRouteButton({
  start,
  end,
  isCalculating,
  canGetRoute,
  onClick,
  variant = 'full',
}) {
  const copy = useLongRouteButtonLabel(isCalculating, start, end);
  const disabled = !canGetRoute || isCalculating;

  if (variant === 'icon') {
    return (
      <button
        type="button"
        className={
          `rc-route-pill` +
          (disabled ? ' is-disabled' : '') +
          (isCalculating ? ' is-busy' : '')
        }
        aria-disabled={disabled}
        aria-busy={isCalculating}
        aria-label={isCalculating ? copy.ariaLabel : 'Get route'}
        onClick={onClick}
      >
        <span className={`rc-route-pill__icons${isCalculating ? ' is-pulse' : ''}`}>
          <Diamond
            size={24}
            strokeWidth={2.25}
            fill="currentColor"
            className="rc-route-pill__diamond"
            aria-hidden
          />
          <CornerUpRight
            size={13}
            strokeWidth={2.5}
            className="rc-route-pill__arrow"
            aria-hidden
          />
        </span>
      </button>
    );
  }

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

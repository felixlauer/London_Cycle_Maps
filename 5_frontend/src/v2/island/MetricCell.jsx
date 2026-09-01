import React from 'react';

/** Bold number + unit. Optional subtitle (e.g. walk add-on) via `delta`. */
export default function MetricCell({ parts, delta, ariaLabel }) {
  return (
    <div className="island-metric" aria-label={ariaLabel}>
      <div className="island-metric__row">
        <span className="island-metric__value">{parts.value}</span>
        <span className="island-metric__unit">{parts.unit}</span>
      </div>
      {delta && (
        <span className="island-metric__delta">{delta}</span>
      )}
    </div>
  );
}

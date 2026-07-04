import React from 'react';

/**
 * Estimated-detour budget bar. `used` fills against `budget` (both minutes).
 * Totals are a linear-sum approximation of interacting weights, so the label
 * always says "Estimated" and values are pre-rounded to 0.5 min.
 */
export default function BudgetBar({ used, budget }) {
  const over = used > budget + 0.01;
  const pct = budget > 0 ? Math.min(100, (used / budget) * 100) : (used > 0 ? 100 : 0);
  return (
    <div className="wiz-budget">
      <div className="wiz-budget-labels">
        <span>Estimated detour</span>
        <span className={`wiz-budget-used${over ? ' over' : ''}`}>
          {used.toFixed(1).replace(/\.0$/, '')} / {budget} min
        </span>
      </div>
      <div className="wiz-budget-track">
        <div
          className={`wiz-budget-fill${over ? ' over' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="wiz-budget-note">
        Estimate from independent sweeps - combined preferences interact, so the
        real detour can differ. {over ? 'You are over your budget; consider easing a slider.' : ''}
      </div>
    </div>
  );
}

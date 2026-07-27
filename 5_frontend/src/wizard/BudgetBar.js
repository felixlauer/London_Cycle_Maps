import React from 'react';

/**
 * Budget bar for wizard fine-tune.
 * `mode="detour"` (default): estimated detour vs budget.
 * `mode="savings"`: Fast-only estimated time saved vs time-saving goal.
 */
export default function BudgetBar({
  used,
  budget,
  mode = 'detour',
  distanceNoteMin = null,
}) {
  const savings = mode === 'savings';
  const over = used > budget + 0.01;
  const pct = budget > 0 ? Math.min(100, (used / budget) * 100) : (used > 0 ? 100 : 0);
  const usedLabel = used.toFixed(1).replace(/\.0$/, '');

  return (
    <div className="wiz-budget">
      <div className="wiz-budget-labels">
        <span>{savings ? 'Estimated time saved' : 'Estimated detour'}</span>
        <span className={`wiz-budget-used${over ? ' over' : ''}`}>
          {usedLabel} / {budget} min
        </span>
      </div>
      <div className="wiz-budget-track">
        <div
          className={`wiz-budget-fill${over ? ' over' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {savings && distanceNoteMin != null && distanceNoteMin > 0.05 && (
        <div className="wiz-budget-note">
          May add ~{distanceNoteMin.toFixed(1).replace(/\.0$/, '')} min of distance
          on a typical ride.
        </div>
      )}
      <div className="wiz-budget-note">
        {savings
          ? 'Estimate from metric improvements × fixed seconds on our 12.6 km reference ride — preferences interact, so real time can differ.'
          : 'Estimate from independent sweeps - combined preferences interact, so the real detour can differ.'}
        {' '}
        {over
          ? (savings
            ? 'You are over your time-saving goal; this is a very aggressive Fast setup.'
            : 'You are over your budget; consider easing a slider.')
          : ''}
      </div>
    </div>
  );
}

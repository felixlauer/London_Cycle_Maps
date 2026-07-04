import React, { useMemo, useState } from 'react';
import AnchoredSlider from './AnchoredSlider';
import BudgetBar from './BudgetBar';
import { totalMinutes, activeConflictWarnings } from './budget';

/**
 * Collapsible advanced tuning: master detour budget + per-weight anchored
 * sliders prefilled from the chosen preset. Slider minute costs fill the
 * budget bar (linear-sum "Estimated detour" - see budget.js).
 */
export default function AdvancedStep({
  config, bikeType, preset, weights, onWeightChange, budget, onBudgetChange,
}) {
  const [open, setOpen] = useState(false);
  const sliders = config.sliders || {};
  const exemplary = config.exemplary_route || {};
  const bikeRules = config.bike_types?.[bikeType]?.rules || {};
  const hillDisabled = !!bikeRules.hill_weight_epsilon;

  const used = totalMinutes(sliders, weights, bikeType);

  const warningsByWeight = useMemo(() => {
    const active = activeConflictWarnings(config.conflict_warnings?.[preset], weights);
    const map = {};
    active.forEach((cw) => {
      const loser = (cw.weights || []).find((k) => k !== cw.winner);
      if (loser && !map[loser]) map[loser] = cw.warning;
    });
    return map;
  }, [config, preset, weights]);

  const baseMin = exemplary.minutes_by_bike?.[bikeType];

  return (
    <>
      <p className="wiz-intro">
        Happy with the preset? You can skip this step. Otherwise, set a detour
        budget and tune each preference.
      </p>
      <div className="wiz-disclaimer">
        {exemplary.disclaimer}
        {baseMin !== undefined && (
          <> On your bike that is about <strong>{Math.round(baseMin)} min</strong> at baseline.</>
        )}
      </div>

      <button type="button" className="wiz-collapse-toggle" onClick={() => setOpen((v) => !v)}>
        <span>Advanced modifications</span>
        <span className={`wiz-chevron${open ? ' open' : ''}`}>▾</span>
      </button>

      {open && (
        <>
          <div className="wiz-panel">
            <div className="wiz-panel-title">Detour budget</div>
            <div className="wiz-slider" style={{ marginBottom: 8 }}>
              <div className="wiz-slider-head">
                <span className="wiz-slider-label">How many extra minutes are OK overall?</span>
                <span className="wiz-slider-cost">{budget} min</span>
              </div>
              <input
                type="range"
                min="0"
                max="30"
                step="1"
                value={budget}
                onChange={(e) => onBudgetChange(parseInt(e.target.value, 10))}
                aria-label="Detour budget"
              />
            </div>
            <BudgetBar used={used} budget={budget} />
          </div>

          <div className="wiz-panel">
            <div className="wiz-panel-title">Preferences</div>
            {Object.entries(sliders).map(([key, cfg]) => {
              if (key === 'hill_weight' && hillDisabled) {
                return (
                  <div key={key} className="wiz-slider">
                    <div className="wiz-slider-head">
                      <span className="wiz-slider-label">{cfg.label}</span>
                      <span className="wiz-slider-cost">disabled</span>
                    </div>
                    <div className="wiz-slider-question">
                      Assumed e-bike: the motor does the climbing, so hill avoidance is off.
                    </div>
                  </div>
                );
              }
              return (
                <AnchoredSlider
                  key={key}
                  sliderKey={key}
                  cfg={cfg}
                  value={weights[key] ?? 0}
                  onChange={onWeightChange}
                  bikeType={bikeType}
                  warning={warningsByWeight[key]}
                />
              );
            })}
          </div>
        </>
      )}
    </>
  );
}

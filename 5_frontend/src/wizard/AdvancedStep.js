import React, { useMemo, useState } from 'react';
import AnchoredSlider from './AnchoredSlider';
import BudgetBar from './BudgetBar';
import { totalMinutes, activeConflictWarnings } from './budget';
import {
  FAST_SLIDER_NOTES,
  FAST_SLIDER_QUESTIONS,
  sliderSaveMinutes,
  totalDistanceCostMinutes,
  totalSaveMinutes,
} from './fastSavings';

/**
 * Collapsible advanced tuning: master budget + per-weight anchored sliders.
 * Safe/Leisure: detour budget. Fast + `timeSavingFraming` (v2): time-saving goal.
 */
export default function AdvancedStep({
  config, bikeType, preset, weights, onWeightChange, budget, onBudgetChange,
  timeSavingFraming = false,
}) {
  const [open, setOpen] = useState(false);
  const sliders = config.sliders || {};
  const exemplary = config.exemplary_route || {};
  const bikeRules = config.bike_types?.[bikeType]?.rules || {};
  const hillDisabled = !!bikeRules.hill_weight_epsilon;
  const savingsMode = timeSavingFraming && preset === 'fast';

  const used = useMemo(() => {
    if (savingsMode) {
      return totalSaveMinutes(sliders, weights, { hillDisabled });
    }
    return totalMinutes(sliders, weights, bikeType);
  }, [savingsMode, sliders, weights, bikeType, hillDisabled]);

  const distanceNoteMin = useMemo(() => {
    if (!savingsMode) return null;
    return totalDistanceCostMinutes(sliders, weights, bikeType);
  }, [savingsMode, sliders, weights, bikeType]);

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
        {savingsMode
          ? 'Happy with the preset? You can skip this step. Otherwise, set a time-saving goal and tune how hard Fast should hunt.'
          : 'Happy with the preset? You can skip this step. Otherwise, set a detour budget and tune each preference.'}
      </p>

      <button type="button" className="wiz-collapse-toggle" onClick={() => setOpen((v) => !v)}>
        <span>Advanced modifications</span>
        <span className={`wiz-chevron${open ? ' open' : ''}`}>▾</span>
      </button>

      {open && (
        <>
          <div className="wiz-disclaimer">
            {exemplary.disclaimer}
            {baseMin !== undefined && (
              <> On your bike that is about <strong>{Math.round(baseMin)} min</strong> at baseline.</>
            )}
          </div>

          <div className="wiz-budget-sticky">
            <div className="wiz-panel" style={{ marginBottom: 0 }}>
              <div className="wiz-panel-title">
                {savingsMode ? 'Time-saving goal' : 'Detour budget'}
              </div>
              <div className="wiz-slider" style={{ marginBottom: 8 }}>
                <div className="wiz-slider-head">
                  <span className="wiz-slider-label">
                    {savingsMode
                      ? 'How much time should we try to save on a typical ride?'
                      : 'How many extra minutes are OK overall?'}
                  </span>
                  <span className="wiz-slider-cost">{budget} min</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="30"
                  step="1"
                  value={budget}
                  onChange={(e) => onBudgetChange(parseInt(e.target.value, 10))}
                  aria-label={savingsMode ? 'Time-saving goal' : 'Detour budget'}
                />
              </div>
              <BudgetBar
                used={used}
                budget={budget}
                mode={savingsMode ? 'savings' : 'detour'}
                distanceNoteMin={distanceNoteMin}
              />
            </div>
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
                  mode={savingsMode ? 'savings' : 'detour'}
                  saveMinutes={savingsMode ? sliderSaveMinutes(cfg, weights[key] ?? 0) : null}
                  questionOverride={savingsMode ? (FAST_SLIDER_QUESTIONS[key] || null) : null}
                  note={savingsMode ? (FAST_SLIDER_NOTES[key] || null) : null}
                />
              );
            })}
          </div>
        </>
      )}
    </>
  );
}

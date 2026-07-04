import React from 'react';
import HelpTip from './HelpTip';
import { sliderMinutes, metricChangeLabel } from './budget';

/**
 * Weight slider with smooth 0.1 drag, three highlighted anchors
 * (0 / moderate / max from the sweep data) and a minute-cost label.
 * Clicking an anchor snaps to it.
 */
export default function AnchoredSlider({ sliderKey, cfg, value, onChange, bikeType, warning }) {
  const cap = cfg.cap ?? 1;
  const anchors = cfg.anchors || [];
  const minutes = sliderMinutes(cfg, value, bikeType);
  const displayVal = value <= 0.0001 ? 0 : value;

  const anchorTitle = (a, idx) => {
    if (idx === 0) return 'Off';
    const mins = (a.minutes_by_bike?.[bikeType] ?? 0).toFixed(1);
    const metric = metricChangeLabel(cfg, a);
    return `${metric}${metric ? ' · ' : ''}~${mins} min`;
  };

  return (
    <div className="wiz-slider">
      <div className="wiz-slider-head">
        <span className="wiz-slider-label">
          {cfg.label}
          <HelpTip text={cfg.help} />
        </span>
        <span className="wiz-slider-cost">
          {minutes > 0.05 ? `+${minutes.toFixed(1)} min est.` : 'no detour'}
        </span>
      </div>
      <div className="wiz-slider-question">{cfg.question}</div>
      <div className="wiz-slider-track-wrap">
        <input
          type="range"
          min="0"
          max={cap}
          step="0.1"
          value={displayVal}
          onChange={(e) => onChange(sliderKey, parseFloat(e.target.value))}
          aria-label={cfg.label}
        />
        <div className="wiz-slider-anchors">
          {anchors.map((a, idx) => {
            const pos = cap > 0 ? (a.value / cap) * 100 : 0;
            const hit = Math.abs(displayVal - a.value) < 0.05;
            return (
              <button
                key={a.value}
                type="button"
                className={`wiz-anchor${hit ? ' hit' : ''}`}
                style={{ left: `${pos}%` }}
                onClick={() => onChange(sliderKey, a.value)}
                title={anchorTitle(a, idx)}
              >
                <span className="wiz-anchor-tick" />
                <span className="wiz-anchor-label">
                  {idx === 0 ? 'off' : `${a.value}`}
                </span>
              </button>
            );
          })}
        </div>
      </div>
      {warning && <div className="wiz-slider-warning">{warning}</div>}
    </div>
  );
}

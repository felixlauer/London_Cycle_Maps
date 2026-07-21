import React, { useState } from 'react';
import HelpTip from './HelpTip';

const DEFAULT_NAME_MAX = 8;

const Switch = ({ on, onToggle }) => (
  <button
    type="button"
    className={`wiz-switch${on ? ' on' : ''}`}
    onClick={onToggle}
    role="switch"
    aria-checked={on}
  >
    <span className="wiz-switch-track" />
    <span className="wiz-switch-knob" />
  </button>
);

export default function QuestionsStep({
  config, bikeType, toggles, onToggleChange, name, onNameChange,
  nameMaxLen = DEFAULT_NAME_MAX,
  nameHint = `Max ${DEFAULT_NAME_MAX} characters`,
}) {
  const cfg = config.toggles || {};
  const hideSurface = (cfg.surface?.hidden_for || []).includes(bikeType);
  const vfOptions = cfg.vf_infrastructure?.options || {};
  const [nameShake, setNameShake] = useState(false);
  const [hintPulse, setHintPulse] = useState(false);

  const softFailName = () => {
    setNameShake(true);
    setHintPulse(true);
    window.setTimeout(() => setNameShake(false), 340);
    window.setTimeout(() => setHintPulse(false), 900);
  };

  const handleNameChange = (e) => {
    const next = e.target.value;
    if (nameMaxLen != null && next.length > nameMaxLen) {
      softFailName();
      onNameChange(next.slice(0, nameMaxLen));
      return;
    }
    onNameChange(next);
  };

  const row = (key, question, help, extraSub) => (
    <div className="wiz-question" key={key}>
      <div>
        <div className="wiz-question-text">
          {question}
          <HelpTip text={help} />
        </div>
        {extraSub && <div className="wiz-question-sub">{extraSub}</div>}
      </div>
      <Switch on={!!toggles[key]} onToggle={() => onToggleChange(key, !toggles[key])} />
    </div>
  );

  return (
    <>
      <p className="wiz-intro">A few final questions, then name your profile.</p>
      <div className="wiz-panel">
        {row('light_night', cfg.light_night?.question, cfg.light_night?.help,
          'Only applies when it is dark outside.')}
        {!hideSurface && row('surface', cfg.surface?.question, cfg.surface?.help)}
        {hideSurface && (
          <div className="wiz-question">
            <div>
              <div className="wiz-question-text">Smooth surfaces</div>
              <div className="wiz-question-sub">
                Enabled automatically for road bikes.
              </div>
            </div>
          </div>
        )}
        {row('jam_comfort', cfg.jam_comfort?.question, cfg.jam_comfort?.help,
          'Road closures are always avoided either way.')}
      </div>

      <div className="wiz-panel">
        <div className="wiz-panel-title">
          {cfg.vf_infrastructure?.question || 'Cycling infrastructure'}
          <HelpTip text={cfg.vf_infrastructure?.help} />
        </div>
        <label className="wiz-check-row locked">
          <input type="checkbox" checked disabled />
          Segregated cycle tracks (always on)
        </label>
        {Object.entries(vfOptions).map(([optKey, opt]) => (
          <label className="wiz-check-row" key={optKey}>
            <input
              type="checkbox"
              checked={!!toggles.vf_infrastructure?.[optKey]}
              onChange={(e) => onToggleChange('vf_infrastructure', {
                ...toggles.vf_infrastructure,
                [optKey]: e.target.checked,
              })}
            />
            {opt.label}
          </label>
        ))}
      </div>

      <div className="wiz-panel">
        <div className="wiz-panel-title">Profile name</div>
        <div className={`wiz-name-field${nameShake ? ' is-shake' : ''}`}>
          <input
            className="wiz-input"
            type="text"
            value={name}
            placeholder="e.g. Commute"
            maxLength={nameMaxLen != null ? nameMaxLen + 1 : undefined}
            onChange={handleNameChange}
            aria-describedby="wiz-name-hint"
          />
          {nameHint && (
            <p
              id="wiz-name-hint"
              className={`wiz-name-hint${hintPulse ? ' is-pulse' : ''}`}
            >
              {nameHint}
            </p>
          )}
        </div>
      </div>
    </>
  );
}

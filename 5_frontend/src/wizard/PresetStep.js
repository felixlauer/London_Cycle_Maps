import React from 'react';

const PRESET_ICONS = { fast: '🏁', safe: '🛡️', leisure: '🌳' };

export default function PresetStep({ config, bikeType, preset, onSelect }) {
  const presets = config.presets || {};
  return (
    <>
      <p className="wiz-intro">
        Pick a starting style. Every value can be fine-tuned in the next step -
        the preset just sets sensible defaults.
      </p>
      <div className="wiz-card-grid" style={{ gridTemplateColumns: '1fr' }}>
        {Object.entries(presets).map(([id, p]) => {
          const est = p.estimated_detour_min_by_bike?.[bikeType];
          return (
            <button
              key={id}
              type="button"
              className={`wiz-card${preset === id ? ' selected' : ''}`}
              onClick={() => onSelect(id)}
            >
              <div className="wiz-card-title">
                <span>{PRESET_ICONS[id] || '•'}</span> {p.label}
              </div>
              <div className="wiz-card-note">{p.description}</div>
              {est !== undefined && (
                <span className="wiz-card-badge">est. detour ~{est} min</span>
              )}
            </button>
          );
        })}
      </div>
    </>
  );
}

import React from 'react';

const BIKE_ICONS = {
  standard: '🚲',
  road: '🚴',
  ebike: '⚡',
  cargo: '📦',
};

export default function BikeTypeStep({ config, bikeType, onSelect }) {
  const types = config.bike_types || {};
  return (
    <>
      <p className="wiz-intro">
        What are you riding? The bike changes what matters: hills, surfaces and
        barriers behave differently for each type.
      </p>
      <div className="wiz-card-grid">
        {Object.entries(types).map(([id, bt]) => (
          <button
            key={id}
            type="button"
            className={`wiz-card${bikeType === id ? ' selected' : ''}`}
            onClick={() => onSelect(id)}
          >
            <div className="wiz-card-icon">{BIKE_ICONS[id] || '🚲'}</div>
            <div className="wiz-card-title">{bt.label}</div>
            <div className="wiz-card-note">{bt.note}</div>
            <span className="wiz-card-badge">{bt.speed_kmh} km/h avg</span>
          </button>
        ))}
      </div>
    </>
  );
}

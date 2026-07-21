import React, { useMemo } from 'react';
import { modeKindAggregates } from './modeData';

function barMatchesHover(modeId, kind, hover) {
  if (!hover) return false;
  if (hover.kind !== kind) return false;
  return hover.modeId == null || hover.modeId === modeId;
}

function ModeBarChart({
  safest,
  modeId,
  externalHover,
  onHoverChange,
}) {
  const agg = useMemo(() => modeKindAggregates(safest, modeId), [safest, modeId]);
  if (!agg) return null;

  const maxPct = Math.max(1, ...agg.kinds.map((k) => k.pct));

  return (
    <div className="island-bars__chart">
      <h3 className="island-bars__heading">{agg.meta.label}</h3>
      {agg.kinds.length === 0 ? (
        <p className="island-bars__empty">
          {modeId === 'surface' ? 'No rough surfaces on this route' : 'None on this route'}
        </p>
      ) : (
        agg.kinds.map((k) => {
          const active = barMatchesHover(modeId, k.kind, externalHover);
          return (
            <div
              key={k.kind}
              className={`island-bar${active ? ' is-active' : ''}`}
              onMouseEnter={() => onHoverChange?.({ modeId, kind: k.kind })}
              onMouseLeave={() => onHoverChange?.(null)}
            >
              <span className="island-bar__track">
                <span
                  className="island-bar__fill island-glow-stroke"
                  style={{
                    width: `${Math.max(3, (k.pct / maxPct) * 100)}%`,
                    background: k.color,
                    color: k.color,
                  }}
                />
              </span>
              <span className="island-bar__label">
                {k.label}
                <em>{`${Math.round(k.pct)}%`}</em>
              </span>
            </div>
          );
        })
      )}
    </div>
  );
}

/** Right column — 2–3 stacked mode bar charts (budget-capped). */
export default function ModeBarCharts({
  safest,
  modes,
  externalHover,
  onHoverChange,
}) {
  return (
    <div className="island-bars">
      {modes.map((m) => (
        <ModeBarChart
          key={m}
          safest={safest}
          modeId={m}
          externalHover={externalHover}
          onHoverChange={onHoverChange}
        />
      ))}
    </div>
  );
}

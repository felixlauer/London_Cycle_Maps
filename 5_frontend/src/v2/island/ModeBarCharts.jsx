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
  maxKinds = Infinity,
}) {
  const agg = useMemo(() => modeKindAggregates(safest, modeId), [safest, modeId]);
  if (!agg) return null;

  const kinds = [...agg.kinds]
    .sort((a, b) => b.pct - a.pct)
    .slice(0, Number.isFinite(maxKinds) ? Math.max(1, maxKinds) : undefined);
  const maxPct = Math.max(1, ...kinds.map((k) => k.pct));

  return (
    <div className="island-bars__chart">
      <h3 className="island-bars__heading">{agg.meta.label}</h3>
      {kinds.length === 0 ? (
        <p className="island-bars__empty">
          {modeId === 'surface' ? 'No rough surfaces on this route' : 'None on this route'}
        </p>
      ) : (
        kinds.map((k) => {
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
  maxKindsPerChart = Infinity,
  showOverlayHint = false,
  onOverlayHintClick,
}) {
  const list = Array.isArray(modes) ? modes : [];
  if (list.length === 0) {
    return (
      <div className="island-bars">
        <p className="island-bars__empty">No mode charts for this route</p>
      </div>
    );
  }

  return (
    <div className="island-bars">
      {showOverlayHint && (
        <p className="island-bars__note">
          Detailed analysis.{' '}
          <button
            type="button"
            className="island-bars__note-link"
            onClick={(e) => {
              e.stopPropagation();
              onOverlayHintClick?.();
            }}
          >
            Switch map overlay
          </button>
          {' '}
          to change charts.
        </p>
      )}
      {list.map((m) => (
        <ModeBarChart
          key={m}
          safest={safest}
          modeId={m}
          externalHover={externalHover}
          onHoverChange={onHoverChange}
          maxKinds={maxKindsPerChart}
        />
      ))}
    </div>
  );
}

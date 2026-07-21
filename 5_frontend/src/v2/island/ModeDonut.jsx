import React, { useMemo, useState } from 'react';
import { modeKindAggregates } from './modeData';

/** SVG arc path from startAngle → endAngle (radians, 0 = east, CCW). */
function describeArc(cx, cy, r, startAngle, endAngle) {
  const sweep = endAngle - startAngle;
  if (sweep < 1e-4) return '';
  if (sweep >= 2 * Math.PI - 1e-4) {
    return (
      `M ${cx} ${cy - r} ` +
      `A ${r} ${r} 0 1 1 ${cx} ${cy + r} ` +
      `A ${r} ${r} 0 1 1 ${cx} ${cy - r}`
    );
  }
  const x1 = cx + r * Math.cos(startAngle);
  const y1 = cy + r * Math.sin(startAngle);
  const x2 = cx + r * Math.cos(endAngle);
  const y2 = cy + r * Math.sin(endAngle);
  const large = sweep > Math.PI ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
}

/**
 * Mode donut: grey track + bright arcs per kind.
 * Hover an arc → map segment highlight (same payload as bar charts).
 */
export default function ModeDonut({
  safest,
  modeId,
  size = 44,
  strokeWidth = 4.5,
  externalHover = null,
  onHoverChange,
}) {
  const [localHover, setLocalHover] = useState(null);
  const agg = useMemo(() => modeKindAggregates(safest, modeId), [safest, modeId]);
  if (!agg) return null;

  const r = (size - strokeWidth) / 2 - 1;
  const c = size / 2;

  const activeKind = localHover?.kind
    || (externalHover
      && (externalHover.modeId == null || externalHover.modeId === modeId)
      ? externalHover.kind
      : null);

  let cursor = -Math.PI / 2;
  const arcs = agg.kinds.map((k) => {
    const sweep = Math.max(0, (k.pct / 100) * 2 * Math.PI);
    const start = cursor;
    const end = cursor + sweep;
    cursor = end;
    const d = describeArc(c, c, r, start, end);
    if (!d) return null;
    const dimmed = Boolean(activeKind && activeKind !== k.kind);
    const active = activeKind === k.kind;
    return (
      <g key={k.kind} className="island-donut__seg">
        <path
          d={d}
          fill="none"
          stroke="transparent"
          strokeWidth={strokeWidth + 10}
          strokeLinecap="butt"
          className="island-donut__hit"
          onMouseEnter={(e) => {
            e.stopPropagation();
            setLocalHover(k);
            onHoverChange?.({ modeId, kind: k.kind });
          }}
          onMouseLeave={(e) => {
            e.stopPropagation();
            setLocalHover(null);
            onHoverChange?.(null);
          }}
        />
        <path
          d={d}
          fill="none"
          stroke={k.color}
          strokeWidth={strokeWidth}
          strokeLinecap={sweep > 0.08 ? 'round' : 'butt'}
          pointerEvents="none"
          className={
            `island-glow-stroke island-donut__arc` +
            (dimmed ? ' is-dim' : '') +
            (active ? ' is-active' : '')
          }
          style={{ color: k.color }}
        />
      </g>
    );
  });

  return (
    <svg
      className="island-donut"
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      aria-hidden
    >
      <circle
        cx={c}
        cy={c}
        r={r}
        fill="none"
        stroke="var(--island-track, #e9e9eb)"
        strokeWidth={strokeWidth}
      />
      {arcs}
      <text
        x={c}
        y={c + 0.5}
        textAnchor="middle"
        dominantBaseline="central"
        className="island-donut__pct"
        fill={agg.meta.hub}
      >
        {`${agg.centerPct}%`}
      </text>
    </svg>
  );
}

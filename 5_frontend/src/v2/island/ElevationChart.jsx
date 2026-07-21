import React, { useCallback, useMemo, useRef, useState } from 'react';
import { Fence, RectangleEllipsis, TrafficCone } from 'lucide-react';
import useMeasure from './useMeasure';
import { scaleProfile, smoothLinePath, areaPathFromLine } from './elevationPath';
import { ELEVATION_ACCENT } from './ElevationSparkline';
import { formatDistance } from '../units';

const AXIS_H = 24;
const TRAFFIC_COLOR = '#F18805';
/** Expanded chart only — elevation line/area use the bottom 75% (slices stay full height). */
const ELEV_PLOT_Y_FRAC = 0.75;

function remapPointsToYBand(points, chartH, fillFrac) {
  if (!points?.length) return points;
  const plotBottom = chartH;
  const plotTop = chartH * (1 - fillFrac);
  const ys = points.map((p) => p[1]);
  const yPeak = Math.min(...ys);
  const yTrough = Math.max(...ys);
  const span = yTrough - yPeak || 1;
  return points.map(([x, y]) => [
    x,
    plotTop + ((y - yPeak) / span) * (plotBottom - plotTop),
  ]);
}

const NODE_ICONS = {
  barrier: Fence,
  signal: RectangleEllipsis,
  calming: TrafficCone,
};

function sliceMatchesHover(slice, hover) {
  if (!hover) return false;
  if (hover.runId) return (slice.runIds || []).includes(hover.runId);
  if (hover.runIds?.length) {
    return hover.runIds.some((id) => (slice.runIds || []).includes(id));
  }
  if (hover.kind) {
    if (hover.modeId && slice.modeId && hover.modeId !== slice.modeId) return false;
    return hover.kind === slice.kind;
  }
  return false;
}

/**
 * Expanded centre chart — elevation line over distance with overlay
 * background slices, node icons on the axis, and a scrub location probe.
 */
export default function ElevationChart({
  profile,
  totalM,
  slices = [],
  trafficSlices = [],
  nodeMarkers = [],
  units = 'metric',
  externalHover = null,
  onSegmentHover,
  onScrub,
}) {
  const [wrapRef, { width, height }] = useMeasure();
  const [scrubD, setScrubD] = useState(null);
  const [hoveredKey, setHoveredKey] = useState(null);
  const [tip, setTip] = useState(null);
  const rafRef = useRef(0);

  const chartH = Math.max(0, height - AXIS_H);
  const geo = useMemo(() => {
    if (!(width > 10 && chartH > 10)) return null;
    const base = scaleProfile(profile, {
      width, height: chartH, padX: 4, padTop: 10, padBottom: 6, smoothWindow: 7,
    });
    if (!base) return null;
    return {
      ...base,
      points: remapPointsToYBand(base.points, chartH, ELEV_PLOT_Y_FRAC),
    };
  }, [profile, width, chartH]);

  const line = useMemo(() => (geo ? smoothLinePath(geo.points) : ''), [geo]);
  const area = useMemo(
    () => (geo ? areaPathFromLine(line, geo.points, chartH) : ''),
    [geo, line, chartH],
  );

  const xForD = useCallback(
    (d) => (geo && totalM > 0 ? geo.xForD((d / totalM) * geo.dMax) : 0),
    [geo, totalM],
  );

  const yAtX = useCallback((x) => {
    if (!geo) return 0;
    const pts = geo.points;
    if (x <= pts[0][0]) return pts[0][1];
    for (let i = 1; i < pts.length; i += 1) {
      if (pts[i][0] >= x) {
        const t = (x - pts[i - 1][0]) / ((pts[i][0] - pts[i - 1][0]) || 1);
        return pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t;
      }
    }
    return pts[pts.length - 1][1];
  }, [geo]);

  const handleMove = useCallback((e) => {
    if (!geo || !totalM) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const frac = Math.max(0, Math.min(1, (x - 4) / Math.max(1, width - 8)));
    const d = frac * totalM;
    setScrubD(d);
    if (rafRef.current) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = 0;
      onScrub?.(d);
    });
  }, [geo, totalM, width, onScrub]);

  const handleLeave = useCallback(() => {
    setScrubD(null);
    onScrub?.(null);
    onSegmentHover?.(null);
    setTip(null);
  }, [onScrub, onSegmentHover]);

  const ticks = useMemo(() => {
    if (!totalM) return [];
    return [0, 0.25, 0.5, 0.75, 1].map((f) => ({
      f,
      label: formatDistance(totalM * f, units),
    }));
  }, [totalM, units]);

  const renderSlice = (slice, isTraffic) => {
    const x0 = xForD(slice.d0);
    const x1 = xForD(slice.d1);
    const active = sliceMatchesHover(slice, externalHover) || slice.key === hoveredKey;
    return (
      <rect
        key={slice.key}
        x={x0}
        y={0}
        width={Math.max(1, x1 - x0)}
        height={chartH}
        fill={isTraffic ? 'url(#island-jam-dots)' : slice.color}
        opacity={isTraffic ? (active ? 1 : 0.55) : (active ? 0.38 : 0.16)}
        className="island-chart__slice"
        onMouseEnter={() => {
          setHoveredKey(slice.key);
          onSegmentHover?.(slice);
        }}
        onMouseLeave={() => {
          setHoveredKey(null);
          onSegmentHover?.(null);
        }}
      />
    );
  };

  const scrubX = scrubD != null ? xForD(scrubD) : null;

  return (
    <div
      ref={wrapRef}
      className="island-chart"
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
    >
      {geo && (
        <svg
          className="island-chart__svg"
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
        >
          <defs>
            <linearGradient id="island-chart-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={ELEVATION_ACCENT} stopOpacity="0.28" />
              <stop offset="100%" stopColor={ELEVATION_ACCENT} stopOpacity="0" />
            </linearGradient>
            <pattern
              id="island-jam-dots"
              width="6"
              height="6"
              patternUnits="userSpaceOnUse"
              patternTransform="rotate(45)"
            >
              <circle cx="1.5" cy="1.5" r="1.1" fill={TRAFFIC_COLOR} opacity="0.55" />
              <circle cx="4.5" cy="4.5" r="1.1" fill={TRAFFIC_COLOR} opacity="0.55" />
            </pattern>
          </defs>

          {slices.map((s) => renderSlice(s, false))}
          {trafficSlices.map((s) => renderSlice(s, true))}

          <path d={area} fill="url(#island-chart-grad)" stroke="none" pointerEvents="none" />
          <path
            d={line}
            fill="none"
            stroke={ELEVATION_ACCENT}
            strokeWidth="2.25"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="island-glow-stroke"
            style={{ color: ELEVATION_ACCENT }}
            pointerEvents="none"
          />

          <line
            x1={0}
            y1={chartH + 0.5}
            x2={width}
            y2={chartH + 0.5}
            stroke="var(--island-axis, #e4e4e7)"
            strokeWidth="1"
          />
          {ticks.map((t) => (
            <text
              key={t.f}
              x={Math.min(Math.max(t.f * width, 14), width - 20)}
              y={height - 6}
              textAnchor={t.f === 0 ? 'start' : t.f === 1 ? 'end' : 'middle'}
              className="island-chart__tick"
            >
              {t.label}
            </text>
          ))}

          {scrubX != null && (
            <g pointerEvents="none">
              <line
                x1={scrubX}
                y1={0}
                x2={scrubX}
                y2={chartH}
                stroke="var(--island-scrub-line, rgba(24,24,27,0.22))"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
              <circle
                cx={scrubX}
                cy={yAtX(scrubX)}
                r="5"
                fill="#ffffff"
                stroke={ELEVATION_ACCENT}
                strokeWidth="2"
                className="island-chart__scrub-dot"
              />
            </g>
          )}
        </svg>
      )}

      {geo && nodeMarkers.map((m) => {
        const Icon = NODE_ICONS[m.type];
        if (!Icon) return null;
        const left = xForD(m.d) - 9;
        return (
          <span
            key={m.key}
            className={`island-chart__node${m.type === 'signal' ? ' is-signal' : ''}`}
            style={{ left, top: chartH - 9 }}
            onMouseEnter={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const wrap = wrapRef.current?.getBoundingClientRect();
              setTip({
                text: m.label || m.type,
                x: rect.left - (wrap?.left || 0) + rect.width / 2,
                y: rect.top - (wrap?.top || 0) - 6,
              });
            }}
            onMouseLeave={() => setTip(null)}
          >
            <Icon size={10} strokeWidth={2.4} aria-hidden />
          </span>
        );
      })}

      {tip && (
        <div
          className="island-chart__tip"
          style={{ left: tip.x, top: tip.y }}
          role="tooltip"
        >
          {tip.text}
        </div>
      )}
    </div>
  );
}

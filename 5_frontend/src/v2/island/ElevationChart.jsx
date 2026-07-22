import React, { useCallback, useMemo, useRef, useState } from 'react';
import { Fence, RectangleEllipsis, TrafficCone } from 'lucide-react';
import useMeasure from './useMeasure';
import { scaleProfile, smoothLinePath, areaPathFromLine } from './elevationPath';
import { ELEVATION_ACCENT } from './ElevationSparkline';
import { formatDistance, formatElevation } from '../units';
import { OVERLAY_KIND_META } from '../map/overlayModes';

const AXIS_H = 24;
const TRAFFIC_COLOR = '#F18805';
/** Expanded chart only — elevation line/area use the bottom 75% (slices stay full height). */
const ELEV_PLOT_Y_FRAC = 0.75;
const NODE_SIZE = 24;
const NODE_ICON = 14;

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

function totalElevationGainM(profile) {
  if (!Array.isArray(profile) || profile.length < 2) return 0;
  let gain = 0;
  for (let i = 1; i < profile.length; i += 1) {
    const prev = Number(profile[i - 1]?.elev_m);
    const next = Number(profile[i]?.elev_m);
    if (!Number.isFinite(prev) || !Number.isFinite(next)) continue;
    const d = next - prev;
    if (d > 0) gain += d;
  }
  return gain;
}

function sliceLabel(slice) {
  if (!slice) return '';
  if (slice.modeId === 'traffic' || slice.kind === 'traffic') return 'Traffic jam';
  return OVERLAY_KIND_META[slice.kind]?.label || slice.kind || 'Segment';
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
  const wrapEl = wrapRef;
  const touchOrigin = useRef(null);
  const touchMode = useRef(null); // 'scrub' | 'page' | null

  const chartH = Math.max(0, height - AXIS_H);
  const gainM = useMemo(() => totalElevationGainM(profile), [profile]);
  const gainLabel = formatElevation(gainM, units);

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

  const placeTip = useCallback((text, clientX, clientY) => {
    const wrap = wrapEl.current?.getBoundingClientRect();
    if (!wrap) return;
    const rawX = clientX - wrap.left;
    const rawY = clientY - wrap.top;
    const pad = 10;
    const estW = Math.min(220, Math.max(80, String(text).length * 7.2));
    const estH = 28;
    const half = estW / 2;
    const clampedX = Math.min(Math.max(rawX, pad + half), Math.max(pad + half, wrap.width - pad - half));
    // Flip below the anchor when there isn't room above (near top / gain pill).
    const placeBelow = rawY < estH + 18;
    const y = placeBelow
      ? Math.min(wrap.height - pad, rawY + 14)
      : Math.max(estH + 4, rawY - 6);
    setTip({ text, x: clampedX, y, place: placeBelow ? 'below' : 'above' });
  }, [wrapEl]);

  const scrubFromClientX = useCallback((clientX, currentTarget) => {
    if (!geo || !totalM) return;
    const rect = currentTarget.getBoundingClientRect();
    const x = clientX - rect.left;
    const frac = Math.max(0, Math.min(1, (x - 4) / Math.max(1, width - 8)));
    const d = frac * totalM;
    setScrubD(d);
    if (rafRef.current) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = 0;
      onScrub?.(d);
    });
  }, [geo, totalM, width, onScrub]);

  const handleMove = useCallback((e) => {
    scrubFromClientX(e.clientX, e.currentTarget);
  }, [scrubFromClientX]);

  const handleLeave = useCallback(() => {
    setScrubD(null);
    onScrub?.(null);
    onSegmentHover?.(null);
    setTip(null);
    setHoveredKey(null);
  }, [onScrub, onSegmentHover]);

  const handleTouchMove = useCallback((e) => {
    if (!e.touches?.[0] || !touchOrigin.current) return;
    const t = e.touches[0];
    const dx = t.clientX - touchOrigin.current.x;
    const dy = t.clientY - touchOrigin.current.y;
    if (!touchMode.current) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
      // Clear horizontal swipe → let the island page pager own the gesture.
      if (Math.abs(dx) > Math.abs(dy) * 1.15 && Math.abs(dx) > 18) {
        touchMode.current = 'page';
        setScrubD(null);
        onScrub?.(null);
        return;
      }
      touchMode.current = 'scrub';
    }
    if (touchMode.current !== 'scrub') return;
    e.preventDefault();
    scrubFromClientX(t.clientX, e.currentTarget);
  }, [scrubFromClientX, onScrub]);

  const handleTouchEnd = useCallback(() => {
    touchOrigin.current = null;
    touchMode.current = null;
    setScrubD(null);
    onScrub?.(null);
  }, [onScrub]);

  const ticks = useMemo(() => {
    if (!totalM) return [];
    return [0, 0.25, 0.5, 0.75, 1].map((f) => ({
      f,
      label: formatDistance(totalM * f, units),
    }));
  }, [totalM, units]);

  const activateSlice = useCallback((slice, e) => {
    setHoveredKey(slice.key);
    onSegmentHover?.(slice);
    const midX = (xForD(slice.d0) + xForD(slice.d1)) / 2;
    const wrap = wrapEl.current?.getBoundingClientRect();
    if (wrap) {
      placeTip(
        sliceLabel(slice),
        wrap.left + midX,
        wrap.top + Math.max(36, chartH * 0.22),
      );
    } else if (e?.clientX != null) {
      placeTip(sliceLabel(slice), e.clientX, e.clientY);
    }
  }, [onSegmentHover, xForD, wrapEl, placeTip, chartH]);

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
        onMouseEnter={(e) => activateSlice(slice, e)}
        onMouseLeave={() => {
          setHoveredKey(null);
          onSegmentHover?.(null);
          setTip(null);
        }}
        onClick={(e) => activateSlice(slice, e)}
        onTouchEnd={(e) => {
          e.preventDefault();
          activateSlice(slice, e.changedTouches?.[0] || e);
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
      onTouchStart={(e) => {
        const t = e.touches?.[0];
        if (!t) return;
        touchOrigin.current = { x: t.clientX, y: t.clientY };
        touchMode.current = null;
        scrubFromClientX(t.clientX, e.currentTarget);
      }}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {geo && gainM > 0 && (
        <div className="island-chart__gain" aria-label={`Total elevation gain ${gainLabel}`}>
          <span className="island-chart__gain-label">Total elevation gain:</span>
          {' '}
          <strong style={{ color: ELEVATION_ACCENT }}>{gainLabel}</strong>
        </div>
      )}

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
        const left = xForD(m.d) - NODE_SIZE / 2;
        return (
          <span
            key={m.key}
            className={`island-chart__node${m.type === 'signal' ? ' is-signal' : ''}`}
            style={{ left, top: chartH - NODE_SIZE / 2 }}
            onMouseEnter={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              placeTip(m.label || m.type, rect.left + rect.width / 2, rect.top);
            }}
            onMouseLeave={() => setTip(null)}
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              placeTip(m.label || m.type, rect.left + rect.width / 2, rect.top);
            }}
          >
            <Icon size={NODE_ICON} strokeWidth={2.4} aria-hidden />
          </span>
        );
      })}

      {tip && (
        <div
          className={`island-chart__tip${tip.place === 'below' ? ' is-below' : ''}`}
          style={{ left: tip.x, top: tip.y }}
          role="tooltip"
        >
          {tip.text}
        </div>
      )}
    </div>
  );
}

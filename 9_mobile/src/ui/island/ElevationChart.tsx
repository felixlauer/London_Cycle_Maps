import { useCallback, useMemo, useRef, useState } from 'react';
import {
  GestureResponderEvent,
  LayoutChangeEvent,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import Svg, {
  Circle,
  Defs,
  LinearGradient,
  Line,
  Path,
  Pattern,
  Rect,
  Stop,
  Text as SvgText,
} from 'react-native-svg';
import { Fence, RectangleEllipsis, TrafficCone } from 'lucide-react-native';
import { OVERLAY_KIND_META } from '../../map/overlayModes';
import type { RouteHover } from '../../map/routeHover';
import { useChrome } from '../../theme/useChrome';
import { areaPathFromLine, scaleProfile, smoothLinePath } from './elevationPath';
import { ELEVATION_ACCENT } from './ElevationSparkline';

const AXIS_H = 24;
/** Left gutter for elevation Y ticks. */
const AXIS_Y_W = 26;
/** Plot line uses mid band — leave headroom above and icon clear space below. */
const ELEV_PLOT_Y_FRAC = 0.40;
const NODE_SIZE = 24;
const NODE_ICON = 13;
/** Keep elevation line clear of node icons sitting on the axis. */
const ELEV_BOTTOM_PAD = NODE_SIZE * 0.55 + 8;
/** Extra hit padding so node taps don't also fire the slice behind them. */
const NODE_DEAD_PAD = 10;
const TRAFFIC_COLOR = '#F18805';
/** Inactive chrome opacity — same family as Get Route inactive / overlay dim. */
const NODE_DIM = 0.4;

/** Web ElevationChart NODE_ICONS — Fence / RectangleEllipsis / TrafficCone. */
function NodeGlyph({
  type,
  color,
}: {
  type: string;
  color: string;
}) {
  if (type === 'barrier') {
    return <Fence size={NODE_ICON} strokeWidth={2.4} color={color} />;
  }
  if (type === 'calming') {
    return <TrafficCone size={NODE_ICON} strokeWidth={2.4} color={color} />;
  }
  // Web: .island-chart__node.is-signal svg { transform: rotate(90deg) }
  return (
    <View style={{ transform: [{ rotate: '90deg' }] }}>
      <RectangleEllipsis size={NODE_ICON} strokeWidth={2.4} color={color} />
    </View>
  );
}

function remapPointsToYBand(
  points: [number, number][],
  chartH: number,
  fillFrac: number,
  bottomPad = 0,
): [number, number][] {
  if (!points?.length) return points;
  const plotBottom = Math.max(8, chartH - bottomPad);
  const plotTop = Math.min(plotBottom - 8, chartH * (1 - fillFrac));
  const ys = points.map((p) => p[1]);
  const yPeak = Math.min(...ys);
  const yTrough = Math.max(...ys);
  const span = yTrough - yPeak || 1;
  return points.map(([x, y]) => [
    x,
    plotTop + ((y - yPeak) / span) * (plotBottom - plotTop),
  ]);
}

function totalElevationGainM(profile?: { elev_m?: number }[] | null) {
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

function formatElevation(metres: number) {
  return `${Math.round(metres)} m`;
}

function formatDistance(metres: number) {
  const m = Number(metres) || 0;
  if (m < 1000) return `${Math.round(m)} m`;
  const km = m / 1000;
  return `${km < 10 ? km.toFixed(1) : Math.round(km)} km`;
}

function sliceLabel(slice: ChartSlice) {
  if (!slice) return '';
  if (slice.modeId === 'traffic' || slice.kind === 'traffic') return 'Traffic jam';
  return OVERLAY_KIND_META[slice.kind]?.label || slice.kind || 'Segment';
}

function sliceMatchesHover(slice: ChartSlice, hover: RouteHover | null | undefined) {
  if (!hover) return false;
  if (hover.runId) return (slice.runIds || []).includes(hover.runId);
  if (hover.runIds?.length) {
    return hover.runIds.some((id) => id != null && (slice.runIds || []).includes(id));
  }
  if (hover.kind) {
    if (hover.modeId && slice.modeId && hover.modeId !== slice.modeId) return false;
    return hover.kind === slice.kind;
  }
  return false;
}

export type ChartSlice = {
  key: string;
  d0: number;
  d1: number;
  kind: string;
  modeId?: string;
  color: string;
  runId?: string;
  runIds?: (string | undefined)[];
};

export type NodeMarker = {
  key: string;
  type: string;
  label: string;
  d: number;
};

type TipState = {
  text: string;
  x: number;
  y: number;
  place: 'above' | 'below';
  width: number;
};

type Props = {
  profile?: { d_m?: number; elev_m?: number }[] | null;
  totalM?: number;
  slices?: ChartSlice[];
  trafficSlices?: ChartSlice[];
  nodeMarkers?: NodeMarker[];
  width?: number;
  height?: number;
  externalHover?: RouteHover | null;
  onSegmentHover?: (seg: {
    modeId?: string;
    kind: string;
    runIds?: (string | undefined)[];
  } | null) => void;
  onScrub?: (d: number | null) => void;
  /** True while a chart-originated gesture is active — parent disables page ScrollView. */
  onGestureActiveChange?: (active: boolean) => void;
  /** Clear horizontal swipe that should change island page (−1 left / +1 right). */
  onPageSwipeIntent?: (dir: -1 | 1) => void;
};

/**
 * Expanded elevation chart — slices, scrub probe, node tips (web ElevationChart).
 */
export function ElevationChart({
  profile,
  totalM,
  slices = [],
  trafficSlices = [],
  nodeMarkers = [],
  width = 300,
  height = 140,
  externalHover = null,
  onSegmentHover,
  onScrub,
  onGestureActiveChange,
  onPageSwipeIntent,
}: Props) {
  const { c, themeMode } = useChrome();
  const tipShadowOpacity = themeMode === 'light' ? 0.08 : 0.2;
  const [scrubD, setScrubD] = useState<number | null>(null);
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  const [activeNodeKey, setActiveNodeKey] = useState<string | null>(null);
  const [tip, setTip] = useState<TipState | null>(null);
  const touchOrigin = useRef<{ x: number; y: number } | null>(null);
  const touchMode = useRef<'scrub' | 'page' | 'node' | null>(null);
  const rafRef = useRef(0);
  const wrapW = useRef(width);
  const tipTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const gestureActiveRef = useRef(false);

  const chartH = Math.max(0, height - AXIS_H);
  const plotLeft = AXIS_Y_W;
  const plotRight = 4;
  const gainM = useMemo(() => totalElevationGainM(profile), [profile]);
  const gainLabel = formatElevation(gainM);
  const distanceTotal = totalM || (Array.isArray(profile) && profile.length
    ? Number(profile[profile.length - 1]?.d_m) || 0
    : 0);

  const geo = useMemo(() => {
    if (!(width > 10 && chartH > 10)) return null;
    const base = scaleProfile(profile, {
      width,
      height: chartH,
      padLeft: plotLeft,
      padRight: plotRight,
      padTop: 10,
      padBottom: 6,
      smoothWindow: 15,
    });
    if (!base) return null;
    return {
      ...base,
      points: remapPointsToYBand(
        base.points as [number, number][],
        chartH,
        ELEV_PLOT_Y_FRAC,
        ELEV_BOTTOM_PAD,
      ),
    };
  }, [profile, width, chartH]);

  const yTicks = useMemo(() => {
    if (!geo) return [];
    const { eMin, eMax, yForE } = geo;
    if (typeof yForE !== 'function') return [];
    const mid = (eMin + eMax) / 2;
    const plotBottom = Math.max(8, chartH - ELEV_BOTTOM_PAD);
    const plotTop = Math.min(plotBottom - 8, chartH * (1 - ELEV_PLOT_Y_FRAC));
    const ys = (geo.points as [number, number][]).map((p) => p[1]);
    const yPeak = Math.min(...ys);
    const yTrough = Math.max(...ys);
    const span = yTrough - yPeak || 1;
    const bandY = (rawY: number) => plotTop + ((rawY - yPeak) / span) * (plotBottom - plotTop);
    return [
      { elev: eMax, y: bandY(yForE(eMax)) },
      { elev: mid, y: bandY(yForE(mid)) },
      { elev: eMin, y: bandY(yForE(eMin)) },
    ];
  }, [geo, chartH]);

  const line = useMemo(() => (geo ? smoothLinePath(geo.points) : ''), [geo]);
  const area = useMemo(
    () => (geo ? areaPathFromLine(line, geo.points, chartH) : ''),
    [geo, line, chartH],
  );

  const xForD = useCallback((d: number) => {
    if (!geo || distanceTotal <= 0) return plotLeft;
    const frac = Math.max(0, Math.min(1, d / distanceTotal));
    return plotLeft + frac * Math.max(1, width - plotLeft - plotRight);
  }, [geo, distanceTotal, width, plotLeft, plotRight]);

  const yAtX = useCallback((x: number) => {
    if (!geo) return 0;
    const pts = geo.points as [number, number][];
    if (!pts.length) return 0;
    if (x <= pts[0][0]) return pts[0][1];
    for (let i = 1; i < pts.length; i += 1) {
      if (pts[i][0] >= x) {
        const t = (x - pts[i - 1][0]) / ((pts[i][0] - pts[i - 1][0]) || 1);
        return pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t;
      }
    }
    return pts[pts.length - 1][1];
  }, [geo]);

  const placeTip = useCallback((text: string, localX: number, localY: number) => {
    const pad = 8;
    const estW = Math.min(220, Math.max(72, String(text).length * 6.8 + 20));
    const estH = 26;
    const w = wrapW.current || width;
    // Keep tip centred on the icon, clamped so it never overflows the chart.
    const half = estW / 2;
    const clampedX = Math.min(Math.max(localX, pad + half), Math.max(pad + half, w - pad - half));
    const placeBelow = localY < estH + 14;
    const y = placeBelow
      ? Math.min(height - pad, localY + NODE_SIZE / 2 + 6)
      : Math.max(estH + 2, localY - NODE_SIZE / 2 - 4);
    setTip({ text, x: clampedX, y, place: placeBelow ? 'below' : 'above', width: estW });
    if (tipTimer.current) clearTimeout(tipTimer.current);
    tipTimer.current = setTimeout(() => {
      setTip(null);
      setActiveNodeKey(null);
    }, 2200);
  }, [width, height]);

  const setGestureActive = useCallback((active: boolean) => {
    if (gestureActiveRef.current === active) return;
    gestureActiveRef.current = active;
    onGestureActiveChange?.(active);
  }, [onGestureActiveChange]);

  const nodeAt = useCallback((x: number, y: number) => {
    const nodeTop = chartH - NODE_SIZE / 2;
    for (const m of nodeMarkers) {
      if (!['barrier', 'signal', 'calming'].includes(m.type)) continue;
      const left = Math.max(0, Math.min(width - NODE_SIZE, xForD(m.d) - NODE_SIZE / 2));
      if (
        x >= left - NODE_DEAD_PAD
        && x <= left + NODE_SIZE + NODE_DEAD_PAD
        && y >= nodeTop - NODE_DEAD_PAD
        && y <= nodeTop + NODE_SIZE + NODE_DEAD_PAD
      ) {
        return m;
      }
    }
    return null;
  }, [nodeMarkers, chartH, width, xForD]);

  const sliceAtX = useCallback((x: number) => {
    const all = [...slices, ...trafficSlices];
    for (let i = all.length - 1; i >= 0; i -= 1) {
      const s = all[i];
      const x0 = xForD(s.d0);
      const x1 = xForD(s.d1);
      if (x >= x0 && x <= Math.max(x0 + 1, x1)) return s;
    }
    return null;
  }, [slices, trafficSlices, xForD]);

  const scrubFromX = useCallback((x: number) => {
    if (!geo || !distanceTotal) return;
    const frac = Math.max(0, Math.min(1, (x - plotLeft) / Math.max(1, width - plotLeft - plotRight)));
    const d = frac * distanceTotal;
    setScrubD(d);
    if (rafRef.current) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = 0;
      onScrub?.(d);
    });
  }, [geo, distanceTotal, width, onScrub, plotLeft, plotRight]);

  const clearScrub = useCallback(() => {
    setScrubD(null);
    onScrub?.(null);
  }, [onScrub]);

  const activateSlice = useCallback((slice: ChartSlice) => {
    setHoveredKey(slice.key);
    onSegmentHover?.({
      modeId: slice.modeId,
      kind: slice.kind,
      runIds: slice.runIds,
    });
    const midX = (xForD(slice.d0) + xForD(slice.d1)) / 2;
    placeTip(sliceLabel(slice), midX, Math.max(36, chartH * 0.22));
  }, [onSegmentHover, xForD, placeTip, chartH]);

  const ticks = useMemo(() => {
    if (!distanceTotal) return [];
    const span = Math.max(1, width - plotLeft - plotRight);
    return [0, 0.25, 0.5, 0.75, 1].map((f) => ({
      f,
      label: formatDistance(distanceTotal * f),
      x: Math.min(
        Math.max(plotLeft + f * span, plotLeft + 2),
        width - plotRight - 2,
      ),
    }));
  }, [distanceTotal, width, plotLeft, plotRight]);

  const onLayout = (e: LayoutChangeEvent) => {
    wrapW.current = e.nativeEvent.layout.width || width;
  };

  const onTouchStart = (e: GestureResponderEvent) => {
    const t = e.nativeEvent;
    touchOrigin.current = { x: t.locationX, y: t.locationY };
    touchMode.current = null;
    const node = nodeAt(t.locationX, t.locationY);
    if (node) {
      touchMode.current = 'node';
      const left = Math.max(0, Math.min(width - NODE_SIZE, xForD(node.d) - NODE_SIZE / 2));
      const cx = left + NODE_SIZE / 2;
      const cy = chartH - NODE_SIZE / 2;
      setActiveNodeKey(node.key);
      placeTip(node.label || node.type, cx, cy);
      return;
    }
    // Lock the page pager so scrub wins while the finger stays in the chart.
    setGestureActive(true);
    scrubFromX(t.locationX);
  };

  const onTouchMove = (e: GestureResponderEvent) => {
    if (!touchOrigin.current || touchMode.current === 'node') return;
    const t = e.nativeEvent;
    const dx = t.locationX - touchOrigin.current.x;
    const dy = t.locationY - touchOrigin.current.y;
    if (!touchMode.current) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
      // Clear horizontal swipe → hand off to island page pager (web ElevationChart).
      if (Math.abs(dx) > Math.abs(dy) * 1.15 && Math.abs(dx) > 18) {
        touchMode.current = 'page';
        clearScrub();
        setGestureActive(false);
        onPageSwipeIntent?.(dx < 0 ? 1 : -1);
        return;
      }
      touchMode.current = 'scrub';
      setGestureActive(true);
    }
    if (touchMode.current !== 'scrub') return;
    scrubFromX(t.locationX);
  };

  const onTouchEnd = (e?: GestureResponderEvent) => {
    const origin = touchOrigin.current;
    const mode = touchMode.current;
    const endX = e?.nativeEvent?.locationX ?? origin?.x;
    const endY = e?.nativeEvent?.locationY ?? origin?.y;
    touchOrigin.current = null;
    touchMode.current = null;
    clearScrub();
    setGestureActive(false);

    // Tap (not scrub/page/node) → activate background slice, with node dead zone.
    if (mode === 'node' || mode === 'page' || mode === 'scrub') return;
    if (origin == null || endX == null || endY == null) return;
    if (Math.abs(endX - origin.x) > 10 || Math.abs(endY - origin.y) > 10) return;
    if (nodeAt(endX, endY)) return;
    const slice = sliceAtX(endX);
    if (slice) activateSlice(slice);
  };

  if (!geo) {
    return (
      <View style={[styles.wrap, { width, height }]}>
        <Text style={[styles.empty, { color: c.textSub }]}>—</Text>
      </View>
    );
  }

  const scrubX = scrubD != null ? xForD(scrubD) : null;

  return (
    <View
      style={[styles.wrap, { width, height }]}
      onLayout={onLayout}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      onTouchCancel={onTouchEnd}
    >
      {gainM > 0 ? (
        <View style={styles.gainRow} pointerEvents="none">
          <View style={[styles.gain, { backgroundColor: c.shellBg, borderColor: c.shellBorder }]} accessibilityLabel={`Total elevation gain ${gainLabel}`}>
            <Text style={[styles.gainLabel, { color: c.textSub }]}>Total elevation gain:</Text>
            <Text style={styles.gainValue}>{gainLabel}</Text>
          </View>
        </View>
      ) : null}

      <Svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <Defs>
          <LinearGradient id="island-chart-grad" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0%" stopColor={ELEVATION_ACCENT} stopOpacity={0.28} />
            <Stop offset="100%" stopColor={ELEVATION_ACCENT} stopOpacity={0} />
          </LinearGradient>
          <Pattern
            id="island-jam-dots"
            patternUnits="userSpaceOnUse"
            width={6}
            height={6}
            patternTransform="rotate(45)"
          >
            <Circle cx={1.5} cy={1.5} r={1.1} fill={TRAFFIC_COLOR} />
          </Pattern>
        </Defs>

        {slices.map((s, i) => {
          const x0 = xForD(s.d0);
          const x1 = xForD(s.d1);
          const active = sliceMatchesHover(s, externalHover) || s.key === hoveredKey;
          return (
            <Rect
              key={`slice-${s.key}-${i}`}
              x={x0}
              y={0}
              width={Math.max(1, x1 - x0)}
              height={chartH}
              fill={s.color || OVERLAY_KIND_META[s.kind]?.color || '#a1a1aa'}
              opacity={active ? 0.38 : 0.16}
              pointerEvents="none"
            />
          );
        })}

        {trafficSlices.map((s, i) => {
          const x0 = xForD(s.d0);
          const x1 = xForD(s.d1);
          const active = sliceMatchesHover(s, externalHover) || s.key === hoveredKey;
          return (
            <Rect
              key={`jam-${s.key}-${i}`}
              x={x0}
              y={0}
              width={Math.max(1, x1 - x0)}
              height={chartH}
              fill="url(#island-jam-dots)"
              opacity={active ? 1 : 0.55}
              pointerEvents="none"
            />
          );
        })}

        <Path d={area} fill="url(#island-chart-grad)" stroke="none" pointerEvents="none" />
        <Path
          d={line}
          fill="none"
          stroke={ELEVATION_ACCENT}
          strokeWidth={2.25}
          strokeLinecap="round"
          strokeLinejoin="round"
          pointerEvents="none"
        />
        <Line
          x1={plotLeft + 0.5}
          y1={4}
          x2={plotLeft + 0.5}
          y2={chartH}
          stroke={c.line}
          strokeWidth={1}
          pointerEvents="none"
        />
        {yTicks.map((t) => (
          <SvgText
            key={`y-${t.elev}`}
            x={plotLeft - 2}
            y={t.y + 3}
            fill={c.textSub}
            fontSize={8}
            fontWeight="600"
            textAnchor="end"
          >
            {formatElevation(t.elev)}
          </SvgText>
        ))}
        <Line
          x1={plotLeft}
          y1={chartH + 0.5}
          x2={width - plotRight}
          y2={chartH + 0.5}
          stroke={c.line}
          strokeWidth={1}
          pointerEvents="none"
        />
        {ticks.map((t) => (
          <SvgText
            key={t.f}
            x={t.x}
            y={height - 4}
            fill={c.textSub}
            fontSize={9.5}
            fontWeight="600"
            textAnchor={t.f === 0 ? 'start' : t.f === 1 ? 'end' : 'middle'}
          >
            {t.label}
          </SvgText>
        ))}

        {scrubX != null && (
          <>
            <Line
              x1={scrubX}
              y1={0}
              x2={scrubX}
              y2={chartH}
              stroke="rgba(244,244,245,0.28)"
              strokeWidth={1}
              strokeDasharray="3 3"
              pointerEvents="none"
            />
            <Circle
              cx={scrubX}
              cy={yAtX(scrubX)}
              r={5}
              fill="#ffffff"
              stroke={ELEVATION_ACCENT}
              strokeWidth={2}
              pointerEvents="none"
            />
          </>
        )}
      </Svg>

      <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
        {nodeMarkers.map((m) => {
          if (!['barrier', 'signal', 'calming'].includes(m.type)) return null;
          const left = Math.max(0, Math.min(width - NODE_SIZE, xForD(m.d) - NODE_SIZE / 2));
          const top = chartH - NODE_SIZE / 2;
          const dimmed = Boolean(activeNodeKey && activeNodeKey !== m.key);
          const active = activeNodeKey === m.key;
          // Omit transform when inactive — RN processTransform crashes on null/undefined.
          const nodeStyle = [
            styles.node,
            {
              left,
              top,
              opacity: dimmed ? NODE_DIM : 1,
              backgroundColor: c.shellBg,
              borderColor: active ? c.textSub : c.line,
              zIndex: active ? 5 : 3,
            },
            active ? { transform: [{ scale: 1.12 }] } : null,
          ];
          return (
            <Pressable
              key={m.key}
              accessibilityRole="button"
              accessibilityLabel={m.label}
              hitSlop={NODE_DEAD_PAD}
              onPress={() => {
                touchMode.current = 'node';
                setActiveNodeKey(m.key);
                placeTip(m.label || m.type, left + NODE_SIZE / 2, top + NODE_SIZE / 2);
              }}
              style={nodeStyle}
            >
              <NodeGlyph
                type={m.type}
                color={dimmed ? c.textSub : (active ? c.text : c.textSub)}
              />
            </Pressable>
          );
        })}
      </View>

      {tip ? (
        <View
          pointerEvents="none"
          style={[
            styles.tip,
            {
              left: tip.x,
              top: tip.place === 'below' ? tip.y : tip.y,
              width: tip.width,
              maxWidth: tip.width,
              backgroundColor: c.shellBg,
              borderColor: c.shellBorder,
              shadowOpacity: tipShadowOpacity,
              transform: tip.place === 'above'
                ? [{ translateX: -tip.width / 2 }, { translateY: -26 }]
                : [{ translateX: -tip.width / 2 }],
            },
          ]}
        >
          <Text style={[styles.tipText, { color: c.text }]} numberOfLines={1}>
            {tip.text}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'relative',
    alignItems: 'stretch',
    justifyContent: 'flex-start',
    overflow: 'visible',
  },
  empty: {
    fontSize: 12,
    textAlign: 'center',
  },
  gainRow: {
    position: 'absolute',
    top: 4,
    left: 0,
    right: 0,
    zIndex: 2,
    alignItems: 'center',
  },
  gain: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 4,
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: 999,
    borderWidth: 1,
  },
  gainLabel: {
    fontSize: 10.5,
    fontWeight: '500',
  },
  gainValue: {
    fontSize: 10.5,
    fontWeight: '700',
    color: ELEVATION_ACCENT,
    fontVariant: ['tabular-nums'],
  },
  node: {
    position: 'absolute',
    width: NODE_SIZE,
    height: NODE_SIZE,
    borderRadius: 999,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 3,
    shadowColor: '#000',
    shadowOpacity: 0.12,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
    elevation: 2,
  },
  tip: {
    position: 'absolute',
    zIndex: 10,
    paddingVertical: 5,
    paddingHorizontal: 10,
    borderRadius: 999,
    borderWidth: 1,
    shadowColor: '#000',
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 6,
    alignItems: 'center',
  },
  tipText: {
    fontSize: 11,
    fontWeight: '600',
  },
});

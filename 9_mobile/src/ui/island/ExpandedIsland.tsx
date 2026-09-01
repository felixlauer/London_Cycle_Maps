import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  LayoutChangeEvent,
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { ChevronDown } from 'lucide-react-native';
import { OVERLAY_KIND_META } from '../../map/overlayModes';
import type { RouteHover } from '../../map/routeHover';
import { brand } from '../../theme/tokens';
import { useChrome } from '../../theme/useChrome';
import { ElevationChart, type ChartSlice, type NodeMarker } from './ElevationChart';
import { MetricCell } from './MetricCell';
import { ModeBarCharts } from './ModeBarCharts';
import { formatDistanceParts, formatDurationParts, formatWalkParts, tripLengthM } from './metrics';
import { modeChunksFor } from './modeData';
import { buildDistanceIndex, buildSlices } from './routeGeometry';
import { IslandHireStations } from './IslandHireStations';
import type { HireStation } from '../../api/santander';
import type { HireWalkStats } from '../../map/useSantanderHire';

const PAGE_METRICS = 0;
const PAGE_CHART = 1;
const PAGE_BARS = 2;
const PAGE_LABELS = ['Core metrics', 'Chart overview', 'Detailed analysis'];
const PAGE_GAP = 8;
const NODE_TYPES = new Set(['barrier', 'signal', 'calming']);

type Props = {
  safest: Record<string, unknown>;
  barModes: string[];
  overlayMode?: string | null;
  onCollapse: () => void;
  onOverlayHintClick?: () => void;
  externalHover?: RouteHover | null;
  onSegmentHover?: (seg: {
    modeId?: string;
    kind: string;
    runIds?: (string | undefined)[];
  } | null) => void;
  onScrub?: (d: number | null) => void;
  santander?: boolean;
  pickupStation?: HireStation | null;
  dropoffStation?: HireStation | null;
  walkStats?: HireWalkStats | null;
  units?: 'metric' | 'imperial';
  onPageChange?: (page: number) => void;
};

function toChartSlices(
  chunks: { path?: number[][]; length_m?: number; kind?: string; run_id?: string }[],
  index: ReturnType<typeof buildDistanceIndex>,
  modeId: string,
): ChartSlice[] {
  return buildSlices(chunks, index).map((s, i) => ({
    ...s,
    modeId,
    color: OVERLAY_KIND_META[s.kind]?.color || '#a1a1aa',
    key: `${modeId}-${s.kind}-${i}`,
  }));
}

function nodeLabel(n: {
  type?: string;
  details?: { barrier?: string; traffic_calming?: string };
}) {
  const details = n.details || {};
  if (n.type === 'barrier') {
    const raw = String(details.barrier || 'barrier').replace(/_/g, ' ');
    return `Barrier: ${raw}`;
  }
  if (n.type === 'signal') return 'Traffic signals';
  if (n.type === 'calming') {
    const raw = String(details.traffic_calming || 'calming').replace(/_/g, ' ');
    return `Traffic calming: ${raw}`;
  }
  return n.type || '';
}

/**
 * Expanded island — ScrollView paging so each panel is exactly the viewport width.
 */
export function ExpandedIsland({
  safest,
  barModes,
  overlayMode = 'cycle',
  onCollapse,
  onOverlayHintClick,
  externalHover = null,
  onSegmentHover,
  onScrub,
  santander = false,
  pickupStation = null,
  dropoffStation = null,
  walkStats = null,
  units = 'metric',
  onPageChange,
}: Props) {
  const { c } = useChrome();
  const [page, setPage] = useState(PAGE_CHART);
  const [vw, setVw] = useState(0);
  const [progressW, setProgressW] = useState(0);
  const [scrollX, setScrollX] = useState(PAGE_CHART);
  const [sheetHover, setSheetHover] = useState<RouteHover | null>(null);
  const [chartGestureActive, setChartGestureActive] = useState(false);
  const scrollRef = useRef<ScrollView>(null);
  const pageRef = useRef(PAGE_CHART);
  pageRef.current = page;

  useEffect(() => {
    onPageChange?.(page);
  }, [page, onPageChange]);

  const stats = (safest.stats || {}) as { duration_min?: number; length_m?: number; distance_m?: number };
  const time = formatDurationParts(stats.duration_min);
  const dist = formatDistanceParts(tripLengthM(stats), units);
  const walkParts = santander
    ? formatWalkParts(walkStats?.duration_min, walkStats?.distance_m, units)
    : null;

  const path = Array.isArray(safest.path) ? (safest.path as number[][]) : [];
  const index = useMemo(() => buildDistanceIndex(path), [path]);
  const totalM = index.totalM || tripLengthM(stats);

  const chartHover = sheetHover || externalHover || null;

  const handleHover = useCallback((seg: {
    modeId?: string;
    kind: string;
    runIds?: (string | undefined)[];
  } | null) => {
    setSheetHover(seg ? { source: 'island', ...seg } : null);
    onSegmentHover?.(seg);
  }, [onSegmentHover]);

  const modeSlices = useMemo(() => {
    if (!overlayMode || !index.totalM) return [];
    return toChartSlices(modeChunksFor(safest, overlayMode), index, overlayMode);
  }, [safest, overlayMode, index]);

  const slices = useMemo(() => {
    const hoverMode = chartHover?.modeId;
    if (!hoverMode || !index.totalM || hoverMode === overlayMode || hoverMode === 'traffic') {
      return modeSlices;
    }
    const extra = toChartSlices(modeChunksFor(safest, hoverMode), index, hoverMode)
      .filter((s) => !chartHover.kind || s.kind === chartHover.kind);
    return [...modeSlices, ...extra];
  }, [modeSlices, chartHover, safest, overlayMode, index]);

  const trafficSlices = useMemo(() => {
    if (!index.totalM) return [];
    return toChartSlices(modeChunksFor(safest, 'traffic'), index, 'traffic');
  }, [safest, index]);

  const nodeMarkers: NodeMarker[] = useMemo(() => {
    if (!barModes?.includes('cycle') || !index.totalM) return [];
    const raw = ((safest.node_highlights || []) as {
      type?: string;
      lat?: number;
      lon?: number;
      details?: { barrier?: string; traffic_calming?: string };
    }[])
      .filter((n) => n.type && NODE_TYPES.has(n.type))
      .map((n, i) => ({
        key: `${n.type}-${i}`,
        type: n.type!,
        label: nodeLabel(n),
        d: index.nearestDist(Number(n.lat), Number(n.lon)),
      }))
      .sort((a, b) => a.d - b.d);
    const minGap = Math.max(1, index.totalM * 0.025);
    const kept: NodeMarker[] = [];
    raw.forEach((m) => {
      if (!kept.length || m.d - kept[kept.length - 1].d >= minGap) kept.push(m);
    });
    return kept;
  }, [safest, barModes, index]);

  const goToPage = (next: number) => {
    const clamped = Math.max(PAGE_METRICS, Math.min(PAGE_BARS, next));
    setPage(clamped);
    setScrollX(clamped);
    if (vw > 0) {
      scrollRef.current?.scrollTo({ x: clamped * vw, animated: true });
    }
  };

  const onChartPageSwipe = useCallback((dir: -1 | 1) => {
    const next = Math.max(PAGE_METRICS, Math.min(PAGE_BARS, pageRef.current + dir));
    setPage(next);
    setScrollX(next);
    const w = vw;
    if (w > 0) {
      scrollRef.current?.scrollTo({ x: next * w, animated: true });
    }
  }, [vw]);

  const onViewportLayout = (e: LayoutChangeEvent) => {
    const w = e.nativeEvent.layout.width;
    if (w <= 0) return;
    setVw(w);
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ x: page * w, animated: false });
    });
  };

  const onProgressLayout = (e: LayoutChangeEvent) => {
    setProgressW(e.nativeEvent.layout.width);
  };

  const onScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    if (vw <= 0) return;
    setScrollX(e.nativeEvent.contentOffset.x / vw);
  };

  const onScrollEnd = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    if (vw <= 0) return;
    const next = Math.round(e.nativeEvent.contentOffset.x / vw);
    setPage(next);
    setScrollX(next);
  };

  const chartW = Math.max(160, vw - 4);
  const segW = progressW > 0 ? (progressW - PAGE_GAP * 2) / 3 : 0;
  const thumbLeft = scrollX * (segW + PAGE_GAP);

  const pages = useMemo(() => {
    const metrics = santander ? (
      <View style={styles.metricsSantander}>
        <View style={styles.metricsCol}>
          <View style={styles.metricBlock}>
            {walkParts?.time ? (
              <Text style={[styles.walkLabel, { color: c.textSub }]} numberOfLines={1}>{walkParts.time}</Text>
            ) : null}
            <MetricCell value={time.value} unit={time.unit} label="Trip time" size="expanded" />
          </View>
          <View style={styles.metricBlock}>
            {walkParts?.distance ? (
              <Text style={[styles.walkLabel, { color: c.textSub }]} numberOfLines={1}>{walkParts.distance}</Text>
            ) : null}
            <MetricCell value={dist.value} unit={dist.unit} label="Trip distance" size="expanded" />
          </View>
        </View>
        <View style={styles.hireCol}>
          <IslandHireStations pickup={pickupStation} dropoff={dropoffStation} />
        </View>
      </View>
    ) : (
      <View style={styles.metricsPage}>
        <MetricCell value={time.value} unit={time.unit} label="Trip time" size="expanded" />
        <MetricCell value={dist.value} unit={dist.unit} label="Trip distance" size="expanded" />
      </View>
    );
    const chart = (
      <View style={styles.chartPage}>
        {vw > 0 ? (
          <ElevationChart
            profile={safest.elevation_profile as { d_m?: number; elev_m?: number }[] | undefined}
            totalM={totalM}
            slices={slices}
            trafficSlices={trafficSlices}
            nodeMarkers={nodeMarkers}
            width={chartW}
            height={148}
            externalHover={chartHover}
            onSegmentHover={handleHover}
            onScrub={onScrub}
            onGestureActiveChange={setChartGestureActive}
            onPageSwipeIntent={onChartPageSwipe}
          />
        ) : null}
      </View>
    );
    const bars = (
      <View style={styles.barsPage}>
        <ModeBarCharts
          safest={safest}
          modes={barModes}
          maxKindsPerChart={3}
          showOverlayHint
          onOverlayHintClick={onOverlayHintClick}
          externalHover={chartHover}
          onHoverChange={handleHover}
        />
      </View>
    );
    return [metrics, chart, bars];
  }, [
    safest, barModes, time, dist, totalM, slices, trafficSlices,
    nodeMarkers, chartW, vw, onOverlayHintClick, chartHover, handleHover, onScrub,
    onChartPageSwipe, santander, walkParts, pickupStation, dropoffStation, c,
  ]);

  return (
    <View style={styles.root}>
      <Pressable
        accessibilityLabel="Collapse route analysis"
        onPress={onCollapse}
        style={({ pressed }) => [styles.collapse, pressed && { opacity: 0.7 }]}
      >
        <ChevronDown size={16} strokeWidth={2.2} color={c.textSub} />
      </Pressable>

      <View style={styles.viewport} onLayout={onViewportLayout}>
        {vw > 0 ? (
          <ScrollView
            ref={scrollRef}
            horizontal
            pagingEnabled
            scrollEnabled={!chartGestureActive}
            bounces={false}
            decelerationRate="fast"
            showsHorizontalScrollIndicator={false}
            onScroll={onScroll}
            onMomentumScrollEnd={onScrollEnd}
            scrollEventThrottle={16}
            style={{ width: vw }}
            contentOffset={{ x: PAGE_CHART * vw, y: 0 }}
          >
            {pages.map((p, i) => (
              <View key={PAGE_LABELS[i]} style={[styles.slide, { width: vw }]}>
                {p}
              </View>
            ))}
          </ScrollView>
        ) : null}
      </View>

      <View
        style={styles.progress}
        accessibilityRole="tablist"
        onLayout={onProgressLayout}
      >
        {progressW > 0 ? (
          <View
            style={[
              styles.thumb,
              {
                width: segW,
                left: thumbLeft,
              },
            ]}
          />
        ) : null}
        {PAGE_LABELS.map((label, i) => (
          <Pressable
            key={label}
            accessibilityRole="tab"
            accessibilityState={{ selected: page === i }}
            onPress={() => goToPage(i)}
            style={styles.progressItem}
          >
            <Text style={[styles.progressLabel, { color: c.textSub }, page === i && { color: c.text }]}>
              {label}
            </Text>
            <View style={[styles.progressSeg, { backgroundColor: c.line }]} />
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    width: '100%',
    height: '100%',
    paddingTop: 14,
    paddingHorizontal: 10,
    paddingBottom: 10,
  },
  collapse: {
    position: 'absolute',
    right: 2,
    top: 8,
    width: 36,
    height: 36,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 2,
    backgroundColor: 'transparent',
  },
  viewport: {
    flex: 1,
    minHeight: 0,
    width: '100%',
    overflow: 'hidden',
  },
  slide: {
    height: '100%',
    paddingTop: 4,
    overflow: 'hidden',
  },
  metricsPage: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 40,
    paddingHorizontal: 4,
  },
  metricsSantander: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'stretch',
    gap: 10,
    minWidth: 0,
    overflow: 'hidden',
    paddingLeft: 8,
    paddingRight: 2,
  },
  metricsCol: {
    flex: 1,
    minWidth: 0,
    justifyContent: 'center',
    alignItems: 'flex-start',
    gap: 14,
  },
  metricBlock: {
    alignItems: 'flex-start',
    gap: 2,
  },
  walkLabel: {
    fontSize: 9.5,
    fontWeight: '600',
    textAlign: 'left',
  },
  hireCol: {
    flex: 1.2,
    minWidth: 0,
    overflow: 'hidden',
  },
  chartPage: {
    flex: 1,
    width: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  barsPage: {
    flex: 1,
    width: '100%',
    minWidth: 0,
    justifyContent: 'center',
    overflow: 'hidden',
    paddingRight: 2,
  },
  progress: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: PAGE_GAP,
    width: '100%',
    marginTop: 12,
    position: 'relative',
  },
  thumb: {
    position: 'absolute',
    bottom: 0,
    height: 4,
    borderRadius: 999,
    backgroundColor: brand.fuchsia,
    zIndex: 1,
  },
  progressItem: {
    flex: 1,
    alignItems: 'center',
    gap: 6,
    minWidth: 0,
  },
  progressLabel: {
    fontSize: 9.5,
    fontWeight: '600',
    textAlign: 'center',
  },
  progressSeg: {
    width: '100%',
    height: 4,
    borderRadius: 999,
  },
});

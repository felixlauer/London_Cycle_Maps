import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  PanResponder,
  StyleSheet,
  View,
} from 'react-native';
import type { RouteHover } from '../../map/routeHover';
import type { HireStation } from '../../api/santander';
import type { HireWalkStats } from '../../map/useSantanderHire';
import { useChrome } from '../../theme/useChrome';
import { REDUCED_MOTION_MS, useReduceMotion } from '../../lib/useReduceMotion';
import { CollapsedIsland } from './CollapsedIsland';
import { ExpandedIsland } from './ExpandedIsland';
import { IslandLegLatch } from './IslandLegLatch';
import { NavIsland } from './NavIsland';
import { ReportPicker } from './ReportPicker';
import type { RideReportCategory } from '../../feedback/rideReportCategories';
import { buildDistanceIndex, lngLatAtDistance } from './routeGeometry';
import { TutorialAnchor } from '../../onboarding/tutorial/TutorialAnchor';

const COLLAPSED_H = 108;
const EXPANDED_H = 240;
const COLLAPSED_R = 999;
const EXPANDED_R = 20;
const EXPAND_MS = 380;
const COLLAPSE_MS = 460;
const MORPH_MS = 280;
const EASE = Easing.bezier(0.23, 1, 0.32, 1);
/** Report face: quick in, quicker out, so a late tap still beats the timeout. */
const REPORT_IN_MS = 220;
const REPORT_OUT_MS = 160;

type Slot =
  | { type: 'elevation' }
  | { type: 'donut'; modeId: string };

/** Present only while a turn-by-turn session is running. */
export type NavIslandState = {
  distanceRemaining: number;
  durationRemaining: number;
  rerouting?: boolean;
  onEnd: () => void;
  onReport: () => void;
  reportDisabled?: boolean;
};

/** Present only while the 10 s category picker is showing. */
export type ReportPickerState = {
  /** Lighting gate from /night_status, not the UI theme. */
  isDark: boolean;
  onPick: (category: RideReportCategory) => void;
  onHoldChange: (held: boolean) => void;
};

type Props = {
  safest: Record<string, unknown>;
  slots: { left: Slot; right: Slot; bars: string[] };
  expanded: boolean;
  onExpandedChange: (v: boolean) => void;
  onOverlayHintClick?: () => void;
  overlayMode?: string | null;
  routeHover?: RouteHover | null;
  onIslandHover?: (hover: RouteHover | null) => void;
  santander?: boolean;
  pickupStation?: HireStation | null;
  dropoffStation?: HireStation | null;
  walkStats?: HireWalkStats | null;
  legCount?: number;
  activeLegIndex?: number;
  onChangeLeg?: (index: number) => void;
  units?: 'metric' | 'imperial';
  onPageChange?: (page: number) => void;
  /** Swaps the capsule body for live nav metrics; the shell stays put. */
  nav?: NavIslandState | null;
  /** Swaps the nav body for the category circles. The shell stays the nav chrome. */
  report?: ReportPickerState | null;
  canNavigate?: boolean;
  navBusy?: boolean;
  onNavigate?: () => void;
};

/**
 * Capsule / sheet shell — web shell-zone--island morph (height + radius).
 * Vertical drag morphs; expand/collapse timings differ for a calmer collapse.
 */
export function DynamicIsland({
  safest,
  slots,
  expanded,
  onExpandedChange,
  onOverlayHintClick,
  overlayMode,
  routeHover = null,
  onIslandHover,
  santander = false,
  pickupStation = null,
  dropoffStation = null,
  walkStats = null,
  legCount = 1,
  activeLegIndex = 0,
  onChangeLeg,
  units = 'metric',
  onPageChange,
  nav = null,
  report = null,
  canNavigate = false,
  navBusy = false,
  onNavigate,
}: Props) {
  const { c, themeMode } = useChrome();
  const reduceMotion = useReduceMotion();
  const shellShadowOpacity = themeMode === 'light' ? 0.08 : 0.45;
  const navMode = Boolean(nav);
  // Nav owns the capsule — analysis stays collapsed underneath it.
  const effExpanded = navMode ? false : expanded;
  const progress = useRef(new Animated.Value(effExpanded ? 1 : 0)).current;
  const progressNum = useRef(effExpanded ? 1 : 0);
  const expandedRef = useRef(effExpanded);
  const navModeRef = useRef(navMode);
  const navFade = useRef(new Animated.Value(navMode ? 1 : 0)).current;
  const reportMode = Boolean(report);
  const reportFade = useRef(new Animated.Value(reportMode ? 1 : 0)).current;
  const dragging = useRef(false);
  const [renderExpanded, setRenderExpanded] = useState(effExpanded);
  const [renderCollapsed, setRenderCollapsed] = useState(!effExpanded);
  const [renderNav, setRenderNav] = useState(navMode);
  const [renderReport, setRenderReport] = useState(reportMode);
  // Hold the last nav payload so the fade-out has something to show.
  const navSnapshotRef = useRef<NavIslandState | null>(nav);
  if (nav) navSnapshotRef.current = nav;
  const navSnapshot = navSnapshotRef.current;
  const reportSnapshotRef = useRef<ReportPickerState | null>(report);
  if (report) reportSnapshotRef.current = report;
  const reportSnapshot = reportSnapshotRef.current;
  const segRef = useRef<{
    modeId?: string;
    kind?: string;
    runIds?: (string | null | undefined)[] | null;
    runId?: string | null;
  } | null>(null);
  const pointRef = useRef<[number, number] | null>(null);

  expandedRef.current = effExpanded;
  navModeRef.current = navMode;

  const index = useMemo(() => {
    const path = Array.isArray(safest.path) ? (safest.path as number[][]) : [];
    return path.length ? buildDistanceIndex(path) : null;
  }, [safest]);

  const mapHover = routeHover?.source === 'map' ? routeHover : null;

  useEffect(() => {
    let shownExp = effExpanded;
    let shownCol = !effExpanded;
    const id = progress.addListener(({ value }) => {
      progressNum.current = value;
      // Expand: defer heavy ExpandedIsland until the morph is nearly done.
      // Collapse: keep the sheet until almost gone.
      const wantExp = effExpanded ? value > 0.88 : value > 0.08;
      const wantCol = effExpanded ? value < 0.78 : value < 0.92;
      if (wantExp !== shownExp) {
        shownExp = wantExp;
        setRenderExpanded(wantExp);
      }
      if (wantCol !== shownCol) {
        shownCol = wantCol;
        setRenderCollapsed(wantCol);
      }
    });
    return () => progress.removeListener(id);
  }, [progress, effExpanded]);

  // Reduce Motion turns the 108 → 240 morph and the plan ↔ nav swap into a
  // short cross-fade. Start and end states are unchanged, and stopAnimation
  // still hands over the presentation value, so a drag stays interruptible.
  const navMorphMs = reduceMotion ? REDUCED_MOTION_MS : MORPH_MS;

  const animateTo = useCallback((next: boolean) => {
    progress.stopAnimation((v) => {
      progressNum.current = typeof v === 'number' ? v : progressNum.current;
    });
    Animated.timing(progress, {
      toValue: next ? 1 : 0,
      duration: reduceMotion
        ? REDUCED_MOTION_MS
        : (next ? EXPAND_MS : COLLAPSE_MS),
      easing: reduceMotion ? Easing.linear : EASE,
      useNativeDriver: false,
    }).start(({ finished }) => {
      if (!finished) return;
      setRenderExpanded(next);
      setRenderCollapsed(!next);
    });
  }, [progress, reduceMotion]);

  useEffect(() => {
    if (dragging.current) return;
    animateTo(effExpanded);
  }, [effExpanded, animateTo]);

  useEffect(() => {
    Animated.timing(navFade, {
      toValue: navMode ? 1 : 0,
      duration: navMorphMs,
      easing: reduceMotion ? Easing.linear : EASE,
      useNativeDriver: false,
    }).start();
    if (navMode) {
      setRenderNav(true);
      return undefined;
    }
    const id = setTimeout(() => setRenderNav(false), navMorphMs);
    return () => clearTimeout(id);
  }, [navMode, navFade, navMorphMs, reduceMotion]);

  useEffect(() => {
    const duration = reportMode ? REPORT_IN_MS : REPORT_OUT_MS;
    // Interruptible: a category tap during the timeout reverse wins immediately.
    reportFade.stopAnimation();
    Animated.timing(reportFade, {
      toValue: reportMode ? 1 : 0,
      duration,
      easing: EASE,
      useNativeDriver: false,
    }).start();
    if (reportMode) {
      setRenderReport(true);
      return undefined;
    }
    const id = setTimeout(() => setRenderReport(false), duration);
    return () => clearTimeout(id);
  }, [reportMode, reportFade]);

  const pushHover = useCallback(() => {
    if (!onIslandHover) return;
    const seg = segRef.current;
    const point = pointRef.current;
    if (!seg && !point) {
      onIslandHover(null);
      return;
    }
    onIslandHover({ source: 'island', ...(seg || {}), point });
  }, [onIslandHover]);

  const handleSegmentHover = useCallback((seg: {
    modeId?: string;
    kind?: string;
    runIds?: (string | undefined)[] | null;
  } | null) => {
    segRef.current = seg
      ? {
        modeId: seg.modeId,
        kind: seg.kind,
        runIds: seg.runIds || null,
        runId: seg.runIds?.length === 1 ? seg.runIds[0] : null,
      }
      : null;
    pushHover();
  }, [pushHover]);

  const handleScrub = useCallback((d: number | null) => {
    pointRef.current = d != null && index ? lngLatAtDistance(index, d) : null;
    pushHover();
  }, [index, pushHover]);

  useEffect(() => {
    segRef.current = null;
    pointRef.current = null;
    pushHover();
  }, [effExpanded, pushHover]);

  // Drive morph from `expanded` only — avoid double animateTo (commit + effect).
  const commitExpanded = useCallback((next: boolean) => {
    dragging.current = false;
    onExpandedChange(next);
  }, [onExpandedChange]);

  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, g) => {
        // Nav body has no sheet to pull up.
        if (navModeRef.current) return false;
        // Stricter when expanded so chart scrub / pager aren't stolen.
        const minDy = expandedRef.current ? 22 : 12;
        return Math.abs(g.dy) > minDy && Math.abs(g.dy) > Math.abs(g.dx) * 1.35;
      },
      onPanResponderGrant: () => {
        dragging.current = true;
        progress.stopAnimation((v) => {
          progressNum.current = v;
        });
      },
      onPanResponderMove: (_, g) => {
        const span = EXPANDED_H - COLLAPSED_H;
        const base = expandedRef.current ? 1 : 0;
        const delta = -g.dy / span;
        const next = Math.max(0, Math.min(1, base + delta));
        progress.setValue(next);
      },
      onPanResponderRelease: (_, g) => {
        const v = progressNum.current;
        const flickUp = g.vy < -0.55 || g.dy < -56;
        const flickDown = g.vy > 0.55 || g.dy > 56;
        if (flickUp || (!expandedRef.current && v > 0.4)) {
          commitExpanded(true);
        } else if (flickDown || (expandedRef.current && v < 0.4)) {
          commitExpanded(false);
        } else {
          commitExpanded(expandedRef.current);
        }
      },
      onPanResponderTerminate: () => {
        commitExpanded(expandedRef.current);
      },
    }),
  ).current;

  const height = progress.interpolate({
    inputRange: [0, 1],
    outputRange: [COLLAPSED_H, EXPANDED_H],
  });
  const borderRadius = progress.interpolate({
    inputRange: [0, 1],
    outputRange: [COLLAPSED_R, EXPANDED_R],
  });
  const collapsedOpacity = progress.interpolate({
    inputRange: [0, 0.4, 1],
    outputRange: [1, 0.15, 0],
  });
  const expandedOpacity = progress.interpolate({
    inputRange: [0, 0.5, 1],
    outputRange: [0, 0.25, 1],
  });
  // Plan body dims as the nav body arrives — one capsule, two faces.
  const planOpacity = Animated.multiply(
    collapsedOpacity,
    Animated.subtract(1, navFade),
  );
  // Nav metrics step aside for the picker rather than stacking behind it.
  const navOpacity = Animated.multiply(navFade, Animated.subtract(1, reportFade));

  return (
    <View style={styles.wrap} collapsable={false}>
      {legCount > 1 && onChangeLeg && !navMode ? (
        <View style={styles.latchSlot} pointerEvents="box-none">
          <IslandLegLatch
            legCount={legCount}
            activeLegIndex={activeLegIndex}
            onChangeLeg={onChangeLeg}
          />
        </View>
      ) : null}
      {/* Measure sibling — do not wrap the animated shell (broke chevron/shadow). */}
      <TutorialAnchor
        id="tut-island"
        opts={{ radius: effExpanded ? 20 : 999, capsule: !effExpanded }}
        style={styles.measure}
        pointerEvents="none"
      >
        <View style={StyleSheet.absoluteFill} pointerEvents="none" />
      </TutorialAnchor>
      <Animated.View
        style={[styles.shell, { height, borderRadius, backgroundColor: c.shellBg, borderColor: c.shellBorder, shadowOpacity: shellShadowOpacity }]}
        accessibilityLabel="Route analysis"
        {...pan.panHandlers}
      >
        {renderCollapsed ? (
          <Animated.View
            style={[styles.layer, { opacity: planOpacity }]}
            pointerEvents={effExpanded || navMode ? 'none' : 'auto'}
          >
            <CollapsedIsland
              safest={safest}
              slots={slots}
              onExpand={() => commitExpanded(true)}
              externalHover={mapHover}
              onSegmentHover={handleSegmentHover}
              units={units}
              canNavigate={canNavigate && !navMode}
              navBusy={navBusy}
              onNavigate={onNavigate}
            />
          </Animated.View>
        ) : null}
        {renderExpanded ? (
          <Animated.View
            style={[styles.layer, { opacity: expandedOpacity }]}
            pointerEvents={effExpanded ? 'auto' : 'none'}
          >
            <ExpandedIsland
              safest={safest}
              barModes={slots.bars}
              overlayMode={overlayMode}
              onCollapse={() => commitExpanded(false)}
              onOverlayHintClick={onOverlayHintClick}
              externalHover={mapHover}
              onSegmentHover={handleSegmentHover}
              onScrub={handleScrub}
              santander={santander}
              pickupStation={pickupStation}
              dropoffStation={dropoffStation}
              walkStats={walkStats}
              units={units}
              onPageChange={onPageChange}
            />
          </Animated.View>
        ) : null}
        {renderNav && navSnapshot ? (
          <Animated.View
            style={[styles.layer, { opacity: navOpacity }]}
            pointerEvents={navMode && !reportMode ? 'auto' : 'none'}
          >
            <NavIsland
              distanceRemaining={navSnapshot.distanceRemaining}
              durationRemaining={navSnapshot.durationRemaining}
              units={units}
              rerouting={navSnapshot.rerouting}
              onEnd={navSnapshot.onEnd}
              onReport={navSnapshot.onReport}
              reportDisabled={navSnapshot.reportDisabled}
            />
          </Animated.View>
        ) : null}
        {renderReport && reportSnapshot ? (
          <Animated.View
            style={[styles.layer, { opacity: reportFade }]}
            pointerEvents={reportMode ? 'auto' : 'none'}
          >
            <ReportPicker
              isDark={reportSnapshot.isDark}
              onPick={reportSnapshot.onPick}
              onHoldChange={reportSnapshot.onHoldChange}
            />
          </Animated.View>
        ) : null}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    width: '100%',
    position: 'relative',
    overflow: 'visible',
  },
  measure: {
    ...StyleSheet.absoluteFill,
    zIndex: 0,
  },
  latchSlot: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: '100%',
    alignItems: 'center',
    zIndex: 3,
  },
  shell: {
    width: '100%',
    borderWidth: 1,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 12,
    zIndex: 1,
  },
  layer: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
  },
});

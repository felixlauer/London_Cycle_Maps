import { useCallback, useEffect, useMemo, useRef } from 'react';
import {
  Animated,
  Dimensions,
  Easing,
  PanResponder,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { ChevronDown, RefreshCw } from 'lucide-react-native';
import { ManeuverIcon } from './ManeuverIcon';
import { formatManeuverDistance, formatStepDistance, type Units } from './navFormat';
import type { FlatStep } from './navSteps';
import { useSafeAreaTop } from '../lib/safeArea';
import { brand, space } from '../theme/tokens';
import { useChrome } from '../theme/useChrome';

/** Then-chip appears once the maneuver is close enough to matter. */
const THEN_VISIBLE_M = 400;
const THEN_H = 38;
const ROW_H = 52;
const EASE = Easing.bezier(0.23, 1, 0.32, 1);
const OPEN_MS = 260;
const CLOSE_MS = 200;
const SPIN_MS = 1100;
/** Stale guidance stays legible but visibly out of play. */
const REROUTE_DIM = 0.45;

type Props = {
  steps: FlatStep[];
  /**
   * Index of the maneuver being ridden towards. Pairs with `stepDistanceRemaining`,
   * which counts down to that maneuver.
   */
  upcomingIndex: number;
  /** Metres to the upcoming maneuver, from the engine. */
  stepDistanceRemaining: number;
  units?: Units;
  /** Flask is replanning — guidance is stale until the new line lands. */
  rerouting?: boolean;
  expanded: boolean;
  onExpandedChange: (next: boolean) => void;
};

/**
 * Top instruction banner: maneuver icon, live countdown, instruction, and a
 * "Then" chip for the maneuver after it. Pull down (or tap the chevron) to see
 * the whole turn list.
 */
export function NavInstructionBanner({
  steps,
  upcomingIndex,
  stepDistanceRemaining,
  units = 'metric',
  rerouting = false,
  expanded,
  onExpandedChange,
}: Props) {
  const topInset = useSafeAreaTop();
  const { c, themeMode } = useChrome();
  const shadowOpacity = themeMode === 'light' ? 0.1 : 0.5;

  const current = steps[upcomingIndex];
  const next = steps[upcomingIndex + 1];
  const thenVisible = Boolean(next) && !rerouting && stepDistanceRemaining <= THEN_VISIBLE_M;

  const listH = useMemo(() => {
    const screenH = Dimensions.get('window').height;
    const budget = Math.round(screenH * 0.46);
    return Math.min(budget, Math.max(ROW_H * 2, steps.length * ROW_H + 12));
  }, [steps.length]);

  const enter = useRef(new Animated.Value(0)).current;
  const open = useRef(new Animated.Value(expanded ? 1 : 0)).current;
  const then = useRef(new Animated.Value(thenVisible ? 1 : 0)).current;
  const spin = useRef(new Animated.Value(0)).current;
  const openNum = useRef(expanded ? 1 : 0);
  const expandedRef = useRef(expanded);
  const scrollRef = useRef<ScrollView>(null);

  expandedRef.current = expanded;

  useEffect(() => {
    Animated.spring(enter, {
      toValue: 1,
      damping: 16,
      stiffness: 170,
      mass: 0.9,
      useNativeDriver: true,
    }).start();
  }, [enter]);

  useEffect(() => {
    const id = open.addListener(({ value }) => {
      openNum.current = value;
    });
    return () => open.removeListener(id);
  }, [open]);

  useEffect(() => {
    Animated.timing(open, {
      toValue: expanded ? 1 : 0,
      duration: expanded ? OPEN_MS : CLOSE_MS,
      easing: EASE,
      useNativeDriver: false,
    }).start();
  }, [expanded, open]);

  useEffect(() => {
    Animated.timing(then, {
      toValue: thenVisible ? 1 : 0,
      duration: 200,
      easing: EASE,
      useNativeDriver: false,
    }).start();
  }, [thenVisible, then]);

  // Keep the active row in view as the ride progresses.
  useEffect(() => {
    if (!expanded) return;
    const y = Math.max(0, (upcomingIndex - 1) * ROW_H);
    const id = setTimeout(() => scrollRef.current?.scrollTo({ y, animated: true }), OPEN_MS);
    return () => clearTimeout(id);
  }, [expanded, upcomingIndex]);

  useEffect(() => {
    if (!rerouting) {
      spin.setValue(0);
      return;
    }
    const loop = Animated.loop(
      Animated.timing(spin, {
        toValue: 1,
        duration: SPIN_MS,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    );
    loop.start();
    return () => loop.stop();
  }, [rerouting, spin]);

  const toggle = useCallback(() => {
    onExpandedChange(!expandedRef.current);
  }, [onExpandedChange]);

  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, g) =>
        Math.abs(g.dy) > 12 && Math.abs(g.dy) > Math.abs(g.dx) * 1.3,
      onPanResponderMove: (_, g) => {
        const base = expandedRef.current ? 1 : 0;
        const next2 = Math.max(0, Math.min(1, base + g.dy / 180));
        open.setValue(next2);
      },
      onPanResponderRelease: (_, g) => {
        const flickDown = g.vy > 0.5 || g.dy > 48;
        const flickUp = g.vy < -0.5 || g.dy < -48;
        if (flickDown) onExpandedChange(true);
        else if (flickUp) onExpandedChange(false);
        else onExpandedChange(openNum.current > 0.5);
      },
      onPanResponderTerminate: () => {
        onExpandedChange(expandedRef.current);
      },
    }),
  ).current;

  if (!current && !rerouting) return null;

  const translateY = enter.interpolate({ inputRange: [0, 1], outputRange: [-180, 0] });
  const listHeight = open.interpolate({ inputRange: [0, 1], outputRange: [0, listH] });
  const listOpacity = open.interpolate({ inputRange: [0, 0.35, 1], outputRange: [0, 0, 1] });
  const chevronRotate = open.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '180deg'] });
  const thenHeight = then.interpolate({ inputRange: [0, 1], outputRange: [0, THEN_H] });
  const thenOpacity = then;
  const thenShift = then.interpolate({ inputRange: [0, 1], outputRange: [-6, 0] });
  const spinRotate = spin.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });

  return (
    <View style={[styles.wrap, { paddingTop: topInset }]} collapsable={false}>
    <Animated.View
      style={[
        styles.panel,
        {
          backgroundColor: c.shellBg,
          borderColor: c.shellBorder,
          shadowOpacity,
          opacity: enter,
          transform: [{ translateY }],
        },
      ]}
      accessibilityLabel={rerouting ? 'Reconnecting' : 'Next maneuver'}
      {...pan.panHandlers}
    >
      <Pressable
        onPress={toggle}
        accessibilityRole="button"
        accessibilityLabel={expanded ? 'Hide all directions' : 'Show all directions'}
        style={styles.headRow}
      >
        <View style={[styles.icon, rerouting && { backgroundColor: c.surface }]}>
          {rerouting ? (
            <Animated.View style={{ transform: [{ rotate: spinRotate }] }}>
              <RefreshCw size={26} color={c.textSub} strokeWidth={2.4} />
            </Animated.View>
          ) : current ? (
            <ManeuverIcon
              type={current.type}
              modifier={current.modifier}
              bearingBefore={current.bearingBefore}
              bearingAfter={current.bearingAfter}
              size={30}
              color="#FFFFFF"
              strokeWidth={2.4}
            />
          ) : null}
        </View>
        <View style={styles.headBody}>
          {/* Countdown is hidden, not blanked, so the row keeps its height. */}
          <Text
            style={[
              styles.distance,
              { color: brand.fuchsia, opacity: rerouting ? 0 : 1 },
            ]}
          >
            {formatManeuverDistance(stepDistanceRemaining, units)}
          </Text>
          <Text
            style={[
              styles.instruction,
              { color: rerouting ? c.textSub : c.text },
            ]}
            numberOfLines={2}
          >
            {rerouting ? 'Reconnecting…' : (current?.instruction || '')}
          </Text>
        </View>
        <Animated.View style={{ transform: [{ rotate: chevronRotate }] }}>
          <ChevronDown size={20} color={c.icon} strokeWidth={2.25} />
        </Animated.View>
      </Pressable>

      <Animated.View
        style={[styles.thenWrap, { height: thenHeight, opacity: thenOpacity }]}
        pointerEvents="none"
      >
        {next ? (
          <Animated.View
            style={[
              styles.thenRow,
              { borderTopColor: c.line, transform: [{ translateY: thenShift }] },
            ]}
          >
            <Text style={[styles.thenLabel, { color: c.textSub }]}>Then</Text>
            <ManeuverIcon
              type={next.type}
              modifier={next.modifier}
              bearingBefore={next.bearingBefore}
              bearingAfter={next.bearingAfter}
              size={16}
              color={c.textSub}
              strokeWidth={2.4}
            />
            <Text style={[styles.thenText, { color: c.textSub }]} numberOfLines={1}>
              {next.instruction}
            </Text>
          </Animated.View>
        ) : null}
      </Animated.View>

      <Animated.View style={{ height: listHeight, opacity: listOpacity, overflow: 'hidden' }}>
        <View style={[styles.listRule, { backgroundColor: c.line }]} />
        <ScrollView
          ref={scrollRef}
          scrollEnabled={expanded}
          showsVerticalScrollIndicator={false}
          contentContainerStyle={[styles.list, rerouting && { opacity: REROUTE_DIM }]}
        >
          {steps.map((step, i) => {
            const active = i === upcomingIndex && !rerouting;
            const done = i < upcomingIndex;
            return (
              <View
                key={step.key}
                style={[
                  styles.row,
                  active && { backgroundColor: c.surface },
                  done && styles.rowDone,
                ]}
              >
                <ManeuverIcon
                  type={step.type}
                  modifier={step.modifier}
                  bearingBefore={step.bearingBefore}
                  bearingAfter={step.bearingAfter}
                  size={20}
                  color={active ? brand.fuchsia : c.icon}
                  strokeWidth={2.3}
                />
                <Text
                  style={[
                    styles.rowText,
                    { color: active ? c.text : c.textSub },
                    active && styles.rowTextActive,
                  ]}
                  numberOfLines={1}
                >
                  {step.instruction}
                </Text>
                <Text style={[styles.rowDist, { color: c.textSub }]}>
                  {active
                    ? formatManeuverDistance(stepDistanceRemaining, units)
                    : formatStepDistance(step.distance, units)}
                </Text>
              </View>
            );
          })}
        </ScrollView>
      </Animated.View>
    </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { width: '100%' },
  panel: {
    width: '100%',
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: space.panelPad,
    paddingTop: space.panelPad,
    paddingBottom: 4,
    shadowColor: '#000',
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 8,
    overflow: 'hidden',
  },
  headRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    paddingBottom: 10,
  },
  icon: {
    width: 56,
    height: 56,
    borderRadius: 14,
    backgroundColor: brand.fuchsia,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  headBody: {
    flex: 1,
    minWidth: 0,
  },
  distance: {
    fontSize: 15,
    fontWeight: '800',
    letterSpacing: -0.2,
    fontVariant: ['tabular-nums'],
  },
  instruction: {
    marginTop: 1,
    fontSize: 18,
    fontWeight: '700',
    lineHeight: 22,
    letterSpacing: -0.4,
  },
  thenWrap: {
    overflow: 'hidden',
  },
  thenRow: {
    height: THEN_H,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  thenLabel: {
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  thenText: {
    flex: 1,
    fontSize: 13.5,
    fontWeight: '600',
  },
  listRule: {
    height: StyleSheet.hairlineWidth,
    marginBottom: 4,
  },
  list: {
    paddingBottom: 8,
  },
  row: {
    height: ROW_H,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 8,
    borderRadius: space.radiusSm,
  },
  rowDone: {
    opacity: 0.45,
  },
  rowText: {
    flex: 1,
    fontSize: 14,
    fontWeight: '600',
  },
  rowTextActive: {
    fontWeight: '700',
  },
  rowDist: {
    fontSize: 12.5,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
});

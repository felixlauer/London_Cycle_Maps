import { useEffect, useMemo, useRef } from 'react';
import { AccessibilityInfo, Animated, Easing, Pressable, StyleSheet, Text, View } from 'react-native';
import { reportSlots, type RideReportCategory } from '../../feedback/rideReportCategories';
import { DONUT } from './NavIsland';
import { useChrome } from '../../theme/useChrome';

const EASE = Easing.bezier(0.23, 1, 0.32, 1);
const ENTER_MS = 220;
const STAGGER_MS = 40;
/** Slot 4 swaps glyph and colour on the darkness gate — never re-enters. */
const SWAP_MS = 160;

type Props = {
  /** Lighting gate from /night_status, not the UI theme. */
  isDark: boolean;
  onPick: (category: RideReportCategory) => void;
  /** Pauses the parent's 10 s timer while a finger is down. */
  onHoldChange: (held: boolean) => void;
};

/**
 * The four choices, shown for 10 s after the Flag.
 *
 * Same recipe as the Navigate play button: solid hub fill, no ring, white
 * glyph (near-black on banana), and a caption under every circle. Circles stay
 * 68 px.
 */
export function ReportPicker({ isDark, onPick, onHoldChange }: Props) {
  const { c } = useChrome();
  const slots = useMemo(() => reportSlots(isDark), [isDark]);
  const enter = useRef(slots.map(() => new Animated.Value(0))).current;
  const reduceMotion = useRef(false);

  useEffect(() => {
    let cancelled = false;
    AccessibilityInfo.isReduceMotionEnabled()
      .then((on) => {
        if (!cancelled) reduceMotion.current = on;
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const animations = enter.map((value, i) =>
      Animated.timing(value, {
        toValue: 1,
        duration: ENTER_MS,
        delay: reduceMotion.current ? 0 : i * STAGGER_MS,
        easing: EASE,
        useNativeDriver: true,
      }),
    );
    Animated.parallel(animations).start();
    // Deliberately not keyed on `slots`: a mid-picker day/night swap changes
    // slot 4's colour, it does not replay the entrance or restart the timer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <View style={styles.root} accessibilityLabel="What is wrong here?">
      {slots.map((slot, i) => (
        <Animated.View
          key={i}
          style={[
            styles.slot,
            {
              opacity: enter[i],
              transform: reduceMotion.current
                ? []
                : [
                  {
                    scale: enter[i].interpolate({
                      inputRange: [0, 1],
                      outputRange: [0.95, 1],
                    }),
                  },
                ],
            },
          ]}
          // Stagger must never gate a tap: the rider may be faster than it.
          pointerEvents="auto"
        >
          <ReportCircle
            slot={slot}
            captionColor={c.textSub}
            onPick={onPick}
            onHoldChange={onHoldChange}
          />
        </Animated.View>
      ))}
    </View>
  );
}

function ReportCircle({
  slot,
  captionColor,
  onPick,
  onHoldChange,
}: {
  slot: RideReportCategory;
  captionColor: string;
  onPick: (category: RideReportCategory) => void;
  onHoldChange: (held: boolean) => void;
}) {
  const swap = useRef(new Animated.Value(1)).current;
  const firstRun = useRef(true);

  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    swap.setValue(0);
    Animated.timing(swap, {
      toValue: 1,
      duration: SWAP_MS,
      easing: EASE,
      useNativeDriver: true,
    }).start();
  }, [slot.id, swap]);

  const { Icon } = slot;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={slot.label}
      hitSlop={6}
      onPressIn={() => onHoldChange(true)}
      onPressOut={() => onHoldChange(false)}
      onPress={() => onPick(slot)}
      style={({ pressed }) => [styles.hit, pressed && styles.pressed]}
    >
      <View style={[styles.circle, { backgroundColor: slot.hub }]}>
        <Animated.View style={{ opacity: swap }}>
          <Icon size={28} strokeWidth={2.3} color={slot.onHub} />
        </Animated.View>
      </View>
      <Text style={[styles.caption, { color: captionColor }]} numberOfLines={1}>
        {slot.shortLabel}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: {
    height: 108,
    width: '100%',
    paddingHorizontal: 8,
    flexDirection: 'row',
    alignItems: 'center',
  },
  slot: {
    flex: 1,
    minWidth: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  hit: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    maxWidth: '100%',
  },
  circle: {
    width: DONUT,
    height: DONUT,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  caption: {
    fontSize: 11,
    fontWeight: '600',
    lineHeight: 13,
    textAlign: 'center',
    maxWidth: '100%',
  },
  pressed: { transform: [{ scale: 0.97 }] },
});

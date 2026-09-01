import { useEffect, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  LayoutChangeEvent,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { ChevronUp, Play } from 'lucide-react-native';
import type { RouteHover } from '../../map/routeHover';
import { brand } from '../../theme/tokens';
import { useChrome } from '../../theme/useChrome';
import { ElevationSparkline } from './ElevationSparkline';
import { MetricCell } from './MetricCell';
import { ModeDonut } from './ModeDonut';
import { formatDistanceParts, formatDurationParts, tripLengthM } from './metrics';
import { islandModeMeta } from './modeData';
import { TutorialAnchor } from '../../onboarding/tutorial/TutorialAnchor';

type Slot =
  | { type: 'elevation' }
  | { type: 'donut'; modeId: string };

type Props = {
  safest: Record<string, unknown>;
  slots: { left: Slot; right: Slot };
  onExpand: () => void;
  externalHover?: RouteHover | null;
  onSegmentHover?: (seg: { modeId?: string; kind: string; runIds?: (string | undefined)[] } | null) => void;
  units?: 'metric' | 'imperial';
  /** Location services on + route revealed — trip metrics stack so Navigate fits. */
  canNavigate?: boolean;
  navBusy?: boolean;
  onNavigate?: () => void;
};

const DONUT = 56;
const SPARK_ASPECT = 0.42;
const SPARK_SIDE_PAD = 10;

function ContentSlot({
  slot,
  safest,
  externalHover,
  onHoverChange,
}: {
  slot: Slot;
  safest: Record<string, unknown>;
  externalHover?: RouteHover | null;
  onHoverChange?: (seg: { modeId: string; kind: string } | null) => void;
}) {
  const { c } = useChrome();
  const [slotW, setSlotW] = useState(0);
  const onSlotLayout = (e: LayoutChangeEvent) => {
    setSlotW(e.nativeEvent.layout.width);
  };

  if (slot.type === 'elevation') {
    const available = slotW > 0 ? slotW : 72;
    const plotW = Math.max(40, Math.floor(available - SPARK_SIDE_PAD * 2));
    const plotH = Math.max(22, Math.round(plotW * SPARK_ASPECT));
    return (
      <View style={[styles.slot, styles.slotElev]} onLayout={onSlotLayout}>
        <View style={styles.sparkWrap}>
          <ElevationSparkline
            profile={safest.elevation_profile as { d_m?: number; elev_m?: number }[] | undefined}
            width={plotW}
            height={plotH}
          />
        </View>
        <Text style={[styles.caption, { color: c.textSub }]}>Elevation</Text>
      </View>
    );
  }
  const meta = islandModeMeta(slot.modeId);
  return (
    <View style={styles.slot}>
      <View style={styles.visual}>
        <ModeDonut
          safest={safest}
          modeId={slot.modeId}
          size={DONUT}
          strokeWidth={5.5}
          externalHover={externalHover}
          onHoverChange={onHoverChange}
        />
      </View>
      <Text style={[styles.caption, { color: c.textSub }]} numberOfLines={1}>
        {meta?.label || slot.modeId}
      </Text>
    </View>
  );
}

function StackedMetrics({
  time,
  dist,
}: {
  time: { value: string; unit: string };
  dist: { value: string; unit: string };
}) {
  const { c } = useChrome();
  return (
    <View style={styles.stack} accessibilityLabel="Trip time and distance">
      <View style={styles.stackRow}>
        <Text style={[styles.stackValue, { color: c.text }]}>{time.value}</Text>
        <Text style={[styles.stackUnit, { color: c.textSub }]}>{time.unit}</Text>
      </View>
      <View style={styles.stackRow}>
        <Text style={[styles.stackValueSm, { color: c.textSub }]}>{dist.value}</Text>
        <Text style={[styles.stackUnitSm, { color: c.textSub }]}>{dist.unit}</Text>
      </View>
    </View>
  );
}

function NavigateCell({ busy, onPress }: { busy: boolean; onPress: () => void }) {
  const { c } = useChrome();
  const pulse = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (!busy) {
      pulse.setValue(1);
      return undefined;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 0.4,
          duration: 460,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 1,
          duration: 460,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [busy, pulse]);

  return (
    <View style={styles.slot}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Start turn-by-turn navigation"
        accessibilityState={{ busy }}
        disabled={busy}
        onPress={onPress}
        style={({ pressed }) => [styles.navBtn, pressed && styles.navBtnPressed]}
      >
        <Animated.View style={{ opacity: pulse }}>
          <Play size={24} strokeWidth={2.4} color="#FFFFFF" fill="#FFFFFF" />
        </Animated.View>
      </Pressable>
      <Text style={[styles.caption, { color: c.textSub }]} numberOfLines={1}>
        Navigate
      </Text>
    </View>
  );
}

/**
 * Collapsed Dynamic Island — web CollapsedIsland mobile.
 * Capsule shell is the parent DynamicIsland; this is the 4-cell body + chevron.
 */
export function CollapsedIsland({
  safest,
  slots,
  onExpand,
  externalHover = null,
  onSegmentHover,
  units = 'metric',
  canNavigate = false,
  navBusy = false,
  onNavigate,
}: Props) {
  const { c } = useChrome();
  const stats = (safest.stats || {}) as { duration_min?: number; length_m?: number; distance_m?: number };
  const time = formatDurationParts(stats.duration_min);
  const dist = formatDistanceParts(tripLengthM(stats), units);
  const lastSeg = useRef<string | null>(null);

  const handleHover = (seg: { modeId: string; kind: string } | null) => {
    const key = seg ? `${seg.modeId}|${seg.kind}` : null;
    if (key === lastSeg.current) return;
    lastSeg.current = key;
    onSegmentHover?.(seg);
  };

  return (
    <View style={styles.root}>
      <View style={styles.grid}>
        {canNavigate && onNavigate ? (
          <View style={styles.cell}>
            <StackedMetrics time={time} dist={dist} />
          </View>
        ) : (
          <>
            <View style={styles.cell}>
              <MetricCell value={time.value} unit={time.unit} label="Trip time" />
            </View>
            <View style={styles.cell}>
              <MetricCell value={dist.value} unit={dist.unit} label="Trip distance" />
            </View>
          </>
        )}
        <View style={styles.cell}>
          <ContentSlot
            slot={slots.left}
            safest={safest}
            externalHover={externalHover}
            onHoverChange={handleHover}
          />
        </View>
        <View style={styles.cell}>
          <ContentSlot
            slot={slots.right}
            safest={safest}
            externalHover={externalHover}
            onHoverChange={handleHover}
          />
        </View>
        {canNavigate && onNavigate ? (
          <View style={styles.cell}>
            <NavigateCell busy={navBusy} onPress={onNavigate} />
          </View>
        ) : null}
      </View>

      <TutorialAnchor
        id="tut-island-expand"
        opts={{ capsule: true }}
        style={styles.chevronAnchor}
      >
        <Pressable
          accessibilityLabel="Expand route analysis"
          onPress={onExpand}
          hitSlop={6}
          style={({ pressed }) => [styles.chevron, pressed && { opacity: 0.7 }]}
        >
          <ChevronUp size={16} strokeWidth={2.2} color={c.textSub} />
        </Pressable>
      </TutorialAnchor>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    height: 108,
    width: '100%',
    paddingHorizontal: 28,
    justifyContent: 'center',
  },
  grid: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
  },
  cell: {
    flex: 1,
    minWidth: 0,
    height: '100%',
    paddingHorizontal: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  slot: {
    width: '100%',
    alignItems: 'center',
    justifyContent: 'flex-start',
    gap: 4,
    overflow: 'hidden',
  },
  slotElev: {
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  visual: {
    width: DONUT,
    height: DONUT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stack: {
    alignItems: 'flex-start',
    gap: 1,
  },
  stackRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 4,
  },
  stackValue: {
    fontSize: 26,
    fontWeight: '800',
    letterSpacing: -0.9,
    lineHeight: 28,
    fontVariant: ['tabular-nums'],
  },
  stackUnit: {
    fontSize: 12.5,
    fontWeight: '600',
  },
  stackValueSm: {
    fontSize: 15,
    fontWeight: '700',
    letterSpacing: -0.3,
    fontVariant: ['tabular-nums'],
  },
  stackUnitSm: {
    fontSize: 11.5,
    fontWeight: '600',
  },
  navBtn: {
    width: DONUT,
    height: DONUT,
    borderRadius: 999,
    backgroundColor: brand.fuchsia,
    alignItems: 'center',
    justifyContent: 'center',
  },
  navBtnPressed: {
    transform: [{ scale: 0.93 }],
  },
  sparkWrap: {
    width: '100%',
    alignItems: 'center',
    minHeight: 22,
  },
  caption: {
    fontSize: 11.5,
    fontWeight: '600',
    lineHeight: 14,
    textAlign: 'center',
    maxWidth: '100%',
  },
  /** Absolute host must be the TutorialAnchor — wrapping broke position before. */
  chevronAnchor: {
    position: 'absolute',
    right: 2,
    top: '50%',
    marginTop: -18,
    width: 36,
    height: 36,
  },
  chevron: {
    width: 36,
    height: 36,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
  },
});

import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Flag, X } from 'lucide-react-native';
import {
  formatEta,
  formatRemainingDistance,
  formatRemainingDuration,
  type Units,
} from '../../navigation/navFormat';
import { REPORT_TRIGGER_HUB } from '../../feedback/rideReportCategories';
import { useChrome } from '../../theme/useChrome';

/** Same capsule height as the planning island; circles scaled up for gloved taps. */
export const DONUT = 68;

type Props = {
  distanceRemaining: number;
  durationRemaining: number;
  units?: Units;
  /** Replanning — the figures below belong to the line being replaced. */
  rerouting?: boolean;
  onEnd: () => void;
  onReport: () => void;
  /** Cooling down after a completed report; the circle still reads as present. */
  reportDisabled?: boolean;
};

/**
 * Nav variant of the collapsed island: end nav, live trip metrics, report.
 * Same 108 px capsule body as the planning island so the morph is a crossfade.
 *
 * Report is filled rather than outlined: it is the one control here a rider
 * hits while moving, so it has to be findable without looking twice.
 */
export function NavIsland({
  distanceRemaining,
  durationRemaining,
  units = 'metric',
  rerouting = false,
  onEnd,
  onReport,
  reportDisabled = false,
}: Props) {
  const { c } = useChrome();
  const time = formatRemainingDuration(durationRemaining);
  const dist = formatRemainingDistance(distanceRemaining, units);
  const eta = formatEta(durationRemaining);

  return (
    <View style={styles.root}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="End navigation"
        onPress={onEnd}
        hitSlop={8}
        style={({ pressed }) => [
          styles.circle,
          { borderColor: c.shellBorder, backgroundColor: c.surface },
          pressed && styles.pressed,
        ]}
      >
        <X size={28} strokeWidth={2.3} color={c.textSub} />
      </Pressable>

      <View
        style={[styles.metrics, rerouting && styles.metricsStale]}
        accessibilityLabel="Remaining time and distance"
      >
        <View style={styles.timeRow}>
          <Text style={[styles.timeValue, { color: c.text }]}>{time.value}</Text>
          <Text style={[styles.timeUnit, { color: c.textSub }]}>{time.unit}</Text>
        </View>
        <Text style={[styles.sub, { color: c.textSub }]} numberOfLines={1}>
          {`${dist.value} ${dist.unit} · ${eta}`}
        </Text>
      </View>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Report a problem with this route"
        disabled={reportDisabled}
        onPress={onReport}
        hitSlop={8}
        style={({ pressed }) => [
          styles.circle,
          {
            borderWidth: 0,
            backgroundColor: REPORT_TRIGGER_HUB,
          },
          reportDisabled && styles.reportCooling,
          pressed && styles.reportPressed,
        ]}
      >
        <Flag size={28} strokeWidth={2.3} color="#FFFFFF" />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    height: 108,
    width: '100%',
    paddingHorizontal: 20,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  circle: {
    width: DONUT,
    height: DONUT,
    borderRadius: 999,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  pressed: { transform: [{ scale: 0.94 }] },
  // Shallower than the End press: a big filled circle reads as moving more.
  reportPressed: { transform: [{ scale: 0.97 }] },
  reportCooling: { opacity: 0.45 },
  metrics: {
    flex: 1,
    minWidth: 0,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  metricsStale: { opacity: 0.45 },
  timeRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 5,
  },
  timeValue: {
    fontSize: 40,
    fontWeight: '800',
    letterSpacing: -1.2,
    lineHeight: 42,
    fontVariant: ['tabular-nums'],
  },
  timeUnit: {
    fontSize: 16,
    fontWeight: '600',
  },
  sub: {
    fontSize: 15,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
});

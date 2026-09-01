import { Pressable, StyleSheet, Text, View } from 'react-native';
import { ChevronLeft, ChevronRight } from 'lucide-react-native';
import { useChrome } from '../../theme/useChrome';

type Props = {
  legCount: number;
  activeLegIndex: number;
  onChangeLeg: (index: number) => void;
};

/**
 * Compact top latch for multi-leg switching — web IslandLegLatch.
 */
export function IslandLegLatch({
  legCount,
  activeLegIndex,
  onChangeLeg,
}: Props) {
  const { c } = useChrome();

  if (legCount <= 1) return null;

  const go = (next: number) => {
    const clamped = Math.max(0, Math.min(legCount - 1, next));
    if (clamped === activeLegIndex) return;
    onChangeLeg(clamped);
  };

  return (
    <View
      style={[
        styles.latch,
        {
          borderColor: c.shellBorder,
          backgroundColor: c.shellBg,
        },
      ]}
      accessibilityRole="adjustable"
      accessibilityLabel="Route segments"
    >
      <Pressable
        accessibilityLabel="Previous segment"
        disabled={activeLegIndex <= 0}
        onPress={() => go(activeLegIndex - 1)}
        style={({ pressed }) => [
          styles.arrow,
          activeLegIndex <= 0 && styles.arrowDisabled,
          pressed && activeLegIndex > 0 && { backgroundColor: c.surface },
        ]}
        hitSlop={6}
      >
        <ChevronLeft size={14} strokeWidth={2.4} color={c.textSub} />
      </Pressable>
      <Text style={[styles.count, { color: c.text }]} accessibilityLiveRegion="polite">
        {activeLegIndex + 1}
        <Text style={[styles.sep, { color: c.textSub }]}> / </Text>
        {legCount}
      </Text>
      <Pressable
        accessibilityLabel="Next segment"
        disabled={activeLegIndex >= legCount - 1}
        onPress={() => go(activeLegIndex + 1)}
        style={({ pressed }) => [
          styles.arrow,
          activeLegIndex >= legCount - 1 && styles.arrowDisabled,
          pressed && activeLegIndex < legCount - 1 && { backgroundColor: c.surface },
        ]}
        hitSlop={6}
      >
        <ChevronRight size={14} strokeWidth={2.4} color={c.textSub} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  latch: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    height: 24,
    minWidth: 104,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderBottomWidth: 0,
    borderTopLeftRadius: 10,
    borderTopRightRadius: 10,
    // iOS soft lift only — Android elevation casts a downward blob under the latch.
    shadowColor: '#000',
    shadowRadius: 6,
    shadowOffset: { width: 0, height: -1 },
    shadowOpacity: 0.08,
    elevation: 0,
  },
  arrow: {
    width: 22,
    height: 22,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  arrowDisabled: {
    opacity: 0.35,
  },
  count: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.2,
    fontVariant: ['tabular-nums'],
    minWidth: 36,
    textAlign: 'center',
  },
  sep: {
    fontWeight: '600',
  },
});

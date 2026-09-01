import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { X } from 'lucide-react-native';
import type { NavigationPayload, NavStep } from './types';
import { ManeuverIcon } from './ManeuverIcon';
import { formatStepDistance } from './navFormat';
import { useSafeAreaTop } from '../lib/safeArea';
import { brand, space } from '../theme/tokens';
import { useChrome } from '../theme/useChrome';

type Props = {
  visible: boolean;
  navigation: NavigationPayload | null;
  busy?: boolean;
  error?: string | null;
  onClose: () => void;
};

function StepRow({ step }: { step: NavStep }) {
  const { c } = useChrome();
  const instruction = step.maneuver?.instruction || step.name || 'Continue';
  return (
    <View style={[styles.row, { backgroundColor: c.surface, borderColor: c.line }]}>
      <View style={styles.iconWrap}>
        <ManeuverIcon
          type={step.maneuver?.type}
          modifier={step.maneuver?.modifier}
          bearingBefore={step.maneuver?.bearing_before}
          bearingAfter={step.maneuver?.bearing_after}
          size={22}
          color="#FFFFFF"
        />
      </View>
      <View style={styles.body}>
        <Text style={[styles.instruction, { color: c.text }]}>{instruction}</Text>
        {step.distance != null ? (
          <Text style={[styles.meta, { color: c.textSub }]}>
            {formatStepDistance(step.distance)}
          </Text>
        ) : null}
      </View>
    </View>
  );
}

/**
 * Fallback step list — shown when a navigation session cannot start
 * (no maneuvers from Flask, or the native view failed to come up).
 */
export function NavigatePreviewSheet({
  visible,
  navigation,
  busy,
  error,
  onClose,
}: Props) {
  const top = useSafeAreaTop();
  const { c } = useChrome();
  const steps = navigation?.legs?.flatMap((leg) => leg.steps || []) || [];

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View
        style={[
          styles.root,
          { paddingTop: top + 8, paddingBottom: 24, backgroundColor: c.shellBg },
        ]}
      >
        <View style={styles.header}>
          <View>
            <Text style={[styles.title, { color: c.text }]}>Directions</Text>
            <Text style={[styles.subtitle, { color: c.textSub }]}>
              Turn-by-turn could not start — here is the route
            </Text>
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Close directions"
            onPress={onClose}
            hitSlop={12}
            style={({ pressed }) => [styles.close, pressed && styles.pressed]}
          >
            <X size={22} color={c.icon} />
          </Pressable>
        </View>

        {busy ? (
          <Text style={[styles.status, { color: c.textSub }]}>Building maneuvers…</Text>
        ) : error || navigation?.error ? (
          <Text style={[styles.status, { color: c.danger }]}>{error || navigation?.error}</Text>
        ) : (
          <ScrollView contentContainerStyle={styles.list}>
            {steps.map((step, i) => (
              <StepRow key={`${i}-${step.maneuver?.instruction}`} step={step} />
            ))}
          </ScrollView>
        )}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    paddingHorizontal: space.inset,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  title: {
    fontSize: 22,
    fontWeight: '800',
    letterSpacing: -0.5,
  },
  subtitle: {
    marginTop: 2,
    fontSize: 13,
  },
  close: {
    padding: 6,
  },
  pressed: { transform: [{ scale: 0.94 }] },
  status: {
    marginTop: 24,
    fontSize: 15,
  },
  list: {
    paddingBottom: 40,
    gap: 8,
  },
  row: {
    flexDirection: 'row',
    gap: 12,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: space.radiusSm,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
  },
  iconWrap: {
    width: 38,
    height: 38,
    borderRadius: 10,
    backgroundColor: brand.fuchsia,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: { flex: 1 },
  instruction: {
    fontSize: 15,
    fontWeight: '600',
  },
  meta: {
    marginTop: 2,
    fontSize: 12,
    fontVariant: ['tabular-nums'],
  },
});

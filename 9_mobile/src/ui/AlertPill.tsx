import { Dimensions, Pressable, StyleSheet, Text, View } from 'react-native';
import type { AlertEntry } from '../alerts/useAlertPill';
import { space } from '../theme/tokens';
import { useChrome } from '../theme/useChrome';

/** Nav stack width (52) + gap — keep centred pill clear of right controls. */
const CONTROLS_W = 52 + 8;

type Props = {
  alert: AlertEntry | null;
  onAction?: (actionId: string, alert: AlertEntry) => void;
};

/**
 * Top communication pill — web AlertPillZone.
 * Centred on full screen width; maxWidth so it never reaches the control stack.
 */
export function AlertPill({ alert, onAction }: Props) {
  const { c, themeMode } = useChrome();
  const shadowOpacity = themeMode === 'light' ? 0.08 : 0.35;
  const visible = Boolean(alert?.message);
  if (!visible || !alert) return null;

  const hasActions = Boolean(alert.actions?.length);
  const screenW = Dimensions.get('window').width;
  // Symmetric clearance: centred pill must fit between left inset and right controls.
  const maxW = Math.max(
    160,
    screenW - 2 * (space.inset + CONTROLS_W),
  );

  return (
    <View
      style={[
        styles.pill,
        hasActions && styles.pillActions,
        { maxWidth: maxW, backgroundColor: c.shellBg, borderColor: c.shellBorder, shadowOpacity },
      ]}
      accessibilityRole="text"
    >
      <Text
        style={[styles.text, { color: c.text }, !hasActions && styles.textCenter]}
        numberOfLines={1}
        ellipsizeMode="tail"
      >
        {alert.message}
      </Text>
      {hasActions && (
        <View style={styles.actions}>
          {alert.actions!.map((action) => (
            <Pressable
              key={action.id}
              onPress={() => onAction?.(action.id, alert)}
              style={({ pressed }) => [
                styles.btn,
                action.primary ? { backgroundColor: c.surface } : styles.btnGhost,
                pressed && { transform: [{ scale: 0.97 }] },
              ]}
            >
              <Text style={action.primary ? [styles.btnPrimaryText, { color: c.text }] : [styles.btnGhostText, { color: c.textSub }]}>
                {action.label}
              </Text>
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    alignSelf: 'center',
    minHeight: 40,
    paddingVertical: 10,
    paddingHorizontal: 18,
    borderRadius: 999,
    borderWidth: 1,
    shadowColor: '#000',
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  pillActions: {
    paddingVertical: 8,
    paddingLeft: 16,
    paddingRight: 10,
  },
  text: {
    flexShrink: 1,
    fontSize: 13,
    fontWeight: '600',
    lineHeight: 17,
  },
  textCenter: {
    textAlign: 'center',
  },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    flexShrink: 0,
  },
  btn: {
    borderRadius: 8,
    paddingVertical: 7,
    paddingHorizontal: 11,
  },
  btnPrimary: {},
  btnGhost: {
    backgroundColor: 'transparent',
  },
  btnPrimaryText: {
    fontSize: 12.5,
    fontWeight: '700',
  },
  btnGhostText: {
    fontSize: 12.5,
    fontWeight: '700',
  },
});

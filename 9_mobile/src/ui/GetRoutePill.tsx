import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { CornerUpRight } from 'lucide-react-native';
import { TutorialAnchor } from '../onboarding/tutorial/TutorialAnchor';
import { brand } from '../theme/tokens';

type Props = {
  disabled?: boolean;
  busy?: boolean;
  onPress: () => void;
};

/**
 * Mobile Get Route — web GetRouteButton icon pill.
 * Inactive (web .is-disabled): whole control at opacity 0.4 — fuchsia fill,
 * white diamond + white arrow dim together with the pill.
 * Busy: icon opacity pulse 1 ↔ 0.45 over 1.4s (web .is-pulse).
 */
export function GetRoutePill({ disabled, busy, onPress }: Props) {
  const blocked = disabled || busy;
  const inactive = Boolean(disabled && !busy);
  const [pulseOpacity, setPulseOpacity] = useState(1);
  const rafRef = useRef(0);
  const startRef = useRef(0);

  useEffect(() => {
    if (!busy) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
      setPulseOpacity(1);
      return undefined;
    }

    startRef.current = Date.now();
    const tick = () => {
      const t = ((Date.now() - startRef.current) % 1400) / 1400;
      const wave = 0.5 - 0.5 * Math.cos(t * Math.PI * 2);
      setPulseOpacity(1 - wave * 0.55);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    };
  }, [busy]);

  return (
    <TutorialAnchor
      id="tut-get-route"
      opts={{ radius: 12 }}
      style={styles.anchor}
    >
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={busy ? 'Getting route' : 'Get route'}
        accessibilityState={{ disabled: blocked, busy: !!busy }}
        onPress={onPress}
        disabled={blocked}
        style={({ pressed }) => [
          styles.pill,
          inactive && styles.pillInactive,
          pressed && !blocked && styles.pressed,
        ]}
      >
        <View style={[styles.icons, { opacity: pulseOpacity }]}>
          <View style={[styles.diamond, inactive && styles.diamondInactive]} />
          <CornerUpRight
            size={13}
            strokeWidth={2.5}
            color={inactive ? '#FFFFFF' : brand.fuchsia}
            style={styles.arrow}
          />
        </View>
      </Pressable>
    </TutorialAnchor>
  );
}

const styles = StyleSheet.create({
  anchor: {
    flex: 1,
    alignSelf: 'stretch',
    width: 40,
  },
  pill: {
    flex: 1,
    width: 40,
    alignSelf: 'stretch',
    borderRadius: 12,
    backgroundColor: brand.fuchsia,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 6,
    overflow: 'hidden',
  },
  /** Web .rc-route-pill.is-disabled { opacity: 0.4 } */
  pillInactive: {
    opacity: 0.4,
  },
  pressed: { transform: [{ scale: 0.97 }] },
  icons: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  diamond: {
    position: 'absolute',
    width: 17,
    height: 17,
    backgroundColor: '#FFFFFF',
    opacity: 0.92,
    transform: [{ rotate: '45deg' }],
    borderRadius: 2,
  },
  /** Blend into pill so the white arrow stays readable when dimmed. */
  diamondInactive: {
    backgroundColor: brand.fuchsia,
    opacity: 1,
  },
  arrow: {
    zIndex: 1,
  },
});

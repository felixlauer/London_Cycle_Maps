import { useEffect, useRef } from 'react';
import { Animated, Easing, Pressable, StyleSheet, View } from 'react-native';
import { LocateFixed, Route, Volume2, VolumeX, Waypoints } from 'lucide-react-native';
import { OVERLAY_MODE_META } from '../map/overlayModes';
import { brand } from '../theme/tokens';
import { useChrome } from '../theme/useChrome';

const EASE = Easing.bezier(0.23, 1, 0.32, 1);
const CYCLE_HUB = OVERLAY_MODE_META.cycle.hub;

type Props = {
  /** False once the rider pans away from the puck. */
  tracking: boolean;
  onRecenter: () => void;
  muted: boolean;
  onToggleMute: () => void;
  cyclewaysVisible: boolean;
  onToggleCycleways: () => void;
  /** Moved off the island so the right circle can be the report trigger. */
  overviewActive: boolean;
  onToggleOverview: () => void;
};

/**
 * Nav map controls. Recenter only exists while the camera is off the puck;
 * traffic stays painted at all times, so only cycleways get a switch.
 * Recenter reuses the plan-mode LocateFixed glyph and chrome dimensions.
 *
 * Overview lives here rather than on the island: it is a map control, and the
 * island's right circle is now the report trigger, which is used mid-ride.
 */
export function NavMapControls({
  tracking,
  onRecenter,
  muted,
  onToggleMute,
  cyclewaysVisible,
  onToggleCycleways,
  overviewActive,
  onToggleOverview,
}: Props) {
  const { c, themeMode } = useChrome();
  const shadowOpacity = themeMode === 'light' ? 0.08 : 0.4;
  const recenter = useRef(new Animated.Value(tracking ? 0 : 1)).current;

  useEffect(() => {
    Animated.timing(recenter, {
      toValue: tracking ? 0 : 1,
      duration: tracking ? 160 : 220,
      easing: EASE,
      useNativeDriver: true,
    }).start();
  }, [tracking, recenter]);

  const recenterScale = recenter.interpolate({
    inputRange: [0, 1],
    outputRange: [0.9, 1],
  });

  return (
    <View style={styles.stack}>
      <View
        style={[
          styles.nav,
          { backgroundColor: c.shellBg, borderColor: c.shellBorder, shadowOpacity },
        ]}
        accessibilityRole="toolbar"
        accessibilityLabel="Navigation controls"
      >
        <Pressable
          accessibilityLabel={muted ? 'Unmute voice guidance' : 'Mute voice guidance'}
          accessibilityState={{ selected: muted }}
          onPress={onToggleMute}
          style={({ pressed }) => [styles.navBtn, pressed && styles.pressed]}
        >
          {muted ? (
            <VolumeX size={18} strokeWidth={2.25} color={c.icon} />
          ) : (
            <Volume2 size={18} strokeWidth={2.25} color={c.icon} />
          )}
        </Pressable>

        <View style={[styles.rule, { backgroundColor: c.shellBorder }]} />

        <Pressable
          accessibilityLabel={cyclewaysVisible ? 'Hide cycleways' : 'Show cycleways'}
          accessibilityState={{ selected: cyclewaysVisible }}
          onPress={onToggleCycleways}
          style={({ pressed }) => [styles.navBtn, pressed && styles.pressed]}
        >
          <Route
            size={18}
            strokeWidth={2.25}
            color={cyclewaysVisible ? CYCLE_HUB : c.icon}
          />
        </Pressable>

        <View style={[styles.rule, { backgroundColor: c.shellBorder }]} />

        <Pressable
          accessibilityLabel={
            overviewActive ? 'Follow my position' : 'Show route overview'
          }
          accessibilityState={{ selected: overviewActive }}
          onPress={onToggleOverview}
          style={({ pressed }) => [
            styles.navBtn,
            overviewActive && { backgroundColor: brand.fuchsia },
            pressed && styles.pressed,
          ]}
        >
          <Waypoints
            size={18}
            strokeWidth={2.25}
            color={overviewActive ? '#FFFFFF' : c.icon}
          />
        </Pressable>
      </View>

      <Animated.View
        style={{ opacity: recenter, transform: [{ scale: recenterScale }] }}
        pointerEvents={tracking ? 'none' : 'auto'}
      >
        <View
          style={[
            styles.nav,
            { backgroundColor: c.shellBg, borderColor: c.shellBorder, shadowOpacity },
          ]}
        >
          <Pressable
            accessibilityLabel="Recenter on my position"
            onPress={onRecenter}
            style={({ pressed }) => [styles.navBtn, pressed && styles.pressed]}
          >
            <LocateFixed size={18} strokeWidth={2.25} color={c.icon} />
          </Pressable>
        </View>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  stack: {
    flexDirection: 'column-reverse',
    alignItems: 'flex-end',
    gap: 6,
  },
  // Match MapControls.nav / navBtn exactly — same LocateFixed chrome.
  nav: {
    width: 52,
    borderRadius: 16,
    borderWidth: 1,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 8,
  },
  navBtn: {
    width: '100%',
    // Matches MapControls: 44 pt minimum inside the clipping capsule.
    height: 44,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
  },
  rule: {
    height: StyleSheet.hairlineWidth,
    marginHorizontal: 8,
  },
  pressed: { transform: [{ scale: 0.94 }] },
});

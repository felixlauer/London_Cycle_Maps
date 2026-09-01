import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { LocateFixed, Navigation2 } from 'lucide-react-native';
import { brand } from '../theme/tokens';
import { useChrome } from '../theme/useChrome';
import { OverlayModeRail } from './OverlayModeRail';

type Props = {
  locateActive?: boolean;
  locatePending?: boolean;
  onLocateToggle: () => void;
  northNeedsReset?: boolean;
  onResetNorth: () => void;
  routeRevealed?: boolean;
  overlayMode: string | null;
  isDark?: boolean;
  onSelectOverlayMode: (id: string | null) => void;
  overlayPulse?: boolean;
  /** When expanded island crowds the stack, pack nav beside overlay (web is-ctl-packed). */
  islandExpanded?: boolean;
};

/**
 * Mobile map controls — web MapControlsZone compact.
 * Order matches CSS column-reverse: locate/north above overlay rail.
 * Icons have transparent backgrounds; north shows Navigation2 + fuchsia "N".
 */
export function MapControls({
  locateActive,
  locatePending,
  onLocateToggle,
  northNeedsReset,
  onResetNorth,
  routeRevealed = false,
  overlayMode,
  isDark = false,
  onSelectOverlayMode,
  overlayPulse = false,
  islandExpanded = false,
}: Props) {
  const { c, themeMode } = useChrome();
  const navShadowOpacity = themeMode === 'light' ? 0.08 : 0.4;
  // Only pack when vertical room is truly gone — most phones keep the stack.
  // Web measures; here we keep stacked unless a future measure pass says otherwise.
  void islandExpanded;
  const packBeside = false;

  return (
    <View style={[styles.stack, packBeside && styles.stackPacked]}>
      <OverlayModeRail
        activeMode={overlayMode}
        isDark={isDark}
        inactive={!routeRevealed}
        onSelectMode={onSelectOverlayMode}
        compact
        pulse={overlayPulse}
      />

      <View style={[styles.nav, { backgroundColor: c.shellBg, borderColor: c.shellBorder, shadowOpacity: navShadowOpacity }]} accessibilityRole="toolbar" accessibilityLabel="Location and orientation">
        <Pressable
          accessibilityLabel={locateActive ? 'Stop using my location' : 'Use my location'}
          accessibilityState={{ selected: !!locateActive, busy: !!locatePending }}
          disabled={locatePending}
          onPress={onLocateToggle}
          style={({ pressed }) => [
            styles.navBtn,
            pressed && !locatePending && { transform: [{ scale: 0.94 }] },
          ]}
        >
          {locatePending ? (
            <ActivityIndicator size="small" color={c.icon} />
          ) : (
            <LocateFixed
              size={18}
              strokeWidth={2.25}
              color={locateActive ? brand.fuchsia : c.icon}
            />
          )}
        </Pressable>

        <View style={[styles.rule, { backgroundColor: c.shellBorder }]} />

        <Pressable
          accessibilityLabel="Reset map to north and flat view"
          accessibilityState={{ disabled: !northNeedsReset }}
          onPress={northNeedsReset ? onResetNorth : undefined}
          style={({ pressed }) => [
            styles.navBtn,
            pressed && northNeedsReset && { transform: [{ scale: 0.94 }] },
          ]}
        >
          <View style={styles.north}>
            <Navigation2
              size={16}
              strokeWidth={2.25}
              color={c.icon}
              style={styles.northIcon}
            />
            <Text
              style={[
                styles.northN,
                // Web: brand N when flat/north; muted when reset is needed (is-active)
                northNeedsReset ? { color: c.icon } : null,
              ]}
            >
              N
            </Text>
          </View>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  stack: {
    flexDirection: 'column-reverse',
    alignItems: 'flex-end',
    gap: 6,
  },
  stackPacked: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
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
    height: 42,
    minHeight: 42,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
  },
  rule: {
    height: StyleSheet.hairlineWidth,
    marginHorizontal: 8,
  },
  north: {
    alignItems: 'center',
    justifyContent: 'center',
    transform: [{ translateY: 2 }],
  },
  northIcon: {
    marginTop: -4,
  },
  northN: {
    marginTop: -1,
    fontSize: 8,
    fontWeight: '700',
    letterSpacing: 0.4,
    lineHeight: 10,
    color: brand.fuchsia,
  },
});

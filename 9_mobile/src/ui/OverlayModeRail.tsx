import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  Globe,
  Lightbulb,
  Mountain,
  Route,
  Trees,
} from 'lucide-react-native';
import Svg, { Path } from 'react-native-svg';
import { availableOverlayModes } from '../map/overlayModes';
import { TutorialAnchor } from '../onboarding/tutorial/TutorialAnchor';
import { useChrome } from '../theme/useChrome';
import {
  armCenterY,
  armExtentForLabel,
  buildOverlayPillPath,
  edgeModeForIndex,
  overlayPillMetrics,
  type EdgeMode,
} from './overlayPillPath';

const ICONS: Record<string, typeof Route> = {
  Route,
  FerrisWheel: Trees,
  Globe,
  Mountain,
  Lightbulb,
};

const PEEK_MS = 2400;
/** Match web motion springs approximately via RN Animated.spring. */
const EXPAND_SPRING = { stiffness: 300, damping: 24, mass: 1, useNativeDriver: false as const };
const COLLAPSE_SPRING = { stiffness: 240, damping: 26, mass: 1, useNativeDriver: false as const };

type Props = {
  activeMode: string | null;
  isDark?: boolean;
  inactive?: boolean;
  onSelectMode: (id: string | null) => void;
  compact?: boolean;
  pulse?: boolean;
};

/**
 * Overlay mode rail — SVG path morph (web OverlayModeRail).
 * Expand/collapse spring on armExtent; icons over transparent buttons; hub colour when active.
 */
export function OverlayModeRail({
  activeMode,
  isDark = false,
  inactive = true,
  onSelectMode,
  compact = true,
  pulse = false,
}: Props) {
  const { c } = useChrome();
  const modes = availableOverlayModes(isDark);
  const m = useMemo(() => overlayPillMetrics(modes.length, { compact }), [modes.length, compact]);

  const [peek, setPeek] = useState(false);
  const [pathD, setPathD] = useState('');
  const [labelOpacity, setLabelOpacity] = useState(0);

  const selectedIndex = modes.findIndex((x) => x.id === activeMode);
  const hasSelection = !inactive && selectedIndex >= 0;
  const morphIndex = hasSelection
    ? selectedIndex
    : Math.max(0, Math.floor((modes.length - 1) / 2));

  const edgeMode: EdgeMode = hasSelection
    ? edgeModeForIndex(selectedIndex, modes.length)
    : 'middle';
  const edgeModeRef = useRef(edgeMode);
  edgeModeRef.current = edgeMode;

  const armExtentMv = useRef(new Animated.Value(0)).current;
  const armCyMv = useRef(new Animated.Value(armCenterY(morphIndex, m))).current;
  const extentRef = useRef(0);
  const cyRef = useRef(armCenterY(morphIndex, m));

  const rebuildPath = () => {
    setPathD(
      buildOverlayPillPath({
        spineW: m.spineW,
        spineH: m.spineH,
        armExtent: extentRef.current,
        armCy: cyRef.current,
        armH: m.armH,
        filletR: m.filletR,
        endR: m.cornerR,
        edgeMode: edgeModeRef.current,
      }),
    );
    const labelExtent = hasSelection
      ? armExtentForLabel(modes[selectedIndex]?.label || '', edgeModeRef.current)
      : 80;
    const fadeStart = Math.max(28, labelExtent * 0.9);
    const fadeEnd = Math.max(fadeStart + 1, labelExtent);
    const ext = extentRef.current;
    if (ext <= fadeStart) setLabelOpacity(0);
    else if (ext >= fadeEnd) setLabelOpacity(1);
    else setLabelOpacity((ext - fadeStart) / (fadeEnd - fadeStart));
  };

  useEffect(() => {
    const id1 = armExtentMv.addListener(({ value }) => {
      extentRef.current = value;
      rebuildPath();
    });
    const id2 = armCyMv.addListener(({ value }) => {
      cyRef.current = value;
      rebuildPath();
    });
    rebuildPath();
    return () => {
      armExtentMv.removeListener(id1);
      armCyMv.removeListener(id2);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [m.spineW, m.spineH, m.armH, m.filletR, m.cornerR, hasSelection, selectedIndex]);

  useEffect(() => {
    if (inactive) setPeek(false);
  }, [inactive]);

  useEffect(() => {
    if (!hasSelection) {
      setPeek(false);
      armExtentMv.setValue(0);
      extentRef.current = 0;
      rebuildPath();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasSelection]);

  useEffect(() => {
    if (!peek || inactive || !hasSelection) return undefined;
    const t = setTimeout(() => setPeek(false), PEEK_MS);
    return () => clearTimeout(t);
  }, [peek, activeMode, inactive, hasSelection]);

  const targetExtent = (peek && hasSelection)
    ? armExtentForLabel(modes[selectedIndex].label, edgeMode)
    : 0;
  const targetCy = armCenterY(morphIndex, m);
  const spring = targetExtent > 0 ? EXPAND_SPRING : COLLAPSE_SPRING;

  useEffect(() => {
    if (!hasSelection && targetExtent === 0) {
      Animated.timing(armCyMv, {
        toValue: targetCy,
        duration: 1,
        easing: Easing.linear,
        useNativeDriver: false,
      }).start();
      return undefined;
    }
    const a1 = Animated.spring(armExtentMv, { ...spring, toValue: targetExtent });
    const a2 = Animated.spring(armCyMv, { ...spring, toValue: targetCy });
    a1.start();
    a2.start();
    return () => {
      a1.stop();
      a2.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetExtent, targetCy, hasSelection]);

  const svgW = m.maxArmExtent + m.spineW;
  const activeLabel = hasSelection ? modes[selectedIndex].label : '';
  const labelExtent = hasSelection
    ? armExtentForLabel(modes[selectedIndex].label, edgeMode)
    : 80;

  const handleClick = (id: string) => {
    if (inactive) {
      onSelectMode(id);
      return;
    }
    if (id === activeMode) {
      setPeek(false);
      onSelectMode(null);
      return;
    }
    onSelectMode(id);
    setPeek(true);
  };

  return (
    <TutorialAnchor id="tut-overlay-rail" opts={{ capsule: true }}>
      <View
        style={[
          styles.pill,
          { width: m.spineW, height: m.spineH },
          compact && styles.pillCompact,
          pulse && styles.pulse,
        ]}
        accessibilityRole="toolbar"
        accessibilityLabel="Route overlay modes"
      >
        <Svg
          width={svgW}
          height={m.spineH}
          style={[styles.svg, { left: -m.maxArmExtent }]}
          viewBox={`${-m.maxArmExtent} 0 ${svgW} ${m.spineH}`}
        >
          <Path
            d={pathD || buildOverlayPillPath({
              spineW: m.spineW,
              spineH: m.spineH,
              armExtent: 0.02,
              armCy: armCenterY(morphIndex, m),
              armH: m.armH,
              filletR: m.filletR,
              endR: m.cornerR,
              edgeMode: 'middle',
            })}
            fill={c.shellBg}
            stroke={c.shellBorder}
            strokeWidth={1}
          />
        </Svg>

        {hasSelection && (
          <View
            pointerEvents="none"
            style={[
              styles.label,
              {
                opacity: labelOpacity,
                top: armCenterY(selectedIndex, m) - m.armH / 2,
                height: m.armH,
                width: labelExtent,
                left: -labelExtent,
              },
            ]}
          >
            <Text style={[styles.labelText, { color: c.text }]}>{activeLabel}</Text>
          </View>
        )}

        <View style={[styles.icons, { padding: m.pad, gap: m.gap }]}>
          {modes.map((mode) => {
            const Icon = ICONS[mode.Icon] || Route;
            const selected = hasSelection && mode.id === activeMode;
            const btn = (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={mode.label}
                accessibilityState={{ selected }}
                onPress={() => handleClick(mode.id)}
                style={({ pressed }) => [
                  styles.btn,
                  { height: m.btnH },
                  pressed && { transform: [{ scale: 0.94 }] },
                ]}
              >
                <Icon
                  size={m.iconSize}
                  strokeWidth={2.25}
                  color={selected ? mode.hub : c.icon}
                />
              </Pressable>
            );
            if (mode.id === 'green') {
              return (
                <TutorialAnchor key={mode.id} id="tut-overlay-attractions" opts={{ capsule: true }}>
                  {btn}
                </TutorialAnchor>
              );
            }
            return <View key={mode.id}>{btn}</View>;
          })}
        </View>
      </View>
    </TutorialAnchor>
  );
}

const styles = StyleSheet.create({
  pill: {
    position: 'relative',
    flexShrink: 0,
    backgroundColor: 'transparent',
    overflow: 'visible',
  },
  pillCompact: {
    // Web compact: no rectangular chrome — SVG path is the only fill.
    // Android elevation/border here showed as a grey box artefact.
    borderRadius: 0,
    borderWidth: 0,
    elevation: 0,
    shadowOpacity: 0,
  },
  pulse: {
    // Web pulses the pill ring; compact has no ring — no-op (hint still fires).
  },
  svg: {
    position: 'absolute',
    top: 0,
    zIndex: 0,
  },
  label: {
    position: 'absolute',
    zIndex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingLeft: 14,
    paddingRight: 10,
  },
  labelText: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.1,
  },
  icons: {
    position: 'relative',
    zIndex: 2,
    flex: 1,
    width: '100%',
    height: '100%',
  },
  btn: {
    width: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
    borderRadius: 12,
  },
});

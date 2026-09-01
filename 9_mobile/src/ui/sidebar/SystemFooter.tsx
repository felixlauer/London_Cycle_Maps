/**
 * System footer — Units first, then Appearance (web SystemFooter).
 */
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Monitor, Moon, Sun, Sunset } from 'lucide-react-native';
import {
  APPEARANCE_OPTIONS,
  type AppearancePref,
} from '../../theme/resolveAppearance';
import { useChrome } from '../../theme/useChrome';
import { useSidebar } from './SidebarContext';

const APPEARANCE_ICONS = {
  light: Sun,
  dark: Moon,
  system: Monitor,
  auto: Sunset,
} as const;

export function SystemFooter() {
  const { appearance, setAppearance, units, setUnits } = useSidebar();
  const { c } = useChrome();

  return (
    <View style={styles.root}>
      <Text style={[styles.title, { color: c.text }]}>System</Text>

      <View style={styles.block}>
        <Text style={[styles.label, { color: c.textSub }]}>Units</Text>
        <View style={[styles.seg, styles.segUnits, { backgroundColor: c.inset, borderColor: c.line }]}>
          {(['metric', 'imperial'] as const).map((id) => {
            const selected = units === id;
            return (
              <Pressable
                key={id}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
                onPress={() => setUnits(id)}
                style={({ pressed }) => [
                  styles.segBtn,
                  styles.segBtnUnits,
                  selected && { backgroundColor: c.selectedSeg },
                  pressed && { opacity: 0.9, transform: [{ scale: 0.97 }] },
                ]}
              >
                <Text style={[
                  styles.segBtnUnitsText,
                  { color: selected ? c.text : c.textSub },
                ]}>
                  {id === 'metric' ? 'Metric' : 'Imperial'}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      <View style={styles.block}>
        <Text style={[styles.label, { color: c.textSub }]}>Appearance</Text>
        <View style={[styles.seg, { backgroundColor: c.inset, borderColor: c.line }]}>
          {APPEARANCE_OPTIONS.map((opt) => {
            const Icon = APPEARANCE_ICONS[opt.id as AppearancePref] || Sun;
            const selected = appearance === opt.id;
            return (
              <Pressable
                key={opt.id}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
                accessibilityLabel={opt.label}
                onPress={() => setAppearance(opt.id)}
                style={({ pressed }) => [
                  styles.segBtn,
                  selected && { backgroundColor: c.selectedSeg },
                  pressed && { opacity: 0.9, transform: [{ scale: 0.97 }] },
                ]}
              >
                <Icon
                  size={14}
                  strokeWidth={2.25}
                  color={selected ? c.text : c.textSub}
                />
                <Text style={[
                  styles.segBtnText,
                  { color: selected ? c.text : c.textSub },
                ]}>
                  {opt.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    gap: 12,
    paddingTop: 2,
  },
  title: {
    fontSize: 14,
    fontWeight: '700',
    letterSpacing: -0.15,
  },
  block: {
    gap: 6,
  },
  label: {
    fontSize: 12,
    fontWeight: '600',
  },
  seg: {
    flexDirection: 'row',
    gap: 4,
    padding: 3,
    borderRadius: 11,
    borderWidth: 1,
  },
  segUnits: {},
  segBtn: {
    flex: 1,
    minHeight: 40,
    paddingVertical: 6,
    paddingHorizontal: 4,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
  },
  segBtnUnits: {
    flexDirection: 'row',
    minHeight: 34,
  },
  segBtnText: {
    fontSize: 10.5,
    fontWeight: '600',
    lineHeight: 12,
  },
  segBtnUnitsText: {
    fontSize: 12.5,
    fontWeight: '600',
  },
});

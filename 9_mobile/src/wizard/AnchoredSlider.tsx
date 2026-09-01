import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { ChromeTokens } from '../theme/tokens';
import { sliderMinutes, type SliderCfg } from './budget';
import { HelpTip } from './HelpTip';
import { RangeSlider } from './RangeSlider';

type Props = {
  sliderKey: string;
  cfg: SliderCfg;
  value: number;
  onChange: (key: string, value: number) => void;
  bikeType: string;
  warning?: string;
  mode?: 'detour' | 'savings';
  saveMinutes?: number | null;
  questionOverride?: string | null;
  note?: string | null;
  c: ChromeTokens;
};

/** Weight slider — web AnchoredSlider without the snap buttons under the track. */
export function AnchoredSlider({
  sliderKey,
  cfg,
  value,
  onChange,
  bikeType,
  warning,
  mode = 'detour',
  saveMinutes = null,
  questionOverride = null,
  note = null,
  c,
}: Props) {
  const savings = mode === 'savings';
  const cap = cfg.cap ?? 1;
  const detourMinutes = sliderMinutes(cfg, value, bikeType);
  const minutes = savings && saveMinutes != null ? saveMinutes : detourMinutes;
  const displayVal = value <= 0.0001 ? 0 : value;
  const question = questionOverride || cfg.question;

  const costLabel = () => {
    if (savings) {
      if (minutes > 0.05) return `~${minutes.toFixed(1)} min saved est.`;
      return 'no time save';
    }
    if (minutes > 0.05) return `+${minutes.toFixed(1)} min est.`;
    return 'no detour';
  };

  return (
    <View style={styles.root}>
      <View style={styles.head}>
        <View style={styles.labelRow}>
          <Text style={[styles.label, { color: c.text }]}>{cfg.label}</Text>
          <HelpTip text={cfg.help} c={c} />
        </View>
        <Text style={[styles.cost, { color: c.textSub }]}>{costLabel()}</Text>
      </View>
      {question ? (
        <Text style={[styles.question, { color: c.textSub }]}>{question}</Text>
      ) : null}

      <RangeSlider
        value={displayVal}
        min={0}
        max={cap}
        step={0.1}
        onChange={(v) => onChange(sliderKey, v)}
        c={c}
        accessibilityLabel={cfg.label}
      />

      {note ? (
        <Text style={[styles.warn, { color: c.textSub, opacity: 0.85 }]}>{note}</Text>
      ) : null}
      {warning ? (
        <Text style={[styles.warn, { color: '#F18805' }]}>{warning}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { marginBottom: 16, gap: 4 },
  head: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  labelRow: { flexDirection: 'row', alignItems: 'center', flexShrink: 1 },
  label: { fontSize: 13.5, fontWeight: '700' },
  cost: { fontSize: 11.5, fontWeight: '600' },
  question: { fontSize: 12.5, lineHeight: 17, fontWeight: '500' },
  warn: { fontSize: 11.5, lineHeight: 15, fontWeight: '500', marginTop: 2 },
});

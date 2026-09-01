import { StyleSheet, Text, View } from 'react-native';
import { brand, type ChromeTokens } from '../theme/tokens';

type Props = {
  used: number;
  budget: number;
  mode?: 'detour' | 'savings';
  distanceNoteMin?: number | null;
  c: ChromeTokens;
};

/** Budget / savings bar — web wizard/BudgetBar.js */
export function BudgetBar({
  used,
  budget,
  mode = 'detour',
  distanceNoteMin = null,
  c,
}: Props) {
  const savings = mode === 'savings';
  const over = used > budget + 0.01;
  const pct = budget > 0 ? Math.min(100, (used / budget) * 100) : (used > 0 ? 100 : 0);
  const usedLabel = used.toFixed(1).replace(/\.0$/, '');
  const warn = over ? '#F18805' : brand.fuchsia;

  return (
    <View style={styles.root}>
      <View style={styles.labels}>
        <Text style={[styles.label, { color: c.textSub }]}>
          {savings ? 'Estimated time saved' : 'Estimated detour'}
        </Text>
        <Text style={[styles.used, { color: over ? warn : c.text }]}>
          {usedLabel} / {budget} min
        </Text>
      </View>
      <View style={[styles.track, { backgroundColor: c.line }]}>
        <View
          style={[
            styles.fill,
            { width: `${pct}%`, backgroundColor: warn },
          ]}
        />
      </View>
      {savings && distanceNoteMin != null && distanceNoteMin > 0.05 ? (
        <Text style={[styles.note, { color: c.textSub }]}>
          {`May add ~${distanceNoteMin.toFixed(1).replace(/\.0$/, '')} min of distance on a typical ride.`}
        </Text>
      ) : null}
      <Text style={[styles.note, { color: c.textSub }]}>
        {savings
          ? 'Estimate from metric improvements × fixed seconds on our 12.6 km reference ride — preferences interact, so real time can differ.'
          : 'Estimate from independent sweeps - combined preferences interact, so the real detour can differ.'}
        {over
          ? (savings
            ? ' You are over your time-saving goal; this is a very aggressive Fast setup.'
            : ' You are over your budget; consider easing a slider.')
          : ''}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { gap: 6 },
  labels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  label: { fontSize: 12, fontWeight: '600' },
  used: { fontSize: 12, fontWeight: '700' },
  track: {
    height: 8,
    borderRadius: 999,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: 999,
  },
  note: { fontSize: 11, lineHeight: 15, fontWeight: '500' },
});

import { StyleSheet, Text, View } from 'react-native';
import { useChrome } from '../../theme/useChrome';

type Props = {
  value: string;
  unit: string;
  label?: string;
  /** Large collapsed metrics omit caption; expanded may too. */
  size?: 'collapsed' | 'expanded';
};

/** Bold number + baseline unit — web MetricCell (mobile: no delta). */
export function MetricCell({ value, unit, label, size = 'collapsed' }: Props) {
  const { c } = useChrome();
  const large = size === 'expanded';
  return (
    <View style={styles.metric} accessibilityLabel={label}>
      <View style={styles.row}>
        <Text style={[styles.value, { color: c.text }, large && styles.valueLg]}>{value}</Text>
        <Text style={[styles.unit, { color: c.textSub }, large && styles.unitLg]}>{unit}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  metric: {
    flexDirection: 'column',
    gap: 2,
    minWidth: 0,
    alignItems: 'flex-start',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 5,
  },
  value: {
    fontSize: 34,
    fontWeight: '800',
    letterSpacing: -1.2,
    lineHeight: 36,
    fontVariant: ['tabular-nums'],
  },
  valueLg: {
    fontSize: 42,
    lineHeight: 44,
  },
  unit: {
    fontSize: 14,
    fontWeight: '600',
  },
  unitLg: {
    fontSize: 16,
  },
});

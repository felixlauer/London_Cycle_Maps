import { Pressable, StyleSheet, Text, View } from 'react-native';
import { brand, type ChromeTokens } from '../theme/tokens';
import type { PresetConfig } from './types';

const BIKE_ICONS: Record<string, string> = {
  standard: '🚲',
  road: '🚴',
  ebike: '⚡',
  cargo: '📦',
};

type Props = {
  config: PresetConfig;
  bikeType: string | null;
  onSelect: (id: string) => void;
  c: ChromeTokens;
};

export function BikeTypeStep({ config, bikeType, onSelect, c }: Props) {
  const types = config.bike_types || {};
  const entries = Object.entries(types);

  return (
    <>
      <Text style={[styles.intro, { color: c.textSub }]}>
        What are you riding? The bike changes what matters: hills, surfaces and
        barriers behave differently for each type.
      </Text>
      <View style={styles.grid}>
        {entries.map(([id, bt]) => {
          const selected = bikeType === id;
          return (
            <Pressable
              key={id}
              onPress={() => onSelect(id)}
              style={[
                styles.card,
                { borderColor: c.line, backgroundColor: c.surface },
                selected && {
                  borderColor: brand.fuchsia,
                  backgroundColor: `${brand.fuchsia}14`,
                },
              ]}
            >
              <Text style={styles.icon}>{BIKE_ICONS[id] || '🚲'}</Text>
              <Text style={[styles.title, { color: c.text }]}>{bt.label}</Text>
              <Text style={[styles.note, { color: c.textSub }]}>{bt.note}</Text>
              {bt.speed_kmh != null ? (
                <Text style={[styles.badge, { color: brand.fuchsia }]}>
                  {bt.speed_kmh} km/h avg
                </Text>
              ) : null}
            </Pressable>
          );
        })}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  intro: { fontSize: 13.5, lineHeight: 19, marginBottom: 12, fontWeight: '500' },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  card: {
    width: '48%',
    flexGrow: 1,
    flexBasis: '46%',
    borderRadius: 12,
    borderWidth: 1.5,
    padding: 14,
    gap: 4,
  },
  icon: { fontSize: 22, marginBottom: 2 },
  title: { fontSize: 15, fontWeight: '700' },
  note: { fontSize: 12.5, lineHeight: 17, fontWeight: '500' },
  badge: { fontSize: 12, fontWeight: '600', marginTop: 4 },
});

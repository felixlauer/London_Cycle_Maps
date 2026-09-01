import { Pressable, StyleSheet, Text, View } from 'react-native';
import { brand, type ChromeTokens } from '../theme/tokens';
import type { PresetConfig } from './types';

const PRESET_ICONS: Record<string, string> = {
  fast: '🏁',
  safe: '🛡️',
  leisure: '🌳',
};

type Props = {
  config: PresetConfig;
  preset: string | null;
  onSelect: (id: string) => void;
  c: ChromeTokens;
};

export function PresetStep({ config, preset, onSelect, c }: Props) {
  const presets = config.presets || {};

  return (
    <>
      <Text style={[styles.intro, { color: c.textSub }]}>
        Pick a starting style. Every value can be fine-tuned in the next step -
        the preset just sets sensible defaults.
      </Text>
      <View style={styles.list}>
        {Object.entries(presets).map(([id, p]) => {
          const selected = preset === id;
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
              <Text style={[styles.title, { color: c.text }]}>
                <Text>{PRESET_ICONS[id] || '•'} </Text>
                {p.label}
              </Text>
              <Text style={[styles.note, { color: c.textSub }]}>{p.description}</Text>
            </Pressable>
          );
        })}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  intro: { fontSize: 13.5, lineHeight: 19, marginBottom: 12, fontWeight: '500' },
  list: { gap: 10 },
  card: {
    borderRadius: 12,
    borderWidth: 1.5,
    padding: 14,
    gap: 4,
  },
  title: { fontSize: 15, fontWeight: '700' },
  note: { fontSize: 13, lineHeight: 18, fontWeight: '500' },
});

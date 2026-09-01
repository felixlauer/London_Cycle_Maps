import { Pressable, StyleSheet, View } from 'react-native';
import { brand, type ChromeTokens } from '../theme/tokens';

type Props = {
  value: boolean;
  onChange: (v: boolean) => void;
  c: ChromeTokens;
  accessibilityLabel?: string;
};

/**
 * Custom switch — web .wiz-switch (40×22, knob 16×16 inset 3px).
 * Avoids Android Switch thumb vertical misalignment.
 */
export function WizSwitch({ value, onChange, c, accessibilityLabel }: Props) {
  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityState={{ checked: value }}
      accessibilityLabel={accessibilityLabel}
      onPress={() => onChange(!value)}
      hitSlop={8}
      style={styles.wrap}
    >
      <View
        style={[
          styles.track,
          {
            backgroundColor: value ? brand.fuchsia : c.inset,
            borderColor: value ? brand.fuchsia : c.line,
          },
        ]}
      />
      <View
        style={[
          styles.knob,
          value ? styles.knobOn : styles.knobOff,
        ]}
      />
    </Pressable>
  );
}

const TRACK_W = 40;
const TRACK_H = 22;
const KNOB = 16;
const INSET = 3;

const styles = StyleSheet.create({
  wrap: {
    width: TRACK_W,
    height: TRACK_H,
    flexShrink: 0,
    justifyContent: 'center',
  },
  track: {
    ...StyleSheet.absoluteFill,
    borderRadius: 999,
    borderWidth: 1,
  },
  knob: {
    position: 'absolute',
    top: INSET,
    width: KNOB,
    height: KNOB,
    borderRadius: 999,
    backgroundColor: '#fff',
    shadowColor: '#000',
    shadowOpacity: 0.25,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
    elevation: 2,
  },
  knobOff: { left: INSET },
  knobOn: { left: TRACK_W - KNOB - INSET },
});

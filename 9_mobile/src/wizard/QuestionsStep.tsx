import { useRef, useState } from 'react';
import {
  Animated,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { brand, type ChromeTokens } from '../theme/tokens';
import { HelpTip } from './HelpTip';
import { MAX_PROFILE_NAME_LEN } from './profileName';
import type { PresetConfig, WizardToggles } from './types';
import { WizSwitch } from './WizSwitch';

type Props = {
  config: PresetConfig;
  bikeType: string;
  toggles: WizardToggles;
  onToggleChange: (key: string, value: unknown) => void;
  name: string;
  onNameChange: (name: string) => void;
  c: ChromeTokens;
};

export function QuestionsStep({
  config,
  bikeType,
  toggles,
  onToggleChange,
  name,
  onNameChange,
  c,
}: Props) {
  const cfg = config.toggles || {};
  const hideSurface = (cfg.surface?.hidden_for || []).includes(bikeType);
  const vfOptions = cfg.vf_infrastructure?.options || {};
  const shakeX = useRef(new Animated.Value(0)).current;
  const [hintPulse, setHintPulse] = useState(false);

  const softFailName = () => {
    setHintPulse(true);
    Animated.sequence([
      Animated.timing(shakeX, { toValue: 6, duration: 40, useNativeDriver: true }),
      Animated.timing(shakeX, { toValue: -6, duration: 40, useNativeDriver: true }),
      Animated.timing(shakeX, { toValue: 4, duration: 40, useNativeDriver: true }),
      Animated.timing(shakeX, { toValue: 0, duration: 40, useNativeDriver: true }),
    ]).start();
    setTimeout(() => setHintPulse(false), 900);
  };

  const handleNameChange = (next: string) => {
    if (next.length > MAX_PROFILE_NAME_LEN) {
      softFailName();
      onNameChange(next.slice(0, MAX_PROFILE_NAME_LEN));
      return;
    }
    onNameChange(next);
  };

  return (
    <>
      <Text style={[styles.intro, { color: c.textSub }]}>
        A few final questions, then name your profile.
      </Text>

      <View style={[styles.panel, { borderColor: c.line, backgroundColor: c.surface }]}>
        <ToggleRow
          label={cfg.light_night?.question || 'Prefer lit routes at night'}
          help={cfg.light_night?.help}
          sub="Only applies when it is dark outside."
          value={toggles.light_night}
          onChange={(v) => onToggleChange('light_night', v)}
          c={c}
        />
        {hideSurface ? (
          <View style={[styles.qRow, { borderTopColor: c.line }]}>
            <View style={{ flex: 1 }}>
              <Text style={[styles.qText, { color: c.text }]}>Smooth surfaces</Text>
              <Text style={[styles.qSub, { color: c.textSub }]}>
                Enabled automatically for road bikes.
              </Text>
            </View>
          </View>
        ) : (
          <ToggleRow
            label={cfg.surface?.question || 'Prefer smooth surfaces'}
            help={cfg.surface?.help}
            value={toggles.surface}
            onChange={(v) => onToggleChange('surface', v)}
            c={c}
          />
        )}
        <ToggleRow
          label={cfg.jam_comfort?.question || 'Stay comfortable in traffic'}
          help={cfg.jam_comfort?.help}
          sub="Road closures are always avoided either way."
          value={toggles.jam_comfort}
          onChange={(v) => onToggleChange('jam_comfort', v)}
          c={c}
        />
      </View>

      <View style={[styles.panel, { borderColor: c.line, backgroundColor: c.surface }]}>
        <View style={styles.panelTitleRow}>
          <Text style={[styles.panelTitleInline, { color: c.text }]}>
            {cfg.vf_infrastructure?.question || 'Cycling infrastructure'}
          </Text>
          <HelpTip text={cfg.vf_infrastructure?.help} c={c} />
        </View>

        <View style={[styles.checkRow, styles.checkLocked]}>
          <View style={[styles.checkbox, styles.checkboxOn, { borderColor: c.line }]}>
            <Text style={styles.checkMark}>✓</Text>
          </View>
          <Text style={[styles.checkLabel, { color: c.textSub }]}>
            Segregated cycle tracks (always on)
          </Text>
        </View>

        {Object.entries(vfOptions).map(([optKey, opt]) => {
          const checked = Boolean(toggles.vf_infrastructure?.[optKey as keyof typeof toggles.vf_infrastructure]);
          return (
            <Pressable
              key={optKey}
              onPress={() => onToggleChange('vf_infrastructure', {
                ...toggles.vf_infrastructure,
                [optKey]: !checked,
              })}
              style={styles.checkRow}
            >
              <View style={[
                styles.checkbox,
                { borderColor: c.line, backgroundColor: c.inset },
                checked && { backgroundColor: brand.fuchsia, borderColor: brand.fuchsia },
              ]}
              >
                {checked ? <Text style={styles.checkMark}>✓</Text> : null}
              </View>
              <Text style={[styles.checkLabel, { color: c.text }]}>{opt.label}</Text>
            </Pressable>
          );
        })}
      </View>

      <View style={[styles.panel, { borderColor: c.line, backgroundColor: c.surface }]}>
        <Text style={[styles.panelTitle, { color: c.text }]}>Profile name</Text>
        <Animated.View style={{ transform: [{ translateX: shakeX }] }}>
          <TextInput
            style={[
              styles.nameInput,
              { color: c.text, borderColor: c.line, backgroundColor: c.inset },
            ]}
            value={name}
            onChangeText={handleNameChange}
            maxLength={MAX_PROFILE_NAME_LEN + 1}
            placeholder="e.g. Commute"
            placeholderTextColor={c.textSub}
            autoCapitalize="words"
          />
        </Animated.View>
        <Text
          style={[
            styles.nameHint,
            { color: hintPulse ? brand.fuchsia : c.textSub },
            hintPulse && { fontWeight: '700' },
          ]}
        >
          {`Max ${MAX_PROFILE_NAME_LEN} characters`}
        </Text>
      </View>
    </>
  );
}

function ToggleRow({
  label,
  help,
  sub,
  value,
  onChange,
  c,
}: {
  label: string;
  help?: string;
  sub?: string;
  value: boolean;
  onChange: (v: boolean) => void;
  c: ChromeTokens;
}) {
  return (
    <View style={[styles.qRow, { borderTopColor: c.line }]}>
      <View style={{ flex: 1, paddingRight: 12 }}>
        <View style={styles.qTextRow}>
          <Text style={[styles.qText, { color: c.text }]}>{label}</Text>
          <HelpTip text={help} c={c} />
        </View>
        {sub ? <Text style={[styles.qSub, { color: c.textSub }]}>{sub}</Text> : null}
      </View>
      <WizSwitch
        value={value}
        onChange={onChange}
        c={c}
        accessibilityLabel={label}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  intro: { fontSize: 13.5, lineHeight: 19, marginBottom: 12, fontWeight: '500' },
  panel: {
    borderRadius: 12,
    borderWidth: 1,
    overflow: 'hidden',
    marginBottom: 12,
    paddingBottom: 4,
  },
  panelTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingTop: 12,
    paddingBottom: 6,
    gap: 4,
  },
  panelTitle: {
    fontSize: 13,
    fontWeight: '700',
    paddingHorizontal: 14,
    paddingTop: 12,
    paddingBottom: 6,
  },
  panelTitleInline: {
    fontSize: 13,
    fontWeight: '700',
  },
  qRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    minHeight: 52,
  },
  qTextRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap' },
  qText: { fontSize: 13.5, fontWeight: '600' },
  qSub: { fontSize: 12, marginTop: 2, lineHeight: 16, fontWeight: '500' },
  checkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  checkLocked: { opacity: 0.75 },
  checkbox: {
    width: 20,
    height: 20,
    borderRadius: 5,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxOn: {
    backgroundColor: brand.fuchsia,
    borderColor: brand.fuchsia,
  },
  checkMark: { color: '#fff', fontSize: 12, fontWeight: '800' },
  checkLabel: { flex: 1, fontSize: 13.5, fontWeight: '600' },
  nameInput: {
    marginHorizontal: 14,
    borderWidth: 1,
    borderRadius: 11,
    paddingHorizontal: 12,
    paddingVertical: 11,
    fontSize: 15,
    fontWeight: '600',
  },
  nameHint: {
    fontSize: 11,
    fontWeight: '500',
    marginHorizontal: 14,
    marginTop: 6,
    marginBottom: 10,
  },
});

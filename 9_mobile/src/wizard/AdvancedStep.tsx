import { useMemo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { ChromeTokens } from '../theme/tokens';
import { brand } from '../theme/tokens';
import { AnchoredSlider } from './AnchoredSlider';
import { BudgetBar } from './BudgetBar';
import { activeConflictWarnings, totalMinutes } from './budget';
import {
  FAST_SLIDER_NOTES,
  FAST_SLIDER_QUESTIONS,
  sliderSaveMinutes,
  totalDistanceCostMinutes,
  totalSaveMinutes,
} from './fastSavings';
import { RangeSlider } from './RangeSlider';
import type { PresetConfig } from './types';

type Shared = {
  config: PresetConfig;
  bikeType: string;
  preset: string | null;
  weights: Record<string, number>;
  onWeightChange: (key: string, value: number) => void;
  budget: number;
  onBudgetChange: (v: number) => void;
  timeSavingFraming?: boolean;
  c: ChromeTokens;
};

function useFineTuneMeta({
  config,
  bikeType,
  preset,
  weights,
  timeSavingFraming = false,
}: Pick<Shared, 'config' | 'bikeType' | 'preset' | 'weights' | 'timeSavingFraming'>) {
  const sliders = config.sliders || {};
  const exemplary = config.exemplary_route || {};
  const bikeRules = config.bike_types?.[bikeType]?.rules || {};
  const hillDisabled = Boolean(bikeRules.hill_weight_epsilon);
  const savingsMode = Boolean(timeSavingFraming && preset === 'fast');

  const used = useMemo(() => {
    if (savingsMode) {
      return totalSaveMinutes(sliders, weights, { hillDisabled });
    }
    return totalMinutes(sliders, weights, bikeType);
  }, [savingsMode, sliders, weights, bikeType, hillDisabled]);

  const distanceNoteMin = useMemo(() => {
    if (!savingsMode) return null;
    return totalDistanceCostMinutes(sliders, weights, bikeType);
  }, [savingsMode, sliders, weights, bikeType]);

  const warningsByWeight = useMemo(() => {
    const active = activeConflictWarnings(
      config.conflict_warnings?.[preset || ''],
      weights,
    );
    const map: Record<string, string> = {};
    active.forEach((cw) => {
      const loser = (cw.weights || []).find((k) => k !== cw.winner);
      if (loser && cw.warning && !map[loser]) map[loser] = cw.warning;
    });
    return map;
  }, [config, preset, weights]);

  return {
    sliders,
    exemplary,
    hillDisabled,
    savingsMode,
    used,
    distanceNoteMin,
    warningsByWeight,
    baseMin: exemplary.minutes_by_bike?.[bikeType],
  };
}

/** Intro + collapse toggle (+ disclaimer once open). */
export function FineTuneLead({
  open,
  onToggle,
  config,
  bikeType,
  preset,
  weights,
  timeSavingFraming = false,
  c,
}: Shared & { open: boolean; onToggle: () => void }) {
  const { exemplary, savingsMode, baseMin } = useFineTuneMeta({
    config, bikeType, preset, weights, timeSavingFraming,
  });

  return (
    <View style={styles.lead}>
      <Text style={[styles.intro, { color: c.textSub }]}>
        {savingsMode
          ? 'Happy with the preset? You can skip this step. Otherwise, set a time-saving goal and tune how hard Fast should hunt.'
          : 'Happy with the preset? You can skip this step. Otherwise, set a detour budget and tune each preference.'}
      </Text>

      <Pressable
        onPress={onToggle}
        style={[styles.collapse, { borderColor: c.line, backgroundColor: c.surface }]}
      >
        <Text style={[styles.collapseText, { color: c.text }]}>Advanced modifications</Text>
        <Text style={[styles.chevron, { color: c.textSub }, open && styles.chevronOpen]}>▾</Text>
      </Pressable>

      {open ? (
        <Text style={[styles.disclaimer, { color: c.textSub }]}>
          {exemplary.disclaimer}
          {baseMin !== undefined
            ? ` On your bike that is about ${Math.round(baseMin)} min at baseline.`
            : ''}
        </Text>
      ) : null}
    </View>
  );
}

/** Detour / time-saving budget — sticky sibling in the shell ScrollView. */
export function FineTuneBudgetSticky({
  config,
  bikeType,
  preset,
  weights,
  budget,
  onBudgetChange,
  timeSavingFraming = false,
  c,
}: Shared) {
  const { savingsMode, used, distanceNoteMin } = useFineTuneMeta({
    config, bikeType, preset, weights, timeSavingFraming,
  });

  return (
    <View style={[styles.stickyBudget, { backgroundColor: c.shellBg, borderBottomColor: c.line }]}>
      <View style={[styles.panel, { borderColor: c.line, backgroundColor: c.surface }]}>
        <Text style={[styles.panelTitle, { color: c.text }]}>
          {savingsMode ? 'Time-saving goal' : 'Detour budget'}
        </Text>
        <View style={styles.budgetHead}>
          <Text style={[styles.budgetLabel, { color: c.textSub }]}>
            {savingsMode
              ? 'How much time should we try to save on a typical ride?'
              : 'How many extra minutes are OK overall?'}
          </Text>
          <Text style={[styles.budgetVal, { color: brand.fuchsia }]}>{budget} min</Text>
        </View>
        <RangeSlider
          value={budget}
          min={0}
          max={30}
          step={1}
          onChange={(v) => onBudgetChange(Math.round(v))}
          c={c}
          accessibilityLabel={savingsMode ? 'Time-saving goal' : 'Detour budget'}
        />
        <BudgetBar
          used={used}
          budget={budget}
          mode={savingsMode ? 'savings' : 'detour'}
          distanceNoteMin={distanceNoteMin}
          c={c}
        />
      </View>
    </View>
  );
}

/** Preference sliders panel. */
export function FineTunePreferences({
  config,
  bikeType,
  preset,
  weights,
  onWeightChange,
  timeSavingFraming = false,
  c,
}: Omit<Shared, 'budget' | 'onBudgetChange'>) {
  const {
    sliders,
    hillDisabled,
    savingsMode,
    warningsByWeight,
  } = useFineTuneMeta({
    config, bikeType, preset, weights, timeSavingFraming,
  });

  return (
    <View style={[styles.panel, styles.prefsPanel, { borderColor: c.line, backgroundColor: c.surface }]}>
      <Text style={[styles.panelTitle, { color: c.text }]}>Preferences</Text>
      {Object.entries(sliders).map(([key, cfg]) => {
        if (key === 'hill_weight' && hillDisabled) {
          return (
            <View key={key} style={styles.disabledHill}>
              <View style={styles.hillHead}>
                <Text style={[styles.hillLabel, { color: c.text }]}>{cfg.label}</Text>
                <Text style={[styles.hillCost, { color: c.textSub }]}>disabled</Text>
              </View>
              <Text style={[styles.hillNote, { color: c.textSub }]}>
                Assumed e-bike: the motor does the climbing, so hill avoidance is off.
              </Text>
            </View>
          );
        }
        return (
          <AnchoredSlider
            key={key}
            sliderKey={key}
            cfg={cfg}
            value={weights[key] ?? 0}
            onChange={onWeightChange}
            bikeType={bikeType}
            warning={warningsByWeight[key]}
            mode={savingsMode ? 'savings' : 'detour'}
            saveMinutes={savingsMode ? sliderSaveMinutes(cfg, weights[key] ?? 0) : null}
            questionOverride={savingsMode ? (FAST_SLIDER_QUESTIONS[key] || null) : null}
            note={savingsMode ? (FAST_SLIDER_NOTES[key] || null) : null}
            c={c}
          />
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  lead: { paddingHorizontal: 20, paddingTop: 8 },
  intro: { fontSize: 13.5, lineHeight: 19, marginBottom: 12, fontWeight: '500' },
  collapse: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 14,
    marginBottom: 12,
  },
  collapseText: { fontSize: 14, fontWeight: '700' },
  chevron: { fontSize: 16, fontWeight: '700' },
  chevronOpen: { transform: [{ rotate: '180deg' }] },
  disclaimer: { fontSize: 12.5, lineHeight: 17, marginBottom: 12, fontWeight: '500' },
  stickyBudget: {
    paddingHorizontal: 20,
    paddingTop: 2,
    paddingBottom: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  panel: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 14,
  },
  prefsPanel: {
    marginHorizontal: 20,
    marginBottom: 12,
    marginTop: 4,
  },
  panelTitle: { fontSize: 13, fontWeight: '700', marginBottom: 10 },
  budgetHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 10,
    marginBottom: 4,
  },
  budgetLabel: { flex: 1, fontSize: 12.5, lineHeight: 17, fontWeight: '500' },
  budgetVal: { fontSize: 13, fontWeight: '700' },
  disabledHill: { marginBottom: 14, gap: 4 },
  hillHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  hillLabel: { fontSize: 13.5, fontWeight: '700' },
  hillCost: { fontSize: 11.5, fontWeight: '600' },
  hillNote: { fontSize: 12.5, lineHeight: 17, fontWeight: '500' },
});

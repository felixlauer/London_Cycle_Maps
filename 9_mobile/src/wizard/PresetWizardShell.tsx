/**
 * Fullscreen profile wizard — web v2 PresetWizardShell (create + edit).
 * Steps: Bike → Style → Fine-tune → Questions.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { apiFetch } from '../api/flaskClient';
import { brand, chromeForTheme } from '../theme/tokens';
import type { ThemeMode } from '../theme/resolveAppearance';
import { useSidebar } from '../ui/sidebar/SidebarContext';
import {
  FineTuneBudgetSticky,
  FineTuneLead,
  FineTunePreferences,
} from './AdvancedStep';
import { BikeTypeStep } from './BikeTypeStep';
import { PresetStep } from './PresetStep';
import { QuestionsStep } from './QuestionsStep';
import { roundHalf, totalMinutes } from './budget';
import { seedFastBudget, totalSaveMinutes } from './fastSavings';
import { MAX_PROFILE_NAME_LEN, validateProfileName } from './profileName';
import {
  DEFAULT_TOGGLES,
  togglesFromProfile,
  type PresetConfig,
  type WizardToggles,
} from './types';

export { MAX_PROFILE_NAME_LEN, validateProfileName } from './profileName';

const STEPS = ['Bike', 'Style', 'Fine-tune', 'Questions'] as const;

type Props = {
  themeMode?: ThemeMode;
  onCreated?: (profile: Record<string, unknown>) => void;
  onUpdated?: (profile: Record<string, unknown>) => void;
  /** Embedded in onboarding — no sidebar pill chrome assumptions. */
  embedded?: boolean;
};

export function PresetWizardShell({
  themeMode: themeProp,
  onCreated,
  onUpdated,
  embedded = false,
}: Props) {
  const { editingProfileId, themeMode: themeFromCtx } = useSidebar();
  const themeMode = themeProp || themeFromCtx;
  const c = chromeForTheme(themeMode);
  const isEditing = embedded ? false : Boolean(editingProfileId);
  const activeEditId = embedded ? null : editingProfileId;
  const footerPadBottom = Platform.OS === 'ios' ? 28 : 14;

  const [config, setConfig] = useState<PresetConfig | null>(null);
  const [loadError, setLoadError] = useState('');
  const [profileLoading, setProfileLoading] = useState(isEditing);
  const [pendingProfile, setPendingProfile] = useState<Record<string, unknown> | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [step, setStep] = useState(0);

  const [bikeType, setBikeType] = useState<string | null>(null);
  const [preset, setPreset] = useState<string | null>(null);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [budget, setBudget] = useState(10);
  const [fineTuneOpen, setFineTuneOpen] = useState(false);
  const [toggles, setToggles] = useState<WizardToggles>(DEFAULT_TOGGLES);
  const [name, setName] = useState('');
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiFetch('/preset_config')
      .then((r: Response) => r.json())
      .then((data: { error?: string } & PresetConfig) => {
        if (cancelled) return;
        if (data.error) setLoadError(data.error);
        else setConfig(data);
      })
      .catch(() => {
        if (!cancelled) setLoadError('Could not load preset configuration.');
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!isEditing || !activeEditId) {
      setProfileLoading(false);
      setPendingProfile(null);
      setHydrated(false);
      return undefined;
    }
    let cancelled = false;
    setProfileLoading(true);
    setHydrated(false);
    setPendingProfile(null);
    apiFetch(`/profiles/${activeEditId}`)
      .then((r: Response) => r.json().then((data: Record<string, unknown> & { error?: string }) => ({ ok: r.ok, data })))
      .then(({ ok, data }: { ok: boolean; data: Record<string, unknown> & { error?: string } }) => {
        if (cancelled) return;
        if (!ok || data.error) {
          setLoadError(data.error || 'Could not load profile.');
          setProfileLoading(false);
          return;
        }
        setPendingProfile(data);
        setProfileLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setLoadError('Could not load profile.');
          setProfileLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [isEditing, activeEditId]);

  useEffect(() => {
    if (!config || !pendingProfile || hydrated) return;
    const p = pendingProfile;
    const bike = String(p.bike_type || 'standard');
    const nextWeights = { ...((p.weights || {}) as Record<string, number>) };
    const nextPreset = (p.preset as string) || null;
    setBikeType(bike);
    setPreset(nextPreset);
    setWeights(nextWeights);
    setToggles(togglesFromProfile(p, config));
    setName(String(p.name || '').slice(0, MAX_PROFILE_NAME_LEN));
    const bikeRules = config.bike_types?.[bike]?.rules || {};
    if (nextPreset === 'fast') {
      setBudget(seedFastBudget(config.sliders, nextWeights, bikeRules));
    } else {
      const est = roundHalf(totalMinutes(config.sliders, nextWeights, bike));
      setBudget(Math.max(5, Math.ceil(est || 10)));
    }
    setHydrated(true);
    setPendingProfile(null);
  }, [config, pendingProfile, hydrated]);

  const selectPreset = (id: string) => {
    if (!config?.presets?.[id]) return;
    setPreset(id);
    const p = config.presets[id];
    const nextWeights = { ...(p.weights || {}) };
    setWeights(nextWeights);
    setToggles((prev) => ({
      ...prev,
      ...(p.toggles || {}),
      vf_infrastructure: prev.vf_infrastructure,
    }));
    const bike = bikeType || 'standard';
    const bikeRules = config.bike_types?.[bike]?.rules || {};
    if (id === 'fast') {
      setBudget(seedFastBudget(config.sliders, nextWeights, bikeRules));
    } else {
      const est = p.estimated_detour_min_by_bike?.[bike] ?? 10;
      setBudget(Math.max(5, Math.ceil(est)));
    }
  };

  const handleWeightChange = (key: string, value: number) => {
    setWeights((prev) => ({ ...prev, [key]: value }));
  };

  const handleToggleChange = (key: string, value: unknown) => {
    setToggles((prev) => ({ ...prev, [key]: value } as WizardToggles));
  };

  const hillDisabled = Boolean(config?.bike_types?.[bikeType || '']?.rules?.hill_weight_epsilon);
  const estUsed = useMemo(() => {
    if (!config || !bikeType) return 0;
    if (preset === 'fast') {
      return totalSaveMinutes(config.sliders, weights, { hillDisabled });
    }
    return roundHalf(totalMinutes(config.sliders, weights, bikeType));
  }, [config, weights, bikeType, preset, hillDisabled]);

  const buildPayloadWeights = () => {
    if (!config || !bikeType) return {};
    const w: Record<string, number> = {};
    Object.keys(config.sliders || {}).forEach((k) => {
      w[k] = weights[k] ?? 0;
    });
    const rules = config.bike_types?.[bikeType]?.rules || {};
    if (rules.hill_weight_epsilon) w.hill_weight = config.epsilon ?? 0.0001;

    const t = config.toggles || {};
    w.light_weight = toggles.light_night ? (t.light_night?.on_value ?? 0.6) : 0;
    if (rules.surface_auto_value != null) {
      w.surface_weight = Number(rules.surface_auto_value);
    } else {
      w.surface_weight = toggles.surface ? (t.surface?.on_value ?? 0.3) : 0;
    }
    w.tfl_live_weight = toggles.jam_comfort
      ? (t.jam_comfort?.comfortable_value ?? 0.1)
      : (t.jam_comfort?.cautious_value ?? 0.4);
    return w;
  };

  const handleSave = async () => {
    setSaveError('');
    const err = validateProfileName(name);
    if (err) {
      setSaveError(err);
      return;
    }
    setSaving(true);
    const body = {
      name: name.trim(),
      weights: buildPayloadWeights(),
      bike_type: bikeType,
      preset,
      toggles,
    };
    try {
      const res = await apiFetch(
        isEditing && activeEditId ? `/profiles/${activeEditId}` : '/profiles',
        {
          method: isEditing ? 'PUT' : 'POST',
          body,
        },
      );
      const data = await res.json();
      if (!res.ok) {
        setSaveError(data.error || (isEditing ? 'Failed to update profile.' : 'Failed to save profile.'));
        return;
      }
      if (isEditing) onUpdated?.(data);
      else onCreated?.(data);
    } catch {
      setSaveError('Backend connection error.');
    } finally {
      setSaving(false);
    }
  };

  // Continue: Bike needs type, Style needs preset, Fine-tune always ok
  const canNext = (step === 0 && !!bikeType) || (step === 1 && !!preset) || step === 2;
  const isLast = step === STEPS.length - 1;
  const nameError = validateProfileName(name);
  const canSave = !saving && !nameError && (!isEditing || hydrated);
  const ready = Boolean(config) && !profileLoading && (!isEditing || hydrated);
  const showFineTune = step === 2 && Boolean(config) && Boolean(bikeType) && ready;
  const stickyHeaderIndices = showFineTune && fineTuneOpen ? [0, 3] : [0];

  const fineTuneProps = config && bikeType ? {
    config,
    bikeType,
    preset,
    weights,
    onWeightChange: handleWeightChange,
    budget,
    onBudgetChange: setBudget,
    timeSavingFraming: true as const,
    c,
  } : null;

  const otherBody = () => {
    if (loadError) {
      return <Text style={[styles.intro, { color: c.danger }]}>{loadError}</Text>;
    }
    if (!ready || !config) {
      return (
        <View style={styles.loading}>
          <ActivityIndicator color={brand.fuchsia} />
          <Text style={[styles.intro, { color: c.textSub }]}>Loading…</Text>
        </View>
      );
    }
    if (step === 0) {
      return (
        <BikeTypeStep
          config={config}
          bikeType={bikeType}
          onSelect={setBikeType}
          c={c}
        />
      );
    }
    if (step === 1) {
      return (
        <PresetStep
          config={config}
          preset={preset}
          onSelect={selectPreset}
          c={c}
        />
      );
    }
    if (step === 3 && bikeType) {
      return (
        <QuestionsStep
          config={config}
          bikeType={bikeType}
          toggles={toggles}
          onToggleChange={handleToggleChange}
          name={name}
          onNameChange={setName}
          c={c}
        />
      );
    }
    return null;
  };

  return (
    <View style={[styles.root, { backgroundColor: c.shellBg }]}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        stickyHeaderIndices={stickyHeaderIndices}
      >
        <View style={[styles.progressSticky, { backgroundColor: c.shellBg }]}>
          <View style={styles.progressRow}>
            {STEPS.map((label, i) => (
              <View
                key={label}
                style={[
                  styles.progressSeg,
                  { backgroundColor: c.line },
                  i < step && { backgroundColor: `${brand.fuchsia}73` },
                  i === step && { backgroundColor: brand.fuchsia },
                ]}
              />
            ))}
          </View>
        </View>

        <View style={styles.header}>
          <Text style={[styles.stepLabel, { color: c.textSub }]}>
            {`Step ${step + 1} of ${STEPS.length} — ${STEPS[step]}`}
          </Text>
          <Text style={[styles.title, { color: c.text }]}>
            {isEditing ? 'Edit riding profile' : 'New riding profile'}
          </Text>
          {isEditing ? (
            <Text style={[styles.blurb, { color: c.textSub }]}>
              Your current bike, style, and preferences are preselected. Walk through the steps to adjust anything, then save.
            </Text>
          ) : null}
        </View>

        {showFineTune && fineTuneProps ? (
          <FineTuneLead
            {...fineTuneProps}
            open={fineTuneOpen}
            onToggle={() => setFineTuneOpen((v) => !v)}
          />
        ) : null}

        {showFineTune && fineTuneOpen && fineTuneProps ? (
          <FineTuneBudgetSticky {...fineTuneProps} />
        ) : null}

        {showFineTune && fineTuneOpen && fineTuneProps ? (
          <FineTunePreferences {...fineTuneProps} />
        ) : null}

        {!showFineTune ? (
          <View style={styles.body}>{otherBody()}</View>
        ) : null}
      </ScrollView>

      <View
        style={[
          styles.footer,
          {
            borderTopColor: c.line,
            backgroundColor: c.shellBg,
            paddingBottom: footerPadBottom,
          },
        ]}
      >
        {step > 0 ? (
          <Pressable
            onPress={() => setStep((s) => s - 1)}
            style={({ pressed }) => [
              styles.btn,
              { borderColor: c.line, backgroundColor: c.surface },
              pressed && { transform: [{ scale: 0.97 }] },
            ]}
          >
            <Text style={[styles.btnText, { color: c.text }]}>Back</Text>
          </Pressable>
        ) : (
          <View style={styles.footerSpacer} />
        )}

        {step >= 2 && config && bikeType ? (
          <Text style={[styles.est, { color: c.textSub }]} numberOfLines={2}>
            {preset === 'fast' ? 'Estimated time saved' : 'Estimated detour'}
            {': '}
            <Text style={{ color: c.text, fontWeight: '700' }}>{estUsed} min</Text>
          </Text>
        ) : null}

        {saveError ? (
          <Text style={[styles.saveError, { color: c.danger }]} numberOfLines={2}>
            {saveError}
          </Text>
        ) : null}

        {!isLast ? (
          <Pressable
            onPress={() => setStep((s) => s + 1)}
            disabled={!canNext || !ready}
            style={({ pressed }) => [
              styles.btn,
              styles.btnPrimary,
              (!canNext || !ready) && { opacity: 0.45 },
              pressed && canNext && ready && { transform: [{ scale: 0.97 }] },
            ]}
          >
            <Text style={styles.btnPrimaryText}>Continue</Text>
          </Pressable>
        ) : (
          <Pressable
            onPress={() => { void handleSave(); }}
            disabled={!canSave}
            style={({ pressed }) => [
              styles.btn,
              styles.btnPrimary,
              !canSave && { opacity: 0.45 },
              pressed && canSave && { transform: [{ scale: 0.97 }] },
            ]}
          >
            {saving ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <Text style={styles.btnPrimaryText}>
                {isEditing ? 'Save changes' : 'Save profile'}
              </Text>
            )}
          </Pressable>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  scroll: { flex: 1 },
  scrollContent: { paddingBottom: 24 },
  progressSticky: {
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 10,
  },
  progressRow: {
    flexDirection: 'row',
    gap: 6,
  },
  progressSeg: {
    flex: 1,
    height: 4,
    borderRadius: 999,
  },
  header: {
    paddingHorizontal: 20,
    paddingBottom: 8,
  },
  stepLabel: {
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 4,
  },
  title: {
    fontSize: 22,
    fontWeight: '700',
    letterSpacing: -0.3,
  },
  blurb: {
    marginTop: 8,
    fontSize: 13,
    fontWeight: '500',
    lineHeight: 18,
  },
  body: {
    paddingHorizontal: 20,
    paddingTop: 8,
  },
  loading: { alignItems: 'center', gap: 12, paddingVertical: 40 },
  intro: { fontSize: 13.5, lineHeight: 19, fontWeight: '500' },
  footer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 14,
    paddingTop: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  btn: {
    minHeight: 44,
    minWidth: 88,
    paddingHorizontal: 16,
    borderRadius: 10,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  footerSpacer: {
    minWidth: 88,
    minHeight: 44,
  },
  btnText: { fontSize: 15, fontWeight: '600' },
  btnPrimary: {
    backgroundColor: brand.fuchsia,
    borderColor: brand.fuchsia,
    marginLeft: 'auto',
  },
  btnPrimaryText: { fontSize: 15, fontWeight: '700', color: '#fff' },
  est: {
    flexGrow: 1,
    flexShrink: 1,
    fontSize: 12,
    fontWeight: '500',
    textAlign: 'center',
  },
  saveError: {
    width: '100%',
    fontSize: 12.5,
    fontWeight: '600',
  },
});

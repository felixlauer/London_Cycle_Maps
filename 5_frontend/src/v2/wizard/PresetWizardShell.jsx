import React, { useEffect, useMemo, useState } from 'react';
import BikeTypeStep from '../../wizard/BikeTypeStep';
import PresetStep from '../../wizard/PresetStep';
import AdvancedStep from '../../wizard/AdvancedStep';
import QuestionsStep from '../../wizard/QuestionsStep';
import { totalMinutes, roundHalf } from '../../wizard/budget';
import { apiFetch } from '../../api/flaskClient';
import { MAX_PROFILE_NAME_LEN, validateProfileName } from './profileName';
import '../../wizard/wizard.css';
import './wizardShell.css';

const STEPS = ['Bike', 'Style', 'Fine-tune', 'Questions'];

const DEFAULT_TOGGLES = {
  light_night: false,
  surface: false,
  jam_comfort: true,
  vf_infrastructure: { shared_path: true, bus_lane: true, painted_lane: false },
};

/** Infer question toggles from stored weights when toggles are incomplete. */
function togglesFromProfile(profile, config) {
  const stored = profile?.toggles || {};
  const weights = profile?.weights || {};
  const cfg = config?.toggles || {};
  const lightOn = cfg.light_night?.on_value ?? 0.6;
  const surfaceOn = cfg.surface?.on_value ?? 0.3;
  const comfortable = cfg.jam_comfort?.comfortable_value ?? 0.1;
  const cautious = cfg.jam_comfort?.cautious_value ?? 0;

  return {
    ...DEFAULT_TOGGLES,
    ...stored,
    light_night: stored.light_night ?? ((weights.light_weight || 0) >= lightOn * 0.5),
    surface: stored.surface ?? ((weights.surface_weight || 0) >= surfaceOn * 0.5),
    jam_comfort: stored.jam_comfort ?? (
      Math.abs((weights.tfl_live_weight || 0) - comfortable)
      <= Math.abs((weights.tfl_live_weight || 0) - cautious)
    ),
    vf_infrastructure: {
      ...DEFAULT_TOGGLES.vf_infrastructure,
      ...(stored.vf_infrastructure || {}),
    },
  };
}

/**
 * Fullscreen v2 wizard shell — create or edit a custom profile.
 */
export default function PresetWizardShell({
  themeMode,
  testMode = false,
  editingProfileId = null,
  onCreated,
  onUpdated,
}) {
  const isEditing = Boolean(editingProfileId);
  const [config, setConfig] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [profileLoading, setProfileLoading] = useState(isEditing);
  const [pendingProfile, setPendingProfile] = useState(null);
  const [hydrated, setHydrated] = useState(false);
  const [step, setStep] = useState(0);

  const [bikeType, setBikeType] = useState(null);
  const [preset, setPreset] = useState(null);
  const [weights, setWeights] = useState({});
  const [budget, setBudget] = useState(10);
  const [toggles, setToggles] = useState(DEFAULT_TOGGLES);
  const [name, setName] = useState('');
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiFetch('/preset_config')
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        if (data.error) setLoadError(data.error);
        else setConfig(data);
      })
      .catch(() => { if (!cancelled) setLoadError('Could not load preset configuration.'); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!isEditing || !editingProfileId) {
      setProfileLoading(false);
      setPendingProfile(null);
      setHydrated(false);
      return undefined;
    }
    let cancelled = false;
    setProfileLoading(true);
    setHydrated(false);
    setPendingProfile(null);
    apiFetch(`/profiles/${editingProfileId}`, { testMode })
      .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
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
  }, [isEditing, editingProfileId, testMode]);

  useEffect(() => {
    if (!config || !pendingProfile || hydrated) return;
    const p = pendingProfile;
    const bike = p.bike_type || 'standard';
    const nextWeights = { ...(p.weights || {}) };
    setBikeType(bike);
    setPreset(p.preset || null);
    setWeights(nextWeights);
    setToggles(togglesFromProfile(p, config));
    setName((p.name || '').slice(0, MAX_PROFILE_NAME_LEN));
    const est = roundHalf(totalMinutes(config.sliders, nextWeights, bike));
    setBudget(Math.max(5, Math.ceil(est || 10)));
    setHydrated(true);
    setPendingProfile(null);
  }, [config, pendingProfile, hydrated]);

  const selectPreset = (id) => {
    setPreset(id);
    const p = config.presets[id];
    setWeights({ ...p.weights });
    setToggles((prev) => ({
      ...prev,
      ...p.toggles,
      vf_infrastructure: prev.vf_infrastructure,
    }));
    const est = p.estimated_detour_min_by_bike?.[bikeType || 'standard'] ?? 10;
    setBudget(Math.max(5, Math.ceil(est)));
  };

  const handleWeightChange = (key, value) => {
    setWeights((prev) => ({ ...prev, [key]: value }));
  };

  const handleToggleChange = (key, value) => {
    setToggles((prev) => ({ ...prev, [key]: value }));
  };

  const estUsed = useMemo(() => {
    if (!config || !bikeType) return 0;
    return roundHalf(totalMinutes(config.sliders, weights, bikeType));
  }, [config, weights, bikeType]);

  const buildPayloadWeights = () => {
    const w = {};
    Object.keys(config.sliders).forEach((k) => { w[k] = weights[k] ?? 0; });
    const rules = config.bike_types[bikeType]?.rules || {};
    if (rules.hill_weight_epsilon) w.hill_weight = config.epsilon;

    const t = config.toggles;
    w.light_weight = toggles.light_night ? t.light_night.on_value : 0;
    if (rules.surface_auto_value) w.surface_weight = rules.surface_auto_value;
    else w.surface_weight = toggles.surface ? t.surface.on_value : 0;
    w.tfl_live_weight = toggles.jam_comfort
      ? t.jam_comfort.comfortable_value
      : t.jam_comfort.cautious_value;
    return w;
  };

  const handleSave = async () => {
    setSaveError('');
    const nameError = validateProfileName(name);
    if (nameError) {
      setSaveError(nameError);
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
        isEditing ? `/profiles/${editingProfileId}` : '/profiles',
        {
          method: isEditing ? 'PUT' : 'POST',
          testMode,
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

  const canNext = (step === 0 && !!bikeType) || (step === 1 && !!preset) || step === 2;
  const isLast = step === STEPS.length - 1;
  const nameError = validateProfileName(name);
  const canSave = !saving && !nameError && (!isEditing || hydrated);
  const ready = Boolean(config) && !profileLoading && (!isEditing || hydrated);

  const body = () => {
    if (loadError) return <p className="v2wiz-intro">{loadError}</p>;
    if (!ready) return <p className="v2wiz-intro">Loading…</p>;
    if (step === 0) return <BikeTypeStep config={config} bikeType={bikeType} onSelect={setBikeType} />;
    if (step === 1) return <PresetStep config={config} preset={preset} onSelect={selectPreset} />;
    if (step === 2) {
      return (
        <AdvancedStep
          config={config}
          bikeType={bikeType}
          preset={preset}
          weights={weights}
          onWeightChange={handleWeightChange}
          budget={budget}
          onBudgetChange={setBudget}
        />
      );
    }
    return (
      <QuestionsStep
        config={config}
        bikeType={bikeType}
        toggles={toggles}
        onToggleChange={handleToggleChange}
        name={name}
        onNameChange={setName}
      />
    );
  };

  return (
    <div className="v2wiz" data-theme={themeMode}>
      <div className="v2wiz__scroll">
        <div className="v2wiz__progress-sticky" aria-hidden>
          <div className="v2wiz__header-inner">
            <div className="v2wiz__progress">
              {STEPS.map((label, i) => (
                <div
                  key={label}
                  className={`v2wiz__progress-seg${i <= step ? ' is-done' : ''}${i === step ? ' is-current' : ''}`}
                />
              ))}
            </div>
          </div>
        </div>

        <header className="v2wiz__header">
          <div className="v2wiz__header-inner">
            <p className="v2wiz__step-label">
              Step {step + 1} of {STEPS.length} — {STEPS[step]}
            </p>
            <h1 className="v2wiz__title">
              {isEditing ? 'Edit riding profile' : 'New riding profile'}
            </h1>
            {isEditing && (
              <p className="v2wiz__blurb">
                Your current bike, style, and preferences are preselected. Walk through the steps to adjust anything, then save.
              </p>
            )}
          </div>
        </header>

        <div className="v2wiz__body">{body()}</div>
      </div>

      <footer className="v2wiz__footer">
        {step > 0 ? (
          <button type="button" className="v2wiz-btn" onClick={() => setStep(step - 1)}>
            Back
          </button>
        ) : <span />}
        {step >= 2 && config && bikeType && (
          <span className="v2wiz-est">
            Estimated detour: <strong>{estUsed} min</strong>
          </span>
        )}
        {saveError && <span className="v2wiz-error">{saveError}</span>}
        {!isLast ? (
          <button
            type="button"
            className="v2wiz-btn v2wiz-btn--primary"
            disabled={!canNext || !ready}
            onClick={() => setStep(step + 1)}
          >
            Continue
          </button>
        ) : (
          <button
            type="button"
            className="v2wiz-btn v2wiz-btn--primary"
            disabled={!canSave}
            onClick={handleSave}
          >
            {saving ? 'Saving…' : (isEditing ? 'Save changes' : 'Save profile')}
          </button>
        )}
      </footer>
    </div>
  );
}

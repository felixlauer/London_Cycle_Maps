/**
 * Shared preset_config types for the profile wizard.
 */
import type { SliderCfg } from './budget';

export type VfInfra = {
  shared_path: boolean;
  bus_lane: boolean;
  painted_lane: boolean;
};

export type WizardToggles = {
  light_night: boolean;
  surface: boolean;
  jam_comfort: boolean;
  avoid_canals: boolean;
  vf_infrastructure: VfInfra;
};

export const DEFAULT_TOGGLES: WizardToggles = {
  light_night: false,
  surface: false,
  jam_comfort: true,
  avoid_canals: false,
  vf_infrastructure: { shared_path: true, bus_lane: true, painted_lane: false },
};

export type PresetConfig = {
  epsilon?: number;
  exemplary_route?: {
    disclaimer?: string;
    minutes_by_bike?: Record<string, number>;
  };
  conflict_warnings?: Record<string, Array<{
    trigger?: Record<string, { gte?: number; lt?: number }>;
    weights?: string[];
    winner?: string;
    warning?: string;
  }>>;
  bike_types?: Record<string, {
    label?: string;
    note?: string;
    speed_kmh?: number;
    rules?: Record<string, unknown>;
  }>;
  presets?: Record<string, {
    label?: string;
    description?: string;
    weights?: Record<string, number>;
    toggles?: Partial<WizardToggles>;
    estimated_detour_min_by_bike?: Record<string, number>;
  }>;
  sliders?: Record<string, SliderCfg>;
  toggles?: {
    light_night?: { question?: string; help?: string; on_value?: number; hidden_for?: string[] };
    surface?: { question?: string; help?: string; on_value?: number; hidden_for?: string[] };
    jam_comfort?: {
      question?: string;
      help?: string;
      comfortable_value?: number;
      cautious_value?: number;
    };
    avoid_canals?: { question?: string; help?: string; weight_key?: string | null };
    vf_infrastructure?: {
      question?: string;
      help?: string;
      options?: Record<string, { label?: string; default?: boolean; help_note?: string }>;
    };
  };
};

export function togglesFromProfile(
  profile: Record<string, unknown>,
  config: PresetConfig,
): WizardToggles {
  const stored = (profile?.toggles || {}) as Partial<WizardToggles>;
  const weights = (profile?.weights || {}) as Record<string, number>;
  const cfg = config?.toggles || {};
  const lightOn = cfg.light_night?.on_value ?? 0.6;
  const surfaceOn = cfg.surface?.on_value ?? 0.3;
  const comfortable = cfg.jam_comfort?.comfortable_value ?? 0.1;
  const cautious = cfg.jam_comfort?.cautious_value ?? 0;
  const tfl = weights.tfl_live_weight || 0;

  return {
    ...DEFAULT_TOGGLES,
    ...stored,
    light_night: stored.light_night ?? ((weights.light_weight || 0) >= lightOn * 0.5),
    surface: stored.surface ?? ((weights.surface_weight || 0) >= surfaceOn * 0.5),
    jam_comfort: stored.jam_comfort ?? (
      Math.abs(tfl - comfortable) <= Math.abs(tfl - cautious)
    ),
    avoid_canals: stored.avoid_canals ?? false,
    vf_infrastructure: {
      ...DEFAULT_TOGGLES.vf_infrastructure,
      ...(stored.vf_infrastructure || {}),
    },
  };
}

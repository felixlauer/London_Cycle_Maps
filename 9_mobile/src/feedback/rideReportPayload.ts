/**
 * Builds the versioned document stored against one rider tap.
 *
 * Deliberately fat: the tap itself carries no words, so everything we might
 * later want to reconstruct the moment has to be captured now. Unused keys are
 * kept rather than pruned so old rows stay comparable with new ones.
 *
 * Pure — no I/O, no clock beyond what is passed in — so it is unit-testable.
 */
import type { RouteProgressEvent } from '../native/maplibreNav';
import type { RideReportCategoryId } from './rideReportCategories';

export const RIDE_REPORT_SCHEMA = 1;

export type RideReportInput = {
  clientEventId: string;
  category: RideReportCategoryId;
  deviceId: string | null;
  personalOnly: boolean;
  simulate: boolean;
  /** Latest raw engine event. Null if the tap beat the first fix. */
  progress: RouteProgressEvent | null;
  /** Fallback position when there is no progress event yet. */
  fallbackLocation?: [number, number] | null;
  nav: {
    rerouting: boolean;
    tracking: boolean;
    overviewActive: boolean;
    muted: boolean;
    cyclewaysVisible: boolean;
    /** Maneuver being ridden towards, from the flattened steps. */
    maneuverType?: string | null;
    maneuverModifier?: string | null;
    maneuverInstruction?: string | null;
    stepName?: string | null;
    startedAtMs?: number | null;
  };
  route: {
    origin?: [number, number] | null;
    destination?: [number, number] | null;
    vias?: ([number, number] | null)[];
    distance?: number | null;
    duration?: number | null;
    /** First and last path points — cheap stand-in for a geometry hash. */
    firstPoint?: [number, number] | null;
    lastPoint?: [number, number] | null;
    pointCount?: number | null;
  };
  profile: {
    profileId?: string | null;
    preset?: string | null;
    bikeType?: string | null;
    weights?: Record<string, number> | null;
    userId?: string | null;
  };
  device: {
    platform: string;
    osVersion?: string | number | null;
    appVersion?: string | null;
    themeMode?: string | null;
    batteryLevel?: number | null;
    batteryState?: string | null;
    netState?: string | null;
  };
  night: {
    isDark: boolean;
    forcedMode?: string | null;
    departAtIso?: string | null;
  };
  timing: {
    tappedAtMs: number;
    /** 0 when the picker timed out into `general`. */
    elapsedMsIntoPicker: number;
  };
};

export type RideReportPayload = {
  schema: number;
  client_event_id: string;
  category: RideReportCategoryId;
  source: string;
  personal_only: boolean;
  simulate: boolean;
  device_id: string | null;
  fix: Record<string, unknown>;
  nav: Record<string, unknown>;
  route: Record<string, unknown>;
  profile: Record<string, unknown>;
  device: Record<string, unknown>;
  night: Record<string, unknown>;
  timing: Record<string, unknown>;
  extra: Record<string, unknown>;
};

export type RideReportEnvelope = {
  client_event_id: string;
  category: RideReportCategoryId;
  device_id: string | null;
  source: string;
  lat: number;
  lon: number;
  simulate: boolean;
  personal_only: boolean;
  payload: RideReportPayload;
};

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function localTimeParts(tappedAtMs: number) {
  const at = new Date(tappedAtMs);
  let tz: string | null = null;
  try {
    tz = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    tz = null;
  }
  return {
    tapped_at_utc: at.toISOString(),
    tapped_at_local: at.toString(),
    tz,
  };
}

/**
 * Returns null when there is no usable position — a report without a place on
 * the network is not worth storing, and the backend would reject it anyway.
 */
export function buildRideReport(input: RideReportInput): RideReportEnvelope | null {
  const p = input.progress;
  const lat = num(p?.latitude) ?? input.fallbackLocation?.[0] ?? null;
  const lon = num(p?.longitude) ?? input.fallbackLocation?.[1] ?? null;
  if (lat == null || lon == null) return null;

  const startedAt = input.nav.startedAtMs;

  const payload: RideReportPayload = {
    schema: RIDE_REPORT_SCHEMA,
    client_event_id: input.clientEventId,
    category: input.category,
    source: 'tbt_island',
    personal_only: input.personalOnly,
    simulate: input.simulate,
    device_id: input.deviceId,

    fix: {
      lat,
      lon,
      alt_m: num(p?.altitude),
      speed_mps: num(p?.speed),
      gps_course_deg: num(p?.bearing),
      compass_heading_deg: num(p?.compassHeadingDeg),
      has_heading: p?.hasHeading ?? null,
      h_acc_m: num(p?.hAccuracyM),
      v_acc_m: num(p?.vAccuracyM),
      speed_acc_mps: num(p?.speedAccuracyMps),
      bearing_acc_deg: num(p?.bearingAccuracyDeg),
      gps_epoch_ms: num(p?.gpsEpochMs),
      mocked: p?.mocked ?? null,
      puck_source: p?.puckSource ?? null,
    },

    nav: {
      leg_index: num(p?.legIndex),
      step_index: num(p?.stepIndex),
      upcoming_leg_index: num(p?.upcomingLegIndex),
      upcoming_step_index: num(p?.upcomingStepIndex),
      step_distance_remaining_m: num(p?.stepDistanceRemaining),
      distance_remaining_m: num(p?.distanceRemaining),
      duration_remaining_s: num(p?.durationRemaining),
      fraction_traveled: num(p?.fractionTraveled),
      distance_from_route_m: num(p?.distanceFromRoute),
      rerouting: input.nav.rerouting,
      tracking: input.nav.tracking,
      overview_active: input.nav.overviewActive,
      muted: input.nav.muted,
      cycleways_visible: input.nav.cyclewaysVisible,
      maneuver_type: input.nav.maneuverType ?? null,
      maneuver_modifier: input.nav.maneuverModifier ?? null,
      maneuver_instruction: input.nav.maneuverInstruction ?? null,
      step_name: input.nav.stepName ?? null,
      elapsed_ms_into_nav:
        startedAt != null ? Math.max(0, input.timing.tappedAtMs - startedAt) : null,
    },

    route: {
      origin: input.route.origin ?? null,
      destination: input.route.destination ?? null,
      vias: (input.route.vias || []).filter(Boolean),
      distance_m: num(input.route.distance),
      duration_s: num(input.route.duration),
      first_point: input.route.firstPoint ?? null,
      last_point: input.route.lastPoint ?? null,
      point_count: num(input.route.pointCount),
    },

    profile: {
      profile_id: input.profile.profileId ?? null,
      preset: input.profile.preset ?? null,
      bike_type: input.profile.bikeType ?? null,
      weights: input.profile.weights ?? null,
      user_id: input.profile.userId ?? null,
    },

    device: {
      platform: input.device.platform,
      os_version: input.device.osVersion ?? null,
      app_version: input.device.appVersion ?? null,
      theme_mode: input.device.themeMode ?? null,
      battery_level: num(input.device.batteryLevel),
      battery_state: input.device.batteryState ?? null,
      net_state: input.device.netState ?? null,
    },

    night: {
      is_dark: input.night.isDark,
      forced_mode: input.night.forcedMode ?? null,
      depart_at_iso: input.night.departAtIso ?? null,
    },

    timing: {
      ...localTimeParts(input.timing.tappedAtMs),
      elapsed_ms_into_picker: input.timing.elapsedMsIntoPicker,
    },

    extra: {},
  };

  return {
    client_event_id: input.clientEventId,
    category: input.category,
    device_id: input.deviceId,
    source: 'tbt_island',
    lat,
    lon,
    simulate: input.simulate,
    personal_only: input.personalOnly,
    payload,
  };
}

/** Category patch after the rider picks one, keeping the payload in step. */
export function withCategory(
  envelope: RideReportEnvelope,
  category: RideReportCategoryId,
  elapsedMsIntoPicker: number,
): RideReportEnvelope {
  return {
    ...envelope,
    category,
    payload: {
      ...envelope.payload,
      category,
      timing: {
        ...envelope.payload.timing,
        elapsed_ms_into_picker: elapsedMsIntoPicker,
      },
    },
  };
}

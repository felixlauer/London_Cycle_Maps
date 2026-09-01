/** Shared routing / mode constants — mirror web v2/routing/constants.js */

export const PRESET_META: Record<string, { id: string; label: string; preset: string; Icon: string }> = {
  preset_safe: { id: 'preset_safe', label: 'Safe', preset: 'safe', Icon: 'Shield' },
  preset_fast: { id: 'preset_fast', label: 'Fast', preset: 'fast', Icon: 'Zap' },
  preset_leisure: { id: 'preset_leisure', label: 'Leisure', preset: 'leisure', Icon: 'Trees' },
};

export const PRESET_ORDER = ['preset_safe', 'preset_fast', 'preset_leisure'] as const;

export const BIKE_OPTIONS = [
  { id: 'standard', label: 'Regular', Icon: 'Bike' },
  { id: 'road', label: 'Road', Icon: 'Road' },
  { id: 'ebike', label: 'E-bike', Icon: 'Zap' },
  { id: 'cargo', label: 'Cargo', Icon: 'Package' },
] as const;

export const SANTANDER_BIKE_OPTIONS = [
  { id: 'standard', label: 'Reg (Sant.)', Icon: 'Bike' },
  { id: 'ebike', label: 'E-bike (Sant.)', Icon: 'Zap' },
] as const;

export type BikeTypeId = (typeof BIKE_OPTIONS)[number]['id'];

export function bikeLabel(bikeType: string | null | undefined, santander = false) {
  if (santander) {
    return bikeType === 'ebike' ? 'E-bike (Sant.)' : 'Reg (Sant.)';
  }
  return BIKE_OPTIONS.find((b) => b.id === bikeType)?.label || 'Regular';
}

export function coerceBikeForSantander(bikeType: string | null | undefined): BikeTypeId {
  if (bikeType === 'ebike') return 'ebike';
  return 'standard';
}

export type ProfileRow = {
  id?: string;
  name?: string;
  is_system?: boolean;
  bike_type?: string;
  toggles?: { light_night?: boolean; surface?: boolean; jam_comfort?: boolean };
  weights?: { light_weight?: number; [key: string]: number | undefined };
};

export type ViaPoint = {
  id: string;
  coord: [number, number] | null;
  label: string;
};

export function buildFavouriteSlots(profiles: ProfileRow[] | null | undefined, order: string[] | null = null) {
  const customs = (profiles || []).filter((p) => {
    if (!p?.id) return false;
    if (p.is_system) return false;
    if (PRESET_META[p.id]) return false;
    if (String(p.id).startsWith('preset_')) return false;
    return true;
  });
  let sorted = customs;
  if (order?.length) {
    const rank = new Map(order.map((id, i) => [id, i]));
    sorted = [...customs].sort((a, b) => {
      const ra = rank.has(a.id!) ? rank.get(a.id!)! : 9999;
      const rb = rank.has(b.id!) ? rank.get(b.id!)! : 9999;
      if (ra !== rb) return ra - rb;
      return String(a.name || '').localeCompare(String(b.name || ''));
    });
  }
  return sorted.slice(0, 3).map((p, i) => ({
    slot: `C${i + 1}`,
    id: p.id!,
    name: p.name || p.id!,
    bike_type: p.bike_type || 'standard',
  }));
}

export const MAX_VIAS = 3;

export const BLOCKED = {
  santanderNeedsNoStops: 'Remove stops to use Santander',
  departNeedsNoSantander: 'Turn off Santander to choose a departure time',
  addStopNeedsNoSantander: 'Turn off Santander to add stops',
  addStopMax: `You can add up to ${MAX_VIAS} stops`,
  getRouteNeedsStart: 'Set a start point first',
  getRouteNeedsEnd: 'Set a destination first',
  getRouteNeedsStops: 'Fill all stops before getting a route',
  getRouteBusy: 'Still working on your route…',
  editFavouritesSoon: 'Favourites editing coming soon',
  overlayNeedsRoute: 'Get a route first to use overlays',
  mapBusyHire: 'Select a Santander station on the map',
} as const;

/**
 * Ride feedback confirmations. Deliberately terse — the rider is moving and the
 * pill is read at a glance, not studied.
 */
export const RIDE_REPORT_COPY = {
  saved: 'Saved — thanks',
  /** Picker timed out: the point is kept, just uncategorised. */
  noted: 'Noted',
  offline: 'Saved on this phone',
} as const;

/** Alert priorities — higher wins; only one shown. */
export const ALERT_PRIORITY: Record<string, number> = {
  confirm: 120,
  error: 100,
  santander_guide: 80,
  bike_override: 60,
  no_ebike: 55,
  warning: 40,
  // Above info so a save confirmation is not buried, below warning so it never
  // covers something the rider needs to act on.
  ride_report: 30,
  info: 20,
};

/** Transient TTLs (ms). Sticky confirms skip TTL. */
export const ALERT_TTL_MS: Record<string, number | null> = {
  confirm: null,
  error: 5000,
  santander_guide: 6000,
  bike_override: 3600,
  no_ebike: 4500,
  warning: 4000,
  ride_report: 3200,
  info: 3200,
};

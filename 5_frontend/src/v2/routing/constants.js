/** Shared routing / mode constants for v2 */

export const PRESET_META = {
  preset_safe: { id: 'preset_safe', label: 'Safe', preset: 'safe', Icon: 'Shield' },
  preset_fast: { id: 'preset_fast', label: 'Fast', preset: 'fast', Icon: 'Zap' },
  preset_leisure: { id: 'preset_leisure', label: 'Leisure', preset: 'leisure', Icon: 'Trees' },
};

export const PRESET_ORDER = ['preset_safe', 'preset_fast', 'preset_leisure'];

export const BIKE_OPTIONS = [
  { id: 'standard', label: 'Regular', Icon: 'Bike' },
  { id: 'road', label: 'Road', Icon: 'Road' },
  { id: 'ebike', label: 'E-bike', Icon: 'Zap' },
  { id: 'cargo', label: 'Cargo', Icon: 'Package' },
];

export const SANTANDER_BIKE_OPTIONS = [
  { id: 'standard', label: 'Reg (Sant.)', Icon: 'Bike' },
  { id: 'ebike', label: 'E-bike (Sant.)', Icon: 'Zap' },
];

export function bikeLabel(bikeType, santander) {
  if (santander) {
    return bikeType === 'ebike' ? 'E-bike (Sant.)' : 'Reg (Sant.)';
  }
  return BIKE_OPTIONS.find((b) => b.id === bikeType)?.label || 'Regular';
}

export function coerceBikeForSantander(bikeType) {
  if (bikeType === 'ebike') return 'ebike';
  return 'standard';
}

/** First 3 custom (non-system) profiles as C1–C3 favourites.
 * Optional `order` (profile id list) controls ranking; unknown ids append by name.
 */
export function buildFavouriteSlots(profiles, order = null) {
  const customs = (profiles || []).filter((p) => {
    if (p.is_system) return false;
    if (PRESET_META[p.id]) return false;
    if (String(p.id).startsWith('preset_')) return false;
    return true;
  });
  let sorted = customs;
  if (order?.length) {
    const rank = new Map(order.map((id, i) => [id, i]));
    sorted = [...customs].sort((a, b) => {
      const ra = rank.has(a.id) ? rank.get(a.id) : 9999;
      const rb = rank.has(b.id) ? rank.get(b.id) : 9999;
      if (ra !== rb) return ra - rb;
      return String(a.name || '').localeCompare(String(b.name || ''));
    });
  }
  return sorted.slice(0, 3).map((p, i) => ({
    slot: `C${i + 1}`,
    id: p.id,
    name: p.name,
    bike_type: p.bike_type || 'standard',
  }));
}

export const MAX_VIAS = 3;

/** User-facing reasons when a control is blocked (alert pill). */
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
  mapBusyHire: 'Select a Santander station on the map',
  overlayNeedsRoute: 'Get a route first to use overlays',
};

/** Alert priorities — higher wins; only one shown. */
export const ALERT_PRIORITY = {
  confirm: 120,
  error: 100,
  santander_guide: 80,
  bike_override: 60,
  no_ebike: 55,
  warning: 40,
  info: 20,
};

/** Every alert is transient — guides get a little longer. Sticky confirms skip TTL. */
export const ALERT_TTL_MS = {
  confirm: null,
  error: 5000,
  santander_guide: 6000,
  bike_override: 3600,
  no_ebike: 4500,
  warning: 4000,
  info: 3200,
};

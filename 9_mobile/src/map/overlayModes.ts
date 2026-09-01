/**
 * Overlay mode rail meta — mirror web v2/map/overlayModes.js.
 */

export const OVERLAY_MODE_META: Record<string, {
  id: string;
  label: string;
  emptyMessage: string;
  Icon: string;
  hub: string;
  alwaysAvailable: boolean;
  default?: boolean;
  requiresDark?: boolean;
  typedKey: string;
}> = {
  cycle: {
    id: 'cycle',
    label: 'Cycleways',
    emptyMessage: 'No cycleways found on this route',
    Icon: 'Route',
    hub: '#4D9DE0',
    alwaysAvailable: true,
    default: true,
    typedKey: 'cycle_typed',
  },
  green: {
    id: 'green',
    label: 'Attractions',
    emptyMessage: 'No attractions on this route',
    Icon: 'FerrisWheel',
    hub: '#3BB273',
    alwaysAvailable: true,
    typedKey: 'green_typed',
  },
  surface: {
    id: 'surface',
    label: 'Surface',
    emptyMessage: 'No rough surfaces found',
    Icon: 'Globe',
    hub: '#13C2A4',
    alwaysAvailable: true,
    typedKey: 'surface_typed',
  },
  hills: {
    id: 'hills',
    label: 'Hills',
    emptyMessage: 'No steep segments on this route',
    Icon: 'Mountain',
    hub: '#8717BF',
    alwaysAvailable: true,
    typedKey: 'hill_typed',
  },
  light: {
    id: 'light',
    label: 'Light',
    emptyMessage: 'No lighting data on this route',
    Icon: 'Lightbulb',
    hub: '#FDE74C',
    alwaysAvailable: false,
    requiresDark: true,
    typedKey: 'light_typed',
  },
};

export const OVERLAY_MODE_ORDER = ['cycle', 'green', 'surface', 'hills', 'light'] as const;

export const DEFAULT_OVERLAY_MODE = 'cycle';

export const TRAFFIC_OVERLAY = {
  id: 'traffic',
  hub: '#F18805',
  label: 'Traffic',
  typedKey: 'disruption_typed',
};

export const OVERLAY_KIND_META: Record<string, { label: string; color: string }> = {
  segregated: { label: 'Segregated', color: '#4D9DE0' },
  bus_shared: { label: 'Bus shared', color: '#2E7AB8' },
  car_shared: { label: 'Car shared', color: '#7BB8E8' },
  tfl: { label: 'TfL network', color: '#1565C0' },
  park: { label: 'Park', color: '#3BB273' },
  river: { label: 'River path', color: '#2A9D8F' },
  sight: { label: 'Scenic', color: '#52B788' },
  rough: { label: 'Rough surface', color: '#13C2A4' },
  steep: { label: 'Steep', color: '#8717BF' },
  lit: { label: 'Lit', color: '#FDE74C' },
  unlit: { label: 'Unlit', color: '#A89B2E' },
  traffic: { label: 'Traffic', color: '#F18805' },
};

export function availableOverlayModes(isDark: boolean) {
  return OVERLAY_MODE_ORDER
    .map((id) => OVERLAY_MODE_META[id])
    .filter((m) => m.alwaysAvailable || (m.requiresDark && isDark));
}

export function chunksForMode(safest: Record<string, unknown> | null | undefined, modeId: string) {
  const meta = OVERLAY_MODE_META[modeId];
  if (!meta || !safest) return [];
  const chunks = safest[meta.typedKey];
  return Array.isArray(chunks) ? chunks : [];
}

export function trafficChunks(safest: Record<string, unknown> | null | undefined) {
  const chunks = safest?.[TRAFFIC_OVERLAY.typedKey];
  return Array.isArray(chunks) ? chunks : [];
}

export function sumChunkLengthM(chunks: { length_m?: number }[]) {
  return (chunks || []).reduce((acc, c) => acc + (Number(c.length_m) || 0), 0);
}

export function formatOverlayLength(metres: number, units: 'metric' | 'imperial' = 'metric') {
  const m = Number(metres) || 0;
  if (units === 'imperial') {
    const miles = m / 1609.344;
    if (miles < 0.1) return `${Math.round(m / 0.3048)} ft`;
    return `${miles < 10 ? miles.toFixed(1) : Math.round(miles)} mi`;
  }
  if (m < 1000) return `${Math.round(m)} m`;
  return `${(m / 1000).toFixed(1)} km`;
}

export function formatOverlayPct(partM: number, totalM: number) {
  if (!totalM || totalM <= 0) return null;
  const pct = Math.round((partM / totalM) * 100);
  return `${Math.max(0, Math.min(100, pct))}%`;
}

/** TomTom cluster_type / legacy keys → display labels (web overlayModes). */
const TRAFFIC_CATEGORY_LABELS: Record<string, string> = {
  jam: 'Traffic jam',
  closure: 'Road closure',
  roadworks: 'Roadworks',
  environmental: 'Environmental hazard',
  other: 'Traffic disruption',
};

function humanizeRaw(str: unknown) {
  return String(str ?? '').replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
}

function sentenceCase(str: unknown) {
  const s = humanizeRaw(str);
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * Consistent hover chip / marker title for map overlay segments (web formatOverlayHoverDetail).
 */
export function formatOverlayHoverDetail(kind: string, props: Record<string, unknown> = {}) {
  const meta = OVERLAY_KIND_META[kind] || { label: kind };

  if (kind === 'traffic') {
    const raw = props.category;
    if (raw == null || raw === '') return meta.label;
    const key = String(raw).trim().toLowerCase();
    if (TRAFFIC_CATEGORY_LABELS[key]) return TRAFFIC_CATEGORY_LABELS[key];
    if (/^\d+$/.test(key)) return TRAFFIC_CATEGORY_LABELS.jam;
    return sentenceCase(raw);
  }
  if (kind === 'park' || kind === 'sight') {
    const name = props.name || props.label;
    if (name) return sentenceCase(name);
    return meta.label;
  }
  if (kind === 'rough') {
    if (props.surface) return sentenceCase(props.surface);
    return meta.label;
  }
  const custom = props.label || props.name;
  if (custom) return sentenceCase(custom);
  return meta.label;
}

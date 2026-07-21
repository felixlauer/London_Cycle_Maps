/**
 * v2 overlay mode rail — locked plan (user 2026-07-17).
 *
 * Rail sits above free-floating zoom/locate in the bottom-right.
 * One mode active at a time (or none — click active to clear).
 * Expand label on select; collapse is the same spring reversed.
 * Live traffic (Tiger Orange #F18805) is always-on, not a mode slot.
 */
import { Route, FerrisWheel, Globe, Mountain, Lightbulb } from 'lucide-react';
import { formatDistance } from '../units';

export const OVERLAY_MODE_META = {
  cycle: {
    id: 'cycle',
    label: 'Cycleways',
    emptyMessage: 'No cycleways found on this route',
    Icon: Route,
    hub: '#4D9DE0', // Blue Bell
    alwaysAvailable: true,
    default: true,
    typedKey: 'cycle_typed',
  },
  green: {
    id: 'green',
    label: 'Attractions',
    emptyMessage: 'No attractions on this route',
    Icon: FerrisWheel,
    hub: '#3BB273', // Jungle Green
    alwaysAvailable: true,
    typedKey: 'green_typed',
  },
  surface: {
    id: 'surface',
    label: 'Surface',
    emptyMessage: 'No rough surfaces found',
    Icon: Globe,
    hub: '#13C2A4', // Turquoise
    alwaysAvailable: true,
    typedKey: 'surface_typed',
  },
  hills: {
    id: 'hills',
    label: 'Hills',
    emptyMessage: 'No steep segments on this route',
    Icon: Mountain,
    hub: '#8717BF', // Violet
    alwaysAvailable: true,
    typedKey: 'hill_typed',
  },
  light: {
    id: 'light',
    label: 'Light',
    emptyMessage: 'No lighting data on this route',
    Icon: Lightbulb,
    hub: '#FDE74C', // Banana Cream
    alwaysAvailable: false,
    requiresDark: true,
    typedKey: 'light_typed',
  },
};

export const OVERLAY_MODE_ORDER = ['cycle', 'green', 'surface', 'hills', 'light'];

export const DEFAULT_OVERLAY_MODE = 'cycle';

/** Always-on disruption styling (not a selectable mode). */
export const TRAFFIC_OVERLAY = {
  id: 'traffic',
  hub: '#F18805', // Tiger Orange
  label: 'Traffic',
  typedKey: 'disruption_typed',
};

/** Subtype colours / labels within each mode. */
export const OVERLAY_KIND_META = {
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

/** TomTom cluster_type / legacy keys → display labels for hover chips. */
const TRAFFIC_CATEGORY_LABELS = {
  jam: 'Traffic jam',
  closure: 'Road closure',
  roadworks: 'Roadworks',
  environmental: 'Environmental hazard',
  other: 'Traffic disruption',
};

function humanizeRaw(str) {
  return String(str).replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
}

/** First character upper; preserves existing word casing (TfL categories). */
function sentenceCase(str) {
  const s = humanizeRaw(str);
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * Consistent hover chip / marker title for map overlay segments.
 * @param {string} kind — overlay kind (traffic, rough, park, …)
 * @param {object} [props] — chunk / feature properties
 */
export function formatOverlayHoverDetail(kind, props = {}) {
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

export function availableOverlayModes(isDark) {
  return OVERLAY_MODE_ORDER
    .map((id) => OVERLAY_MODE_META[id])
    .filter((m) => m.alwaysAvailable || (m.requiresDark && isDark));
}

export function chunksForMode(safest, modeId) {
  const meta = OVERLAY_MODE_META[modeId];
  if (!meta || !safest) return [];
  return safest[meta.typedKey] || [];
}

export function trafficChunks(safest) {
  return safest?.disruption_typed || [];
}

export function sumChunkLengthM(chunks) {
  return (chunks || []).reduce((acc, c) => acc + (Number(c.length_m) || 0), 0);
}

export function formatOverlayLength(metres, units = 'metric') {
  return formatDistance(metres, units);
}

export function formatOverlayPct(partM, totalM) {
  if (!totalM || totalM <= 0) return null;
  const pct = Math.round((partM / totalM) * 100);
  return `${Math.max(0, Math.min(100, pct))}%`;
}

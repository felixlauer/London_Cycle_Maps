/**
 * Per-mode aggregates for island donuts / bar charts.
 * VF-vs-TfL double counting is already resolved server-side
 * (get_typed_cycle_sections gives VF kinds priority over 'tfl').
 */
import {
  OVERLAY_MODE_META,
  OVERLAY_KIND_META,
  TRAFFIC_OVERLAY,
} from '../map/overlayModes';

/** Kinds that count toward a mode's centre metric + arcs/bars. */
export const MODE_ARC_KINDS = {
  cycle: ['segregated', 'bus_shared', 'car_shared', 'tfl'],
  green: ['park', 'river', 'sight'],
  surface: ['rough'],
  hills: ['steep'],
  light: ['lit'],
  traffic: ['traffic'],
};

export function islandModeMeta(modeId) {
  if (modeId === 'traffic') {
    return {
      id: 'traffic',
      label: TRAFFIC_OVERLAY.label,
      hub: TRAFFIC_OVERLAY.hub,
      typedKey: TRAFFIC_OVERLAY.typedKey,
    };
  }
  const m = OVERLAY_MODE_META[modeId];
  if (!m) return null;
  return { id: m.id, label: m.label, hub: m.hub, typedKey: m.typedKey };
}

/**
 * Aggregate typed chunk lengths per kind for one mode.
 * Returns { meta, totalM, kinds: [{kind,label,color,lengthM,pct}], sumM, centerPct }.
 */
export function modeKindAggregates(safest, modeId) {
  const meta = islandModeMeta(modeId);
  if (!meta) return null;
  const totalM = Number(safest?.stats?.length_m) || 0;
  const chunks = safest?.[meta.typedKey] || [];
  const wanted = MODE_ARC_KINDS[modeId] || [];
  const byKind = new Map();
  chunks.forEach((c) => {
    if (!wanted.includes(c.kind)) return;
    byKind.set(c.kind, (byKind.get(c.kind) || 0) + (Number(c.length_m) || 0));
  });
  const kinds = wanted
    .filter((k) => byKind.has(k) && byKind.get(k) > 0)
    .map((k) => {
      const lengthM = byKind.get(k);
      return {
        kind: k,
        label: OVERLAY_KIND_META[k]?.label || k,
        color: OVERLAY_KIND_META[k]?.color || meta.hub,
        lengthM,
        pct: totalM > 0 ? Math.min(100, (lengthM / totalM) * 100) : 0,
      };
    });
  const sumM = kinds.reduce((acc, k) => acc + k.lengthM, 0);
  const centerPct = totalM > 0 ? Math.min(100, Math.round((sumM / totalM) * 100)) : 0;
  return { meta, totalM, kinds, sumM, centerPct };
}

/** Chunks of a mode that carry geometry (for hover highlight on the map). */
export function modeChunksFor(safest, modeId) {
  const meta = islandModeMeta(modeId);
  if (!meta) return [];
  const wanted = MODE_ARC_KINDS[modeId] || [];
  return (safest?.[meta.typedKey] || []).filter((c) => wanted.includes(c.kind));
}

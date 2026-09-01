import {
  OVERLAY_KIND_META,
  OVERLAY_MODE_META,
  TRAFFIC_OVERLAY,
} from '../../map/overlayModes';

export const MODE_ARC_KINDS: Record<string, string[]> = {
  cycle: ['segregated', 'bus_shared', 'car_shared', 'tfl'],
  green: ['park', 'river', 'sight'],
  surface: ['rough'],
  hills: ['steep'],
  light: ['lit'],
  traffic: ['traffic'],
};

export function islandModeMeta(modeId: string) {
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

export function modeKindAggregates(safest: Record<string, unknown> | null | undefined, modeId: string) {
  const meta = islandModeMeta(modeId);
  if (!meta || !safest) return null;
  const stats = (safest.stats || {}) as { length_m?: number; distance_m?: number };
  const totalM = Number(stats.length_m ?? stats.distance_m) || 0;
  const rawChunks = safest[meta.typedKey];
  const chunks = Array.isArray(rawChunks)
    ? (rawChunks as { kind?: string; length_m?: number }[])
    : [];
  const wanted = MODE_ARC_KINDS[modeId] || [];
  const byKind = new Map<string, number>();
  chunks.forEach((c) => {
    if (!c.kind || !wanted.includes(c.kind)) return;
    byKind.set(c.kind, (byKind.get(c.kind) || 0) + (Number(c.length_m) || 0));
  });
  const kinds = wanted
    .filter((k) => byKind.has(k) && (byKind.get(k) || 0) > 0)
    .map((k) => {
      const lengthM = byKind.get(k)!;
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

/** Chunks of a mode that carry geometry (for chart slices / map highlight). */
export function modeChunksFor(
  safest: Record<string, unknown> | null | undefined,
  modeId: string,
) {
  const meta = islandModeMeta(modeId);
  if (!meta || !safest) return [];
  const wanted = MODE_ARC_KINDS[modeId] || [];
  const rawChunks = safest[meta.typedKey];
  const chunks = Array.isArray(rawChunks)
    ? (rawChunks as {
      kind?: string;
      path?: number[][];
      length_m?: number;
      run_id?: string;
    }[])
    : [];
  return chunks.filter((c) => c.kind && wanted.includes(c.kind));
}

import { apiFetch } from './flaskClient';
import type { LatLon } from '../lib/coords';
import type { NavigationPayload } from '../navigation/types';

export type RouteLegStats = {
  distance_m?: number;
  duration_min?: number;
  [key: string]: unknown;
};

export type RouteVariant = {
  path?: number[][];
  stats?: RouteLegStats;
  [key: string]: unknown;
};

export type RouteResponse = {
  status?: string;
  error?: string;
  fastest?: RouteVariant;
  safest?: RouteVariant;
  /** Per-leg safest (and optional fastest) when vias are present (length = vias+1). */
  legs?: RouteLeg[];
  /** Present when `navigate=1` — Tuned Option B / OSRM-shaped steps. */
  navigation?: NavigationPayload;
  /**
   * Present when `navigate=1` — MapLibre DirectionsResponse (polyline6)
   * for native Navigation Activity `DirectionsResponse.fromJson`.
   */
  directions?: DirectionsResponsePayload;
  meta?: Record<string, unknown>;
};

/** MapLibre/Mapbox Directions API–shaped payload from Flask. */
export type DirectionsResponsePayload = {
  code?: string;
  uuid?: string;
  waypoints?: unknown[];
  routes?: unknown[];
  [key: string]: unknown;
};

export type RouteLeg = {
  index?: number;
  fastest?: RouteVariant;
  safest?: RouteVariant;
  [key: string]: unknown;
};

function encodeVias(vias?: ([number, number] | null | undefined)[]) {
  const filled = (vias || []).filter((c): c is [number, number] => Array.isArray(c) && c.length === 2);
  if (!filled.length) return '';
  return filled.map((c) => `${c[0]},${c[1]}`).join(';');
}

export async function fetchRoute(opts: {
  start: LatLon;
  end: LatLon;
  vias?: (LatLon | null)[];
  profileId?: string | null;
  bikeType?: string | null;
  departAtIso?: string | null;
  purpose?: 'prefetch' | 'commit';
  /** When true, Flask attaches Option B `navigation` (OSRM-shaped steps). */
  navigate?: boolean;
  /** Units spoken in the voice cues. Defaults to metric server-side. */
  voiceUnits?: 'metric' | 'imperial';
  /** When true, Flask also returns the length×highway baseline (`fastest`). Default off. */
  includeFastest?: boolean;
  /**
   * Places to route around for this request only (max 5). Used by the in-ride
   * "impassable" replan, which knows where the rider is but not which edge.
   */
  avoidPoints?: LatLon[];
  signal?: AbortSignal;
}): Promise<{ ok: true; data: RouteResponse } | { ok: false; error: string; status?: number }> {
  const params = new URLSearchParams({
    start_lat: String(opts.start[0]),
    start_lon: String(opts.start[1]),
    end_lat: String(opts.end[0]),
    end_lon: String(opts.end[1]),
    purpose: opts.purpose || 'commit',
  });
  if (opts.profileId) params.set('profile_id', opts.profileId);
  if (opts.bikeType) params.set('bike_type', opts.bikeType);
  const viasStr = encodeVias(opts.vias);
  if (viasStr) params.set('vias', viasStr);
  if (opts.departAtIso) params.set('depart_at', opts.departAtIso);
  if (opts.navigate) params.set('navigate', '1');
  if (opts.voiceUnits) params.set('voice_units', opts.voiceUnits);
  if (opts.includeFastest) params.set('include_fastest', '1');
  const avoidStr = encodeVias(opts.avoidPoints);
  if (avoidStr) params.set('avoid_points', avoidStr);

  const res = await apiFetch(`/route?${params}`, { signal: opts.signal });
  const data = (await res.json().catch(() => ({}))) as RouteResponse;
  if (res.status === 429) {
    return { ok: false, error: data.error || 'Too many route requests', status: 429 };
  }
  if (!res.ok || data.status !== 'success') {
    return {
      ok: false,
      error: data.error || `Route failed (${res.status})`,
      status: res.status,
    };
  }
  return { ok: true, data };
}

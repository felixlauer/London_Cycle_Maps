/**
 * Santander Cycles hire API — web App.jsx fetchHireCandidates / fetchWalkLeg.
 */
import { apiFetch } from './flaskClient';
import type { LatLon } from '../lib/coords';

export type HireNeed = 'bikes' | 'docks';

export type HireStation = {
  id: string;
  name?: string;
  lat: number;
  lon: number;
  nb_bikes?: number;
  nb_empty?: number;
  nb_docks?: number;
  nb_standard?: number;
  nb_ebikes?: number;
  temporary?: boolean;
  distance_m?: number;
  walk_estimate_min?: number;
  suitable?: boolean;
  has_bikes?: boolean;
  walk_duration_min?: number | null;
  walk_distance_m?: number | null;
};

export type HireCandidatesResponse = {
  shown?: HireStation[];
  stations?: HireStation[];
  suitable_count?: number;
  total_in_radius?: number;
  need?: HireNeed;
  radius_m?: number;
  error?: string;
};

export type WalkLegResponse = {
  path?: number[][];
  duration_s?: number;
  distance_m?: number;
  duration_min?: number;
  error?: string;
};

export async function fetchHireCandidates(
  lat: number,
  lon: number,
  need: HireNeed,
  radiusM = 1500,
): Promise<HireCandidatesResponse> {
  const params = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
    need,
    radius_m: String(radiusM),
  });
  const res = await apiFetch(`/santander/candidates?${params}`);
  const data = (await res.json().catch(() => ({}))) as HireCandidatesResponse;
  if (!res.ok || data.error) {
    throw new Error(data.error || `Candidates failed (${res.status})`);
  }
  return data;
}

export async function fetchWalkLeg(
  from: LatLon,
  to: LatLon,
): Promise<WalkLegResponse | null> {
  try {
    const res = await apiFetch('/santander/walk', {
      method: 'POST',
      body: { from, to },
    });
    const data = (await res.json().catch(() => ({}))) as WalkLegResponse;
    if (!res.ok || data.error) return null;
    return data;
  } catch {
    return null;
  }
}

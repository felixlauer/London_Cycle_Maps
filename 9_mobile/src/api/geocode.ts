/**
 * Mapbox Search Box via Flask — same contract as web mapboxGeocoding.js.
 * Token stays on the server; mobile only sends session_token + query.
 */
import { apiFetch } from './flaskClient';

export type SuggestItem = {
  mapbox_id?: string;
  name?: string;
  full_address?: string;
  place_formatted?: string;
};

export function createSessionToken() {
  // RN / Hermes: prefer crypto.randomUUID when available
  const c = globalThis.crypto as { randomUUID?: () => string } | undefined;
  if (c?.randomUUID) return c.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (ch) => {
    const r = (Math.random() * 16) | 0;
    const v = ch === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export async function suggest(query: string, sessionToken: string): Promise<SuggestItem[]> {
  if (!sessionToken) throw new Error('Session token required');
  const params = new URLSearchParams({
    q: query,
    session_token: sessionToken,
  });
  const res = await apiFetch(`/geocode/suggest?${params}`);
  const data = await res.json().catch(() => ({} as { error?: string; suggestions?: SuggestItem[] }));
  if (res.status === 429) {
    throw new Error(data.error || 'Search limit reached for this month. Try again next month.');
  }
  if (!res.ok) {
    throw new Error(data.error || `Suggest failed (${res.status})`);
  }
  return data.suggestions || [];
}

export async function retrieve(
  mapboxId: string,
  sessionToken: string,
): Promise<{ lat: number; lon: number; label: string }> {
  if (!sessionToken) throw new Error('Session token required');
  const params = new URLSearchParams({ session_token: sessionToken });
  const res = await apiFetch(`/geocode/retrieve/${encodeURIComponent(mapboxId)}?${params}`);
  const data = await res.json().catch(() => ({} as { error?: string; lat?: number; lon?: number; label?: string }));
  if (res.status === 429) {
    throw new Error(data.error || 'Search limit reached for this month. Try again next month.');
  }
  if (!res.ok) {
    throw new Error(data.error || `Retrieve failed (${res.status})`);
  }
  return {
    lat: Number(data.lat),
    lon: Number(data.lon),
    label: String(data.label || ''),
  };
}

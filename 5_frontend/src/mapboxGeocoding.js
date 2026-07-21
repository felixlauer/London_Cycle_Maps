/**
 * Mapbox Search Box helpers — requests go through Flask so the Mapbox API
 * key never appears in the browser bundle / inspector.
 */
import { API_BASE } from './api/flaskClient';

export function isGeocodingConfigured() {
  // Backend holds the key; UI assumes geocoding is available. On 503 the
  // input surfaces an error. Avoid shipping any token presence signal.
  return true;
}

/** @deprecated Use isGeocodingConfigured — token must not live in the browser. */
export function getMapboxToken() {
  return isGeocodingConfigured() ? 'server-proxied' : null;
}

export function createSessionToken() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export async function suggest(query, sessionToken) {
  if (!sessionToken) throw new Error('Session token required');
  const params = new URLSearchParams({
    q: query,
    session_token: sessionToken,
  });
  const res = await fetch(`${API_BASE}/geocode/suggest?${params}`);
  const data = await res.json().catch(() => ({}));
  if (res.status === 429) {
    throw new Error(data.error || 'Search limit reached for this month. Try again next month.');
  }
  if (!res.ok) {
    throw new Error(data.error || `Suggest failed (${res.status})`);
  }
  return data.suggestions || [];
}

export async function retrieve(mapboxId, sessionToken) {
  if (!sessionToken) throw new Error('Session token required');
  const params = new URLSearchParams({ session_token: sessionToken });
  const res = await fetch(
    `${API_BASE}/geocode/retrieve/${encodeURIComponent(mapboxId)}?${params}`
  );
  const data = await res.json().catch(() => ({}));
  if (res.status === 429) {
    throw new Error(data.error || 'Search limit reached for this month. Try again next month.');
  }
  if (!res.ok) {
    throw new Error(data.error || `Retrieve failed (${res.status})`);
  }
  return { lat: data.lat, lon: data.lon, label: data.label };
}

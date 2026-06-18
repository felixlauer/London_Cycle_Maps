/**
 * Mapbox Search Box API v1 — suggest + retrieve helpers.
 * Session tokens must be created on input focus and reused for suggest/retrieve.
 */

const SUGGEST_URL = 'https://api.mapbox.com/search/searchbox/v1/suggest';
const RETRIEVE_URL = 'https://api.mapbox.com/search/searchbox/v1/retrieve';
const LONDON_BBOX = '-0.51,51.28,0.33,51.69';

export function getMapboxToken() {
  const token = process.env.REACT_APP_MAPBOX_API_KEY;
  return token && token.trim() ? token.trim() : null;
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
  const token = getMapboxToken();
  if (!token) throw new Error('Mapbox API key not configured');
  if (!sessionToken) throw new Error('Session token required');

  const params = new URLSearchParams({
    q: query,
    session_token: sessionToken,
    access_token: token,
    limit: '5',
    language: 'en',
    types: 'address,poi,place',
    country: 'GB',
    bbox: LONDON_BBOX,
  });

  const res = await fetch(`${SUGGEST_URL}?${params}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `Suggest failed (${res.status})`);
  }
  const data = await res.json();
  return data.suggestions || [];
}

export async function retrieve(mapboxId, sessionToken) {
  const token = getMapboxToken();
  if (!token) throw new Error('Mapbox API key not configured');
  if (!sessionToken) throw new Error('Session token required');

  const params = new URLSearchParams({
    session_token: sessionToken,
    access_token: token,
  });

  const res = await fetch(`${RETRIEVE_URL}/${encodeURIComponent(mapboxId)}?${params}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `Retrieve failed (${res.status})`);
  }
  const data = await res.json();
  const feature = data.features?.[0];
  if (!feature?.geometry?.coordinates) {
    throw new Error('No coordinates in retrieve response');
  }
  const [lon, lat] = feature.geometry.coordinates;
  const label =
    feature.properties?.full_address ||
    feature.properties?.name ||
    feature.properties?.place_formatted ||
    `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
  return { lat, lon, label };
}

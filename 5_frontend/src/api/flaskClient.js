/**
 * Authenticated fetch wrapper for the Flask backend.
 *
 * Security rules (do not change):
 * - Access tokens come from sessionStore (issued by Flask /auth/*).
 * - On 401: try one refresh via Flask, then clear session and notify listeners.
 * - Test mode sends X-Tuned-Test-Mode: 1 and NO Authorization header.
 * - Secret API keys never live in the frontend bundle.
 */
import {
  getAccessToken,
  getRefreshToken,
  setSession,
  clearSession,
} from '../auth/sessionStore';

export const API_BASE = 'http://127.0.0.1:5000';

const unauthorizedListeners = new Set();
let refreshInFlight = null;

/** Subscribe to 401 events (used by AuthProvider to prompt re-login). */
export function onUnauthorized(listener) {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

async function refreshAccessToken() {
  const refresh_token = getRefreshToken();
  if (!refresh_token) return null;
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token }),
      });
      if (!res.ok) {
        clearSession();
        return null;
      }
      const data = await res.json();
      if (!data?.access_token) {
        clearSession();
        return null;
      }
      setSession(data);
      return data.access_token;
    } catch {
      clearSession();
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

/**
 * apiFetch('/profiles', { method, body, testMode })
 * body objects are JSON-encoded automatically. Returns the raw Response.
 */
export async function apiFetch(path, { method = 'GET', body, testMode = false, headers = {}, signal } = {}) {
  const finalHeaders = { ...headers };

  if (testMode) {
    finalHeaders['X-Tuned-Test-Mode'] = '1';
  } else {
    let token = getAccessToken();
    if (!token && getRefreshToken()) {
      token = await refreshAccessToken();
    }
    if (token) finalHeaders['Authorization'] = `Bearer ${token}`;
  }

  const options = { method, headers: finalHeaders };
  if (signal) options.signal = signal;
  if (body !== undefined) {
    finalHeaders['Content-Type'] = 'application/json';
    options.body = typeof body === 'string' ? body : JSON.stringify(body);
  }

  let res = await fetch(`${API_BASE}${path}`, options);

  if (res.status === 401 && !testMode && getRefreshToken()) {
    const next = await refreshAccessToken();
    if (next) {
      finalHeaders['Authorization'] = `Bearer ${next}`;
      res = await fetch(`${API_BASE}${path}`, options);
    }
  }

  if (res.status === 401 && !testMode) {
    clearSession();
    unauthorizedListeners.forEach((fn) => fn());
  }

  return res;
}

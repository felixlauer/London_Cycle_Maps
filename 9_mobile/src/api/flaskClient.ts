/**
 * Authenticated fetch wrapper for the Flask backend (mobile port of web flaskClient).
 *
 * - Access tokens from sessionStore (Flask /auth/*).
 * - On 401: one refresh via Flask, then clear session + notify.
 * - No secret API keys in the bundle.
 */
import { API_BASE } from './config';
import {
  clearSession,
  getRefreshToken,
  getSession,
  isAccessTokenExpired,
  setSession,
} from '../auth/sessionStore';

const unauthorizedListeners = new Set<() => void>();
let refreshInFlight: Promise<string | null> | null = null;

export { API_BASE };

export function onUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

async function refreshAccessToken(): Promise<string | null> {
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
        await clearSession();
        return null;
      }
      const data = await res.json();
      if (!data?.access_token) {
        await clearSession();
        return null;
      }
      await setSession(data);
      return data.access_token as string;
    } catch {
      await clearSession();
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

export async function ensureValidAccessToken({
  forceRefresh = false,
}: { forceRefresh?: boolean } = {}): Promise<string | null> {
  const session = getSession();
  if (!session) return null;

  const needsRefresh =
    forceRefresh ||
    !session.access_token ||
    isAccessTokenExpired() ||
    !session.user;

  if (!needsRefresh) return session.access_token;

  if (!session.refresh_token) {
    await clearSession();
    return null;
  }

  return refreshAccessToken();
}

type ApiFetchOptions = {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
};

export async function apiFetch(
  path: string,
  { method = 'GET', body, headers = {}, signal }: ApiFetchOptions = {},
): Promise<Response> {
  const finalHeaders: Record<string, string> = { ...headers };
  const token = await ensureValidAccessToken();
  if (token) finalHeaders.Authorization = `Bearer ${token}`;

  const options: RequestInit = { method, headers: finalHeaders, signal };
  if (body !== undefined) {
    finalHeaders['Content-Type'] = 'application/json';
    options.body = typeof body === 'string' ? body : JSON.stringify(body);
  }

  if (!API_BASE) {
    throw new Error('EXPO_PUBLIC_API_BASE is not set');
  }

  let res = await fetch(`${API_BASE}${path}`, options);

  if (res.status === 401 && getRefreshToken()) {
    const next = await refreshAccessToken();
    if (next) {
      finalHeaders.Authorization = `Bearer ${next}`;
      res = await fetch(`${API_BASE}${path}`, options);
    }
  }

  if (res.status === 401) {
    await clearSession();
    unauthorizedListeners.forEach((fn) => fn());
  }

  return res;
}

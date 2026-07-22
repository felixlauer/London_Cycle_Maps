/**
 * Browser session store for Supabase JWTs issued by Flask auth endpoints.
 *
 * Tokens live in localStorage (SPA). Secret API keys never enter this file —
 * auth goes through Flask so Mapbox / service_role / JWT secret stay server-side.
 */
const STORAGE_KEY = 'tuned_auth_session';

let memorySession = null;
const listeners = new Set();

function readStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.access_token || !parsed?.refresh_token) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeStorage(session) {
  if (!session) {
    localStorage.removeItem(STORAGE_KEY);
    return;
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function getSession() {
  if (memorySession) return memorySession;
  memorySession = readStorage();
  return memorySession;
}

export function getAccessToken() {
  return getSession()?.access_token ?? null;
}

export function getRefreshToken() {
  return getSession()?.refresh_token ?? null;
}

/** True when access token is missing or past expires_at (with skew). */
export function isAccessTokenExpired(skewSeconds = 60) {
  const session = getSession();
  if (!session?.access_token) return true;
  const exp = session.expires_at;
  if (exp == null || exp === '') return false;
  let expMs;
  if (typeof exp === 'number') {
    // Supabase uses unix seconds; tolerate ms just in case.
    expMs = exp < 1e12 ? exp * 1000 : exp;
  } else {
    const parsed = Date.parse(String(exp));
    if (!Number.isFinite(parsed)) return false;
    expMs = parsed;
  }
  return Date.now() >= expMs - skewSeconds * 1000;
}

export function setSession(session) {
  memorySession = session
    ? {
        access_token: session.access_token,
        refresh_token: session.refresh_token,
        expires_at: session.expires_at ?? null,
        expires_in: session.expires_in ?? null,
        user: session.user ?? null,
        type: session.type ?? null,
      }
    : null;
  writeStorage(memorySession);
  listeners.forEach((fn) => fn(memorySession));
}

export function clearSession() {
  setSession(null);
}

export function onSessionChange(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Parse Supabase recovery / invite redirects: #access_token=...&type=recovery */
export function consumeAuthHash() {
  const hash = window.location.hash?.replace(/^#/, '') || '';
  if (!hash) return null;
  const params = new URLSearchParams(hash);
  const access_token = params.get('access_token');
  const refresh_token = params.get('refresh_token');
  const type = params.get('type');
  if (!access_token || !refresh_token) return null;
  // Clear sensitive tokens from the address bar.
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
  return {
    access_token,
    refresh_token,
    expires_in: params.get('expires_in') ? Number(params.get('expires_in')) : null,
    type,
    user: null,
  };
}

/**
 * Session store for JWTs issued by Flask /auth/*.
 * Tokens live in expo-secure-store (not AsyncStorage plaintext).
 * No Supabase anon / service keys in the mobile bundle.
 */
import * as SecureStore from 'expo-secure-store';

const STORAGE_KEY = 'tuned_auth_session';

export type AuthUser = {
  id?: string;
  email?: string;
  display_name?: string | null;
  [key: string]: unknown;
};

export type AuthSession = {
  access_token: string;
  refresh_token: string;
  expires_at?: number | string | null;
  expires_in?: number | null;
  user?: AuthUser | null;
  type?: string | null;
};

let memorySession: AuthSession | null = null;
const listeners = new Set<(session: AuthSession | null) => void>();

function notify() {
  listeners.forEach((fn) => fn(memorySession));
}

export function getSession(): AuthSession | null {
  return memorySession;
}

export function getAccessToken(): string | null {
  return memorySession?.access_token ?? null;
}

export function getRefreshToken(): string | null {
  return memorySession?.refresh_token ?? null;
}

/** True when access token is missing or past expires_at (with skew). */
export function isAccessTokenExpired(skewSeconds = 60): boolean {
  const session = getSession();
  if (!session?.access_token) return true;
  const exp = session.expires_at;
  if (exp == null || exp === '') return false;
  let expMs: number;
  if (typeof exp === 'number') {
    expMs = exp < 1e12 ? exp * 1000 : exp;
  } else {
    const parsed = Date.parse(String(exp));
    if (!Number.isFinite(parsed)) return false;
    expMs = parsed;
  }
  return Date.now() >= expMs - skewSeconds * 1000;
}

export async function hydrateSession(): Promise<AuthSession | null> {
  try {
    const raw = await SecureStore.getItemAsync(STORAGE_KEY);
    if (!raw) {
      memorySession = null;
      return null;
    }
    const parsed = JSON.parse(raw) as AuthSession;
    if (!parsed?.access_token || !parsed?.refresh_token) {
      memorySession = null;
      return null;
    }
    memorySession = parsed;
    return memorySession;
  } catch {
    memorySession = null;
    return null;
  }
}

export async function setSession(session: AuthSession | null): Promise<void> {
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

  try {
    if (!memorySession) {
      await SecureStore.deleteItemAsync(STORAGE_KEY);
    } else {
      await SecureStore.setItemAsync(STORAGE_KEY, JSON.stringify(memorySession));
    }
  } catch {
    // SecureStore can fail on some emulator edge cases; memory still works for the session.
  }
  notify();
}

export async function clearSession(): Promise<void> {
  await setSession(null);
}

export function onSessionChange(listener: (session: AuthSession | null) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

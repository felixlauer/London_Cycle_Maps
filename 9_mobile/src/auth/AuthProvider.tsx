/**
 * Auth context — password login/signup/account via Flask (web AuthProvider parity).
 * Profile CRUD stays on Flask; no Supabase client in the app.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { API_BASE, apiFetch, ensureValidAccessToken, onUnauthorized } from '../api/flaskClient';
import {
  AuthSession,
  AuthUser,
  clearSession,
  getSession,
  hydrateSession,
  onSessionChange,
  setSession,
} from './sessionStore';

const MIN_PASSWORD_LEN = 10;

type AuthResult = {
  error: string | null;
  needsConfirm?: boolean;
  displayName?: string | null;
};

type AuthContextValue = {
  user: AuthUser | null;
  session: AuthSession | null;
  isLoading: boolean;
  authNotice: string;
  signIn: (email: string, password: string) => Promise<AuthResult>;
  signUp: (email: string, password: string, displayName?: string) => Promise<AuthResult>;
  signOut: () => Promise<void>;
  resetPassword: (email: string) => Promise<AuthResult>;
  changePassword: (
    currentPassword: string,
    newPassword: string,
    confirmPassword: string,
  ) => Promise<AuthResult>;
  updateDisplayName: (displayName: string) => Promise<AuthResult>;
  deleteAccount: (currentPassword: string) => Promise<AuthResult>;
};

const AuthContext = createContext<AuthContextValue>({
  user: null,
  session: null,
  isLoading: true,
  authNotice: '',
  signIn: async () => ({ error: 'Auth not ready' }),
  signUp: async () => ({ error: 'Auth not ready' }),
  signOut: async () => {},
  resetPassword: async () => ({ error: 'Auth not ready' }),
  changePassword: async () => ({ error: 'Auth not ready' }),
  updateDisplayName: async () => ({ error: 'Auth not ready' }),
  deleteAccount: async () => ({ error: 'Auth not ready' }),
});

async function readError(res: Response): Promise<string> {
  const data = await res.json().catch(() => ({} as { error?: string }));
  return data.error || `Request failed (${res.status})`;
}

/** Password-reset email link target — web uses window.origin; mobile uses env or API host. */
function passwordRedirectUrl() {
  const fromEnv = (process.env.EXPO_PUBLIC_AUTH_REDIRECT || '').trim();
  if (fromEnv) return fromEnv.replace(/\/$/, '');
  const base = (API_BASE || '').replace(/\/$/, '');
  if (base) return base.replace(/\/api$/i, '') || base;
  return 'https://tuned.app';
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSessionState] = useState<AuthSession | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authNotice, setAuthNotice] = useState('');

  useEffect(() => {
    let cancelled = false;
    const unsub = onSessionChange((next) => {
      if (!cancelled) setSessionState(next);
    });

    (async () => {
      try {
        await hydrateSession();
        const current = getSession();
        if (current?.refresh_token) {
          const token = await ensureValidAccessToken({ forceRefresh: true });
          if (!token && !cancelled) {
            setAuthNotice('Your session expired — please log in again.');
          }
        }
      } finally {
        if (!cancelled) {
          setSessionState(getSession());
          setIsLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      unsub();
    };
  }, []);

  useEffect(
    () =>
      onUnauthorized(() => {
        setAuthNotice('Your session expired — please log in again.');
      }),
    [],
  );

  const signIn = useCallback(async (email: string, password: string) => {
    if (!API_BASE) return { error: 'API base URL is not configured.' };
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim(), password }),
    });
    if (!res.ok) return { error: await readError(res) };
    const data = await res.json();
    await setSession(data);
    setAuthNotice('');
    return { error: null };
  }, []);

  const signUp = useCallback(async (email: string, password: string, displayName = '') => {
    if (!API_BASE) return { error: 'API base URL is not configured.' };
    if (password.length < MIN_PASSWORD_LEN) {
      return { error: `Password must be at least ${MIN_PASSWORD_LEN} characters.` };
    }
    const res = await fetch(`${API_BASE}/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email.trim(),
        password,
        display_name: String(displayName || '').trim(),
      }),
    });
    if (!res.ok) return { error: await readError(res) };
    const data = await res.json();
    if (data.session) await setSession(data.session);
    return { error: null, needsConfirm: !!data.needs_confirm && !data.session };
  }, []);

  const signOut = useCallback(async () => {
    await clearSession();
    setAuthNotice('');
  }, []);

  const resetPassword = useCallback(async (email: string) => {
    if (!API_BASE) return { error: 'API base URL is not configured.' };
    const res = await fetch(`${API_BASE}/auth/password-reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email.trim(),
        redirect_to: passwordRedirectUrl(),
      }),
    });
    if (!res.ok) return { error: await readError(res) };
    return { error: null };
  }, []);

  const changePassword = useCallback(async (
    currentPassword: string,
    newPassword: string,
    confirmPassword: string,
  ) => {
    if (newPassword.length < MIN_PASSWORD_LEN) {
      return { error: `Password must be at least ${MIN_PASSWORD_LEN} characters.` };
    }
    if (newPassword !== confirmPassword) {
      return { error: 'New passwords do not match.' };
    }
    if (currentPassword === newPassword) {
      return { error: 'New password must be different from your current password.' };
    }
    const res = await apiFetch('/auth/change-password', {
      method: 'POST',
      body: {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      },
    });
    if (!res.ok) return { error: await readError(res) };
    return { error: null };
  }, []);

  const updateDisplayName = useCallback(async (displayName: string) => {
    const trimmed = String(displayName || '').trim();
    if (trimmed.length > 80) {
      return { error: 'Name must be at most 80 characters.' };
    }
    const res = await apiFetch('/auth/account', {
      method: 'PATCH',
      body: { display_name: trimmed },
    });
    if (!res.ok) return { error: await readError(res) };
    const data = await res.json().catch(() => ({} as { display_name?: string | null }));
    const current = getSession();
    if (current?.user) {
      await setSession({
        ...current,
        user: {
          ...current.user,
          display_name: data.display_name ?? null,
        },
      });
    }
    return { error: null, displayName: data.display_name ?? null };
  }, []);

  const deleteAccount = useCallback(async (currentPassword: string) => {
    const email = getSession()?.user?.email;
    if (!email) return { error: 'Not signed in.' };
    if (!API_BASE) return { error: 'API base URL is not configured.' };
    const verify = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password: currentPassword }),
    });
    if (!verify.ok) return { error: 'Password is incorrect.' };
    const data = await verify.json();
    await setSession(data);
    const res = await apiFetch('/auth/account', { method: 'DELETE' });
    if (!res.ok) return { error: await readError(res) };
    await clearSession();
    return { error: null };
  }, []);

  const value = useMemo(
    () => ({
      user: session?.user ?? null,
      session,
      isLoading,
      authNotice,
      signIn,
      signUp,
      signOut,
      resetPassword,
      changePassword,
      updateDisplayName,
      deleteAccount,
    }),
    [
      session, isLoading, authNotice, signIn, signUp, signOut,
      resetPassword, changePassword, updateDisplayName, deleteAccount,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

/** Authenticated helper used by home screen. */
export { apiFetch };

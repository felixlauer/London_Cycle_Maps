/**
 * Supabase session context. AUTH ONLY — profile CRUD goes through Flask.
 *
 * Password login / signup / reset / change go through rate-limited Flask
 * endpoints so brute-force attempts are blocked server-side. Tokens are
 * stored via sessionStore; no Supabase anon key is shipped in the bundle.
 *
 * Consumers (TopBar / ProfileMenu) must render a neutral placeholder while
 * isLoading — never the "Guest" state — to avoid the flash-of-Guest on load.
 */
import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { apiFetch, API_BASE, onUnauthorized, ensureValidAccessToken } from '../api/flaskClient';
import {
  getSession,
  setSession,
  clearSession,
  onSessionChange,
  consumeAuthHash,
} from './sessionStore';

const MIN_PASSWORD_LEN = 6;

const AuthContext = createContext({
  user: null,
  session: null,
  isLoading: true,
  isConfigured: true,
  passwordRecoveryPending: false,
  authNotice: '',
  signIn: async () => ({ error: 'Auth not ready' }),
  signUp: async () => ({ error: 'Auth not ready' }),
  signOut: async () => {},
  resetPassword: async () => ({ error: 'Auth not ready' }),
  completePasswordRecovery: async () => ({ error: 'Auth not ready' }),
  changePassword: async () => ({ error: 'Auth not ready' }),
  updateDisplayName: async () => ({ error: 'Auth not ready' }),
  deleteAccount: async () => ({ error: 'Auth not ready' }),
});

function passwordRedirectUrl() {
  return `${window.location.origin}${window.location.pathname}`;
}

async function readError(res) {
  const data = await res.json().catch(() => ({}));
  return data.error || `Request failed (${res.status})`;
}

export function AuthProvider({ children }) {
  const [session, setSessionState] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authNotice, setAuthNotice] = useState('');
  const [passwordRecoveryPending, setPasswordRecoveryPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const unsub = onSessionChange((next) => {
      if (!cancelled) setSessionState(next);
    });

    (async () => {
      try {
        const fromHash = consumeAuthHash();
        if (fromHash) {
          setSession(fromHash);
          if (fromHash.type === 'recovery') {
            setPasswordRecoveryPending(true);
          }
        } else {
          const existing = getSession();
          if (existing) setSession(existing);
        }

        const current = getSession();
        // Returning devices often still have a cached user blob after the
        // access token expired. Refresh (or clear) before revealing signed-in UI.
        if (current?.refresh_token && current.type !== 'recovery') {
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

  useEffect(() => onUnauthorized(() => {
    setAuthNotice('Your session expired — please log in again.');
    setPasswordRecoveryPending(false);
  }), []);

  const signIn = useCallback(async (email, password) => {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim(), password }),
    });
    if (!res.ok) return { error: await readError(res) };
    const data = await res.json();
    setSession(data);
    setAuthNotice('');
    return { error: null };
  }, []);

  const signUp = useCallback(async (email, password, displayName = '') => {
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
    if (data.session) setSession(data.session);
    return { error: null, needsConfirm: !!data.needs_confirm && !data.session };
  }, []);

  const signOut = useCallback(async () => {
    setPasswordRecoveryPending(false);
    clearSession();
  }, []);

  const resetPassword = useCallback(async (email) => {
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

  const completePasswordRecovery = useCallback(async (newPassword, confirmPassword) => {
    if (newPassword.length < MIN_PASSWORD_LEN) {
      return { error: `Password must be at least ${MIN_PASSWORD_LEN} characters.` };
    }
    if (newPassword !== confirmPassword) {
      return { error: 'Passwords do not match.' };
    }
    const res = await apiFetch('/auth/set-password', {
      method: 'POST',
      body: { new_password: newPassword, confirm_password: confirmPassword },
    });
    if (!res.ok) return { error: await readError(res) };
    setPasswordRecoveryPending(false);
    setAuthNotice('');
    return { error: null };
  }, []);

  const changePassword = useCallback(async (currentPassword, newPassword, confirmPassword) => {
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

  const updateDisplayName = useCallback(async (displayName) => {
    const trimmed = String(displayName || '').trim();
    if (trimmed.length > 80) {
      return { error: 'Name must be at most 80 characters.' };
    }
    const res = await apiFetch('/auth/account', {
      method: 'PATCH',
      body: { display_name: trimmed },
    });
    if (!res.ok) return { error: await readError(res) };
    const data = await res.json().catch(() => ({}));
    const current = getSession();
    if (current?.user) {
      setSession({
        ...current,
        user: {
          ...current.user,
          display_name: data.display_name ?? null,
        },
      });
    }
    return { error: null, displayName: data.display_name ?? null };
  }, []);

  const deleteAccount = useCallback(async (currentPassword) => {
    // Re-verify password via change-password style login check first.
    const email = getSession()?.user?.email;
    if (!email) return { error: 'Not signed in.' };
    const verify = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password: currentPassword }),
    });
    if (!verify.ok) return { error: 'Password is incorrect.' };
    const data = await verify.json();
    setSession(data); // keep a fresh token for the delete call
    const res = await apiFetch('/auth/account', { method: 'DELETE' });
    if (!res.ok) return { error: await readError(res) };
    setPasswordRecoveryPending(false);
    clearSession();
    return { error: null };
  }, []);

  const value = {
    user: session?.user ?? null,
    session,
    isLoading,
    isConfigured: true,
    passwordRecoveryPending,
    authNotice,
    signIn,
    signUp,
    signOut,
    resetPassword,
    completePasswordRecovery,
    changePassword,
    updateDisplayName,
    deleteAccount,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}

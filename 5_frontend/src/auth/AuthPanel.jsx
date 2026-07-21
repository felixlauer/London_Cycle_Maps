/**
 * Reusable auth form — modal overlay or inline sidebar panel.
 * Resets credentials on every dismiss path.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useAuth } from './AuthProvider';
import './auth.css';

const TABS = [
  { id: 'login', label: 'Log in' },
  { id: 'signup', label: 'Sign up' },
  { id: 'reset', label: 'Forgot password' },
];

const INITIAL_FORM = {
  email: '',
  password: '',
  error: '',
  notice: '',
  busy: false,
};

export default function AuthPanel({
  variant = 'modal',
  themeMode,
  initialTab = 'login',
  visible = true,
  onClose,
}) {
  const { signIn, signUp, resetPassword } = useAuth();
  const [tab, setTab] = useState(initialTab);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const resetForm = useCallback(() => {
    setTab(initialTab);
    setEmail(INITIAL_FORM.email);
    setPassword(INITIAL_FORM.password);
    setError(INITIAL_FORM.error);
    setNotice(INITIAL_FORM.notice);
    setBusy(INITIAL_FORM.busy);
  }, [initialTab]);

  const handleDismiss = useCallback(() => {
    resetForm();
    onClose?.();
  }, [onClose, resetForm]);

  useEffect(() => {
    if (!visible) resetForm();
  }, [visible, resetForm]);

  useEffect(() => () => resetForm(), [resetForm]);

  useEffect(() => {
    setTab(initialTab);
  }, [initialTab]);

  const switchTab = (id) => {
    setTab(id);
    setError('');
    setNotice('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setNotice('');
    setBusy(true);
    try {
      if (tab === 'login') {
        const { error: err } = await signIn(email.trim(), password);
        if (err) setError(err);
        else handleDismiss();
      } else if (tab === 'signup') {
        const { error: err, needsConfirm } = await signUp(email.trim(), password);
        if (err) setError(err);
        else if (needsConfirm) setNotice('Check your inbox to confirm your email, then log in.');
        else handleDismiss();
      } else {
        const { error: err } = await resetPassword(email.trim());
        if (err) setError(err);
        else setNotice('Password reset email sent — check your inbox.');
      }
    } finally {
      setBusy(false);
    }
  };

  const submitLabel = tab === 'login' ? 'Log in' : tab === 'signup' ? 'Create account' : 'Send reset link';
  const heading = tab === 'login' ? 'Log in' : tab === 'signup' ? 'Sign up' : 'Reset password';
  const isInline = variant === 'inline';

  const form = (
    <div
      className={isInline ? 'auth-modal auth-panel--inline' : 'auth-modal'}
      data-theme={themeMode}
    >
      <div className="auth-modal__header">
        <span className="auth-modal__brand">{heading}</span>
        {isInline ? (
          <button type="button" className="auth-modal__close" onClick={handleDismiss}>
            Cancel
          </button>
        ) : (
          <button type="button" className="auth-modal__close" onClick={handleDismiss} aria-label="Close">
            ✕
          </button>
        )}
      </div>

      <div className="auth-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={`auth-tab${tab === t.id ? ' active' : ''}`}
            onClick={() => switchTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="auth-field">
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            required
          />
        </label>

        {tab !== 'reset' && (
          <label className="auth-field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={tab === 'signup' ? 'At least 6 characters' : 'Your password'}
              autoComplete={tab === 'signup' ? 'new-password' : 'current-password'}
              minLength={6}
              required
            />
          </label>
        )}

        {error && <div className="auth-message error">{error}</div>}
        {notice && <div className="auth-message notice">{notice}</div>}

        <button type="submit" className="auth-submit" disabled={busy}>
          {busy ? 'Please wait…' : submitLabel}
        </button>

        {tab === 'login' && (
          <button type="button" className="auth-link" onClick={() => switchTab('reset')}>
            Forgot your password?
          </button>
        )}
      </form>
    </div>
  );

  if (isInline) return form;

  return (
    <div
      className="auth-overlay"
      onMouseDown={(e) => { if (e.target === e.currentTarget) handleDismiss(); }}
    >
      {form}
    </div>
  );
}

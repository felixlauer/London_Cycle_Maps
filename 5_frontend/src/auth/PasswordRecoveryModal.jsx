/**
 * Mandatory overlay after a password-reset link — user must set a new password
 * before using the app. Cannot be dismissed until updateUser succeeds.
 */
import React, { useState } from 'react';
import { useAuth } from './AuthProvider';
import './auth.css';

export default function PasswordRecoveryModal({ themeMode }) {
  const { user, completePasswordRecovery } = useAuth();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const { error: err } = await completePasswordRecovery(password, confirm);
      if (err) setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-overlay auth-overlay--blocking">
      <div className="auth-modal auth-modal--recovery" data-theme={themeMode}>
        <div className="auth-modal__header">
          <span className="auth-modal__brand">Set a new password</span>
        </div>

        <p className="auth-recovery__intro">
          {user?.email
            ? <>Choose a new password for <strong>{user.email}</strong>.</>
            : 'Choose a new password to finish resetting your account.'}
        </p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="auth-field">
            <span>New password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              minLength={6}
              required
            />
          </label>

          <label className="auth-field">
            <span>Confirm new password</span>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              minLength={6}
              required
            />
          </label>

          {error && <div className="auth-message error">{error}</div>}

          <button type="submit" className="auth-submit" disabled={busy}>
            {busy ? 'Saving…' : 'Save new password'}
          </button>
        </form>
      </div>
    </div>
  );
}

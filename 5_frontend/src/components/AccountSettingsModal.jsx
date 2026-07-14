/**
 * Account settings: change password (verify current) and GDPR account deletion.
 * Rendered at App root (not inside the top bar) so fixed overlay centers on viewport.
 */
import React, { useState } from 'react';
import { useAuth } from '../auth/AuthProvider';
import '../auth/auth.css';

export default function AccountSettingsModal({ onClose, themeMode }) {
  const { user, changePassword, deleteAccount } = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setError('');
    setNotice('');
    setBusy(true);
    try {
      const { error: err } = await changePassword(currentPassword, newPassword, confirmPassword);
      if (err) setError(err);
      else {
        setNotice('Password updated.');
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
      }
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteAccount = async () => {
    setError('');
    setNotice('');
    if (!deleteConfirm) {
      setError('Please confirm you want to permanently delete your account.');
      return;
    }
    setBusy(true);
    try {
      const { error: err } = await deleteAccount(deletePassword);
      if (err) setError(err);
      else onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="auth-modal auth-modal--wide" data-theme={themeMode}>
        <div className="auth-modal__header">
          <span className="auth-modal__brand">Account settings</span>
          <button type="button" className="auth-modal__close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <p className="auth-settings__signed-in">
          Signed in as <strong>{user?.email}</strong>
        </p>

        <section className="auth-settings__section">
          <h5 className="auth-settings__title">Change password</h5>
          <form className="auth-form" onSubmit={handleChangePassword}>
            <label className="auth-field">
              <span>Current password</span>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <label className="auth-field">
              <span>New password</span>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                minLength={6}
                required
              />
            </label>
            <label className="auth-field">
              <span>Confirm new password</span>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                minLength={6}
                required
              />
            </label>
            <button type="submit" className="auth-submit" disabled={busy}>
              Update password
            </button>
          </form>
        </section>

        <section className="auth-settings__section auth-settings__section--danger">
          <h5 className="auth-settings__title">Delete account</h5>
          <p className="auth-settings__hint">
            Permanently deletes your account and all custom routing profiles. This cannot be undone.
            System presets remain available to other users.
          </p>
          <label className="auth-field">
            <span>Confirm with your password</span>
            <input
              type="password"
              value={deletePassword}
              onChange={(e) => setDeletePassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          <label className="auth-settings__confirm">
            <input
              type="checkbox"
              checked={deleteConfirm}
              onChange={(e) => setDeleteConfirm(e.target.checked)}
            />
            <span>I understand this will permanently delete my account and data.</span>
          </label>
          <button
            type="button"
            className="auth-submit auth-submit--danger"
            disabled={busy}
            onClick={handleDeleteAccount}
          >
            Delete my account
          </button>
        </section>

        {error && <div className="auth-message error">{error}</div>}
        {notice && <div className="auth-message notice">{notice}</div>}
      </div>
    </div>
  );
}

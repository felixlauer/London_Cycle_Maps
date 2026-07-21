import React, { useState } from 'react';
import { ChevronDown, KeyRound, Trash2 } from 'lucide-react';
import { useAuth } from '../../../auth/AuthProvider';

/**
 * Account section — same card language as routing waypoints (rc-wpcard).
 */
export default function AccountManageSection() {
  const { user, changePassword, deleteAccount } = useAuth();
  const [openPwd, setOpenPwd] = useState(false);
  const [openDel, setOpenDel] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  if (!user) return null;

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
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="sb-section" aria-labelledby="sb-account-heading">
      <h2 id="sb-account-heading" className="sb-section__title">Account</h2>
      <div className="sb-card sb-card--actions">
        <button
          type="button"
          className={`sb-card__row${openPwd ? ' is-open' : ''}`}
          aria-expanded={openPwd}
          onClick={() => { setOpenPwd((v) => !v); setOpenDel(false); }}
        >
          <span className="sb-card__icon" aria-hidden>
            <KeyRound size={16} strokeWidth={2.2} />
          </span>
          <span className="sb-card__label">Change password</span>
          <span className="sb-card__chevron" aria-hidden>
            <ChevronDown size={14} strokeWidth={2} />
          </span>
        </button>
        {openPwd && (
          <form className="sb-card__panel" onSubmit={handleChangePassword}>
            <label className="sb-field">
              <span>Current password</span>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <label className="sb-field">
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
            <label className="sb-field">
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
            <button type="submit" className="sb-btn" disabled={busy}>
              Update password
            </button>
          </form>
        )}

        <div className="sb-card__divider" aria-hidden />

        <button
          type="button"
          className={`sb-card__row${openDel ? ' is-open' : ''}`}
          aria-expanded={openDel}
          onClick={() => { setOpenDel((v) => !v); setOpenPwd(false); }}
        >
          <span className="sb-card__icon" aria-hidden>
            <Trash2 size={16} strokeWidth={2.2} />
          </span>
          <span className="sb-card__label">Delete account</span>
          <span className="sb-card__chevron" aria-hidden>
            <ChevronDown size={14} strokeWidth={2} />
          </span>
        </button>
        {openDel && (
          <div className="sb-card__panel">
            <p className="sb-form__hint">
              Permanently deletes your account and custom profiles. This cannot be undone.
            </p>
            <label className="sb-field">
              <span>Confirm with your password</span>
              <input
                type="password"
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                autoComplete="current-password"
              />
            </label>
            <label className="sb-check">
              <input
                type="checkbox"
                checked={deleteConfirm}
                onChange={(e) => setDeleteConfirm(e.target.checked)}
              />
              <span>I understand this permanently deletes my account.</span>
            </label>
            <button
              type="button"
              className="sb-btn"
              disabled={busy}
              onClick={handleDeleteAccount}
            >
              Delete my account
            </button>
          </div>
        )}
      </div>

      {error && <div className="sb-message sb-message--error">{error}</div>}
      {notice && <div className="sb-message sb-message--notice">{notice}</div>}
    </section>
  );
}

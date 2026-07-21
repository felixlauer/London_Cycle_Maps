/**
 * Profile avatar trigger + dropdown (top bar).
 *
 * Render states (no flash-of-Guest — see AuthProvider.isLoading):
 * - isLoading:  disabled skeleton placeholder, same footprint, no "Guest" label
 * - test mode:  "Local dev" — all local profiles, wizard enabled, no auth items
 * - guest:      system presets only, wizard disabled ("Log in to create..."), Log in
 * - logged in:  initials avatar, system + custom profiles, wizard, Settings, Sign out
 */
import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthProvider';
import './topbar.css';

const initialsOf = (email) => (email ? email.slice(0, 2).toUpperCase() : '?');

export default function ProfileMenu({
  profiles,
  activeProfileId,
  onSelectProfile,
  onCreateProfile,
  onOpenAuth,
  onOpenSettings,
  testMode,
}) {
  const { user, isLoading, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  // Session check in flight: neutral disabled placeholder, never "Guest".
  if (isLoading && !testMode) {
    return (
      <button type="button" className="profile-trigger skeleton" disabled aria-label="Loading account">
        <span className="profile-trigger__avatar guest" />
        <span className="profile-trigger__label" />
      </button>
    );
  }

  const loggedIn = !testMode && !!user;
  const systemProfiles = profiles.filter((p) => p.is_system !== false);
  const customProfiles = profiles.filter((p) => p.is_system === false);

  const avatarClass = testMode ? 'dev' : loggedIn ? '' : 'guest';
  const triggerLabel = testMode ? 'Local dev' : loggedIn ? user.email : 'Guest';
  const avatarContent = testMode ? 'DEV' : loggedIn ? initialsOf(user.email) : '☺';

  const selectAndClose = (id) => {
    onSelectProfile(id);
    setOpen(false);
  };

  const profileSection = (title) => (
    <div className="profile-menu__section">
      <span>{title}</span>
      <span className="profile-menu__section-bike">Bike type</span>
    </div>
  );

  const renderProfileItem = (p) => (
    <button
      key={p.id}
      type="button"
      className={`profile-menu__item${p.id === activeProfileId ? ' active' : ''}`}
      onClick={() => selectAndClose(p.id)}
    >
      <span className="profile-menu__radio" />
      <span className="profile-menu__item-label">{p.name}</span>
      {p.bike_type && <span className="profile-menu__item-meta">{p.bike_type}</span>}
    </button>
  );

  return (
    <div ref={rootRef} style={{ position: 'relative' }}>
      <button type="button" className="profile-trigger" onClick={() => setOpen((v) => !v)}>
        <span className={`profile-trigger__avatar ${avatarClass}`}>{avatarContent}</span>
        <span className="profile-trigger__label">{triggerLabel}</span>
        <span className="profile-trigger__caret">▾</span>
      </button>

      {open && (
        <div className="profile-menu">
          <div className="profile-menu__header">
            <span className={`profile-menu__header-avatar ${avatarClass}`}>{avatarContent}</span>
            <div className="profile-menu__header-text">
              <div className="profile-menu__header-title">
                {testMode ? 'Local dev' : loggedIn ? user.email : 'Guest'}
              </div>
              <div className="profile-menu__header-sub">
                {testMode
                  ? 'Test mode — local profiles, no Supabase'
                  : loggedIn ? 'Signed in' : 'Not signed in'}
              </div>
            </div>
          </div>

          {testMode ? (
            <>
              {profileSection('Local profiles')}
              {profiles.map(renderProfileItem)}
              <div className="profile-menu__divider" />
              <button
                type="button"
                className="profile-menu__item"
                onClick={() => { setOpen(false); onCreateProfile(); }}
              >
                <span className="profile-menu__item-label">＋ Create Profile</span>
              </button>
            </>
          ) : (
            <>
              {profileSection('Riding styles')}
              {systemProfiles.map(renderProfileItem)}

              {loggedIn && (
                <>
                  {profileSection('My profiles')}
                  {customProfiles.length > 0
                    ? customProfiles.map(renderProfileItem)
                    : <div className="profile-menu__empty">No custom profiles yet.</div>}
                </>
              )}

              <div className="profile-menu__divider" />

              {loggedIn ? (
                <>
                  <button
                    type="button"
                    className="profile-menu__item"
                    onClick={() => { setOpen(false); onCreateProfile(); }}
                  >
                    <span className="profile-menu__item-label">＋ Create Profile</span>
                  </button>
                  <button
                    type="button"
                    className="profile-menu__item"
                    onClick={() => { setOpen(false); onOpenSettings(); }}
                  >
                    <span className="profile-menu__item-label">Settings</span>
                  </button>
                  <button
                    type="button"
                    className="profile-menu__item"
                    onClick={async () => { setOpen(false); await signOut(); }}
                  >
                    <span className="profile-menu__item-label">Sign out</span>
                  </button>
                </>
              ) : (
                <>
                  <button type="button" className="profile-menu__item" disabled>
                    <span className="profile-menu__item-label">Log in to create custom profiles</span>
                  </button>
                  <button
                    type="button"
                    className="profile-menu__item"
                    onClick={() => { setOpen(false); onOpenAuth(); }}
                  >
                    <span className="profile-menu__item-label">Log in / Sign up</span>
                  </button>
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

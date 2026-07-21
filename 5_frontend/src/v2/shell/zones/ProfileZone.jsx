import React from 'react';
import logoUrl from '../../assets/logo_transparent_bg_noshadow.svg';
import { useAuth } from '../../../auth/AuthProvider';
import { useSidebar } from '../SidebarContext';
import {
  avatarStyleForEmail,
  initialsFromEmail,
} from '../avatar';

/**
 * Top-right brand/profile pill.
 * Closed: avatar + logo. Open: expands left; logo stays pinned to the right edge.
 */
export default function ProfileZone() {
  const { user, isLoading, signOut } = useAuth();
  const { open, toggleSidebar, openAuthPanel } = useSidebar();

  const initials = initialsFromEmail(user?.email);
  const avatarStyle = user ? avatarStyleForEmail(user.email) : undefined;

  const handleAuthLink = (e) => {
    e.stopPropagation();
    if (user) signOut();
    else openAuthPanel('login');
  };

  return (
    <section
      className={`shell-zone shell-zone--profile${open ? ' is-sidebar-open' : ''}`}
      aria-label="Profile and brand"
      data-zone="profile"
    >
      <div className="profile-pill__main">
        <button
          type="button"
          className={[
            'profile-pill__slot',
            'profile-pill__slot--avatar',
            user ? 'is-signed-in' : 'is-guest',
            isLoading ? 'is-loading' : '',
          ].filter(Boolean).join(' ')}
          style={avatarStyle}
          aria-label={open ? 'Close profile sidebar' : 'Open profile sidebar'}
          aria-expanded={open}
          onClick={toggleSidebar}
        >
          {!isLoading && (
            <span
              className={`profile-pill__initials${user ? '' : ' is-guest-label'}`}
              aria-hidden
            >
              {user ? initials : 'Guest'}
            </span>
          )}
        </button>

        <div className="profile-pill__identity" aria-hidden={!open}>
          {isLoading ? (
            <span className="profile-pill__email">…</span>
          ) : (
            <span className="profile-pill__email" title={user?.email || undefined}>
              {user ? user.email : 'Not signed in'}
            </span>
          )}
          {!isLoading && (
            <button
              type="button"
              className="profile-pill__auth-link"
              onClick={handleAuthLink}
            >
              {user ? 'Log out' : 'Sign in'}
            </button>
          )}
        </div>
      </div>

      <div className="profile-pill__slot profile-pill__slot--logo" aria-hidden>
        <img
          src={logoUrl}
          alt=""
          className="profile-pill__logo"
          draggable={false}
        />
      </div>
    </section>
  );
}

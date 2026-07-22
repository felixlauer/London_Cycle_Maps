import React from 'react';
import { X } from 'lucide-react';
import logoUrl from '../../assets/logo_transparent_bg_noshadow.svg';
import { useAuth } from '../../../auth/AuthProvider';
import { useSidebar } from '../SidebarContext';
import { useIsMobile } from '../../hooks/useMediaQuery';
import {
  avatarStyleForEmail,
  initialsFromUser,
} from '../avatar';

/**
 * Top-right brand/profile pill.
 * Closed: avatar + logo. Open: expands left; logo stays pinned to the right edge.
 * Mobile open: single wizard-style X to the left of the pill.
 */
export default function ProfileZone() {
  const { user, isLoading, signOut } = useAuth();
  const {
    open,
    view,
    toggleSidebar,
    openAuthPanel,
    closeSidebar,
    closeWizard,
    closeAuthPanel,
  } = useSidebar();
  const isMobile = useIsMobile();

  const initials = initialsFromUser(user);
  const avatarStyle = user ? avatarStyleForEmail(user.email) : undefined;

  const handleAuthLink = (e) => {
    e.stopPropagation();
    if (user) signOut();
    else openAuthPanel('login');
  };

  const handleCloseX = () => {
    if (view === 'wizard') closeWizard();
    else if (view === 'auth') closeAuthPanel();
    else closeSidebar();
  };

  const closeLabel = view === 'wizard'
    ? 'Return to profiles'
    : view === 'auth'
      ? 'Close sign in'
      : 'Close sidebar';

  return (
    <section
      className={`shell-zone shell-zone--profile${open ? ' is-sidebar-open' : ''}${isMobile && open ? ' is-mobile-open' : ''}`}
      aria-label="Profile and brand"
      data-zone="profile"
    >
      {isMobile && open && (
        <button
          type="button"
          className="profile-pill__close-x"
          aria-label={closeLabel}
          onClick={handleCloseX}
        >
          <X size={18} strokeWidth={2.2} aria-hidden />
        </button>
      )}

      <div className="profile-pill__chrome">
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
              <span
                className="profile-pill__email"
                title={user?.email || undefined}
              >
                {user
                  ? (user.display_name || user.email)
                  : 'Not signed in'}
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
      </div>
    </section>
  );
}

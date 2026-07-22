import React from 'react';
import { useAuth } from '../../../auth/AuthProvider';

/**
 * Compact identity strip under the profile pill.
 */
export default function AccountStrip({ onSignIn, onSignUp }) {
  const { user, isLoading, signOut } = useAuth();

  if (isLoading) {
    return (
      <div className="sb-account sb-account--loading" aria-busy="true">
        <div className="sb-skeleton sb-skeleton--line" />
        <div className="sb-skeleton sb-skeleton--btn" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="sb-account">
        <p className="sb-account__status">Not signed in</p>
        <div className="sb-account__actions">
          <button type="button" className="sb-btn sb-btn--primary" onClick={onSignIn}>
            Sign in
          </button>
          <button type="button" className="sb-btn sb-btn--ghost" onClick={onSignUp}>
            Sign up
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="sb-account">
      {user.display_name ? (
        <p className="sb-account__name" title={user.display_name}>{user.display_name}</p>
      ) : null}
      <p className="sb-account__email" title={user.email}>{user.email}</p>
      <div className="sb-account__actions">
        <button type="button" className="sb-btn sb-btn--ghost" onClick={() => signOut()}>
          Sign out
        </button>
      </div>
    </div>
  );
}

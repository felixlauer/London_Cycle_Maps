/**
 * Email/password auth modal — thin wrapper around AuthPanel.
 */
import React from 'react';
import AuthPanel from './AuthPanel';

export default function AuthModal({ onClose, themeMode, initialTab = 'login' }) {
  return (
    <AuthPanel
      variant="modal"
      themeMode={themeMode}
      initialTab={initialTab}
      visible
      onClose={onClose}
    />
  );
}

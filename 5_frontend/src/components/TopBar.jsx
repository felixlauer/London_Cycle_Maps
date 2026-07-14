/**
 * Application top bar: brand, status line, ProfileMenu, Test Mode master toggle.
 * Test Mode ON = frontend ignores Supabase auth and Flask uses the local JSON
 * store (X-Tuned-Test-Mode header, localhost-only bypass).
 */
import React from 'react';
import ProfileMenu from './ProfileMenu';
import './topbar.css';

export default function TopBar({
  status,
  testMode,
  setTestMode,
  profiles,
  activeProfileId,
  onSelectProfile,
  onCreateProfile,
  onOpenAuth,
  onOpenSettings,
}) {
  return (
    <div className="topbar">
      <div className="topbar__left">
        <span className="topbar__brand">Tuned Cycling</span>
        <span className="topbar__status">| {status}</span>
      </div>
      <div className="topbar__right">
        <ProfileMenu
          profiles={profiles}
          activeProfileId={activeProfileId}
          onSelectProfile={onSelectProfile}
          onCreateProfile={onCreateProfile}
          onOpenAuth={onOpenAuth}
          onOpenSettings={onOpenSettings}
          testMode={testMode}
        />
        <div
          className={`topbar-testmode${testMode ? ' on' : ''}`}
          onClick={() => setTestMode(!testMode)}
          role="switch"
          aria-checked={testMode}
        >
          <span className="topbar-testmode__label">Test Mode</span>
          <div className="topbar-testmode__track">
            <div className="topbar-testmode__knob" />
          </div>
        </div>
      </div>
    </div>
  );
}

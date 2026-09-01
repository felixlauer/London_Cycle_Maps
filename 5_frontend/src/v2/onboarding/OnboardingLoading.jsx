import React from 'react';
import { TriangleAlert } from 'lucide-react';
import logoUrl from '../assets/logo_transparent_bg_noshadow.svg';
import { useOnboarding } from './OnboardingContext';

const DEFAULT_SUB = "Let's find a smarter way to ride your routes";
const MAINTENANCE_LINE_1 = 'Server is currently undergoing maintenance';
const MAINTENANCE_LINE_2 = '(expected duration: 5 minutes)';

/**
 * Boot splash — pulsing TUNE logo while auth / map / profiles / backend warm up.
 */
export default function OnboardingLoading() {
  const {
    isFirstTimer,
    onboardingTheme,
    bootExiting,
    user,
    displayName,
    showMaintenanceHint,
  } = useOnboarding();

  const name = displayName
    || user?.display_name
    || (user?.email ? String(user.email).split('@')[0] : '');

  const showNamedWelcome = !isFirstTimer && user && name;

  return (
    <div
      className={`onb-screen onb-screen--boot${bootExiting ? ' is-exiting' : ''}`}
      data-theme={onboardingTheme}
      role="status"
      aria-live="polite"
      aria-busy={!bootExiting}
    >
      <div className="onb-boot__stack">
        <div className="onb-boot__logo-wrap">
          <img className="onb-boot__logo" src={logoUrl} alt="" draggable={false} />
        </div>
        <h1 className="onb-boot__title">
          {showNamedWelcome ? (
            <>
              Welcome back,
              {' '}
              <span className="onb-boot__name">{name}</span>
            </>
          ) : (!isFirstTimer && user) ? (
            'Welcome back!'
          ) : (
            'Welcome to TUNE'
          )}
        </h1>
        {showMaintenanceHint ? (
          <p className="onb-boot__sub onb-boot__sub--maint">
            <span className="onb-boot__maint-copy">
              {MAINTENANCE_LINE_1}
              <br />
              {MAINTENANCE_LINE_2}
            </span>
            <TriangleAlert className="onb-boot__maint-icon" size={18} strokeWidth={2.2} aria-hidden />
          </p>
        ) : (
          <p className="onb-boot__sub">{DEFAULT_SUB}</p>
        )}
      </div>
    </div>
  );
}

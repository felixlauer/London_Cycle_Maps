import React from 'react';
import logoUrl from '../assets/logo_transparent_bg_noshadow.svg';
import { useOnboarding } from './OnboardingContext';

/**
 * Boot splash — pulsing TUNE logo while auth / map / profiles warm up.
 */
export default function OnboardingLoading() {
  const {
    isFirstTimer,
    onboardingTheme,
    bootExiting,
    user,
    displayName,
  } = useOnboarding();

  const name = displayName
    || user?.display_name
    || (user?.email ? String(user.email).split('@')[0] : '');

  const sub = "Let's find a smarter way to ride your routes";
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
        <p className="onb-boot__sub">{sub}</p>
      </div>
    </div>
  );
}

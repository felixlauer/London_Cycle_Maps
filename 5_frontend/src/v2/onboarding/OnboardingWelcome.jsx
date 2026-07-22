import React from 'react';
import { useOnboarding } from './OnboardingContext';

/**
 * First-timer fork — sign up + tour, or sign in / continue as guest.
 * Flat composition (no card chrome).
 */
export default function OnboardingWelcome() {
  const {
    onboardingTheme,
    chooseSignup,
    chooseGuest,
    chooseSignIn,
    skipAll,
  } = useOnboarding();

  return (
    <div className="onb-screen" data-theme={onboardingTheme}>
      <button type="button" className="onb-skip" onClick={skipAll}>
        Skip
      </button>

      <div className="onb-flat">
        <h1 className="onb-flat__title">Welcome to TUNE</h1>
        <p className="onb-flat__body">
          Get your own personalised cycle route across London, matched to your bike
          and the way you like to ride. Since it&apos;s your first time here, let&apos;s
          set up an account so we can remember your preferences.
        </p>
        <div className="onb-flat__actions">
          <button type="button" className="onb-btn onb-btn--primary" onClick={chooseSignup}>
            Sign up and take the tour
          </button>
          <p className="onb-flat__alt">
            <button type="button" className="onb-text-link" onClick={chooseSignIn}>
              Sign in
            </button>
            {' or '}
            <button type="button" className="onb-text-link" onClick={chooseGuest}>
              continue as a guest
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}

import React, { useCallback } from 'react';
import AuthPanel from '../../auth/AuthPanel';
import { useOnboarding } from './OnboardingContext';

/**
 * Full-screen signup — AuthPanel without card chrome.
 */
export default function OnboardingSignup() {
  const { onboardingTheme, signupDone, skipAll, setDisplayName } = useOnboarding();

  const handleSuccess = useCallback(({ displayName: name } = {}) => {
    if (name) setDisplayName(name);
    signupDone(name || '');
  }, [setDisplayName, signupDone]);

  return (
    <div className="onb-screen" data-theme={onboardingTheme}>
      <button type="button" className="onb-skip" onClick={skipAll}>
        Skip
      </button>

      <div className="onb-signup">
        <h1 className="onb-flat__title">Create your account</h1>
        <p className="onb-flat__body">
          This is how we&apos;ll remember your profiles and preferences. It only takes
          a few seconds.
        </p>
        <AuthPanel
          variant="inline"
          themeMode={onboardingTheme}
          initialTab="signup"
          signupOnly
          visible
          onSuccess={handleSuccess}
        />
      </div>
    </div>
  );
}

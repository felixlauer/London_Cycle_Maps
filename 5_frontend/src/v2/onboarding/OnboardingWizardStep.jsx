import React, { useCallback } from 'react';
import PresetWizardShell from '../wizard/PresetWizardShell';
import { useOnboarding } from './OnboardingContext';

/**
 * First riding profile — embeds the real PresetWizardShell full-screen.
 * On save, auto-advances into the spotlight tutorial (no Next button).
 */
export default function OnboardingWizardStep({ onProfileCreated }) {
  const {
    onboardingTheme,
    displayName,
    wizardDone,
    skipAll,
  } = useOnboarding();

  const name = displayName || 'there';

  const handleCreated = useCallback((profile) => {
    onProfileCreated?.(profile);
    wizardDone();
  }, [onProfileCreated, wizardDone]);

  return (
    <div className="onb-wizard" data-theme={onboardingTheme}>
      <button type="button" className="onb-skip" onClick={skipAll}>
        Skip
      </button>
      <div className="onb-wizard__intro">
        <p className="onb-wizard__intro-text">
          Hey {name}, let&apos;s build your first riding profile so the algorithm
          knows exactly how you like your routes.
        </p>
      </div>
      <div className="onb-wizard__body">
        <PresetWizardShell
          themeMode={onboardingTheme}
          onCreated={handleCreated}
        />
      </div>
    </div>
  );
}

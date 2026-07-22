import React from 'react';
import { useOnboarding } from './OnboardingContext';
import OnboardingLoading from './OnboardingLoading';
import OnboardingWelcome from './OnboardingWelcome';
import OnboardingSignup from './OnboardingSignup';
import OnboardingWizardStep from './OnboardingWizardStep';
import TutorialController from './TutorialController';
import './onboarding.css';

/**
 * Renders the active onboarding phase overlay above MapShell.
 */
export default function OnboardingLayer({
  tutorialSignals,
  onProfileCreated,
}) {
  const { phase } = useOnboarding();

  if (phase === 'done') return null;

  if (phase === 'booting') {
    return <OnboardingLoading />;
  }

  if (phase === 'welcome') {
    return <OnboardingWelcome />;
  }

  if (phase === 'signup') {
    return <OnboardingSignup />;
  }

  if (phase === 'wizard') {
    return (
      <OnboardingWizardStep
        onProfileCreated={onProfileCreated}
      />
    );
  }

  if (phase === 'tutorial') {
    return <TutorialController signals={tutorialSignals || {}} />;
  }

  return null;
}

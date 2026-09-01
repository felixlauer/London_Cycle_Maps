import { StyleSheet, View } from 'react-native';
import { useOnboarding } from './OnboardingContext';
import { OnboardingLoading } from './OnboardingLoading';
import { OnboardingSignup } from './OnboardingSignup';
import { OnboardingWelcome } from './OnboardingWelcome';
import { OnboardingWizardStep } from './OnboardingWizardStep';
import { TutorialController } from './tutorial/TutorialController';

type Props = {
  onProfileCreated?: (profile: Record<string, unknown>) => void;
};

/** Fixed overlay — phase → screen. Unmounts when phase === 'done'. */
export function OnboardingLayer({ onProfileCreated }: Props) {
  const { phase, tutorialSignals } = useOnboarding();

  if (phase === 'done') return null;

  if (phase === 'tutorial') {
    return <TutorialController signals={tutorialSignals || {}} />;
  }

  return (
    <View style={styles.layer} pointerEvents="box-none">
      {phase === 'booting' ? <OnboardingLoading /> : null}
      {phase === 'welcome' ? <OnboardingWelcome /> : null}
      {phase === 'signup' ? <OnboardingSignup /> : null}
      {phase === 'wizard' ? (
        <OnboardingWizardStep onProfileCreated={onProfileCreated} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  layer: {
    ...StyleSheet.absoluteFill,
    zIndex: 2000,
    elevation: 2000,
  },
});

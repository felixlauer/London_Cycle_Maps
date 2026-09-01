import { useCallback } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { PresetWizardShell } from '../wizard/PresetWizardShell';
import { useOnboarding } from './OnboardingContext';

type Props = {
  onProfileCreated?: (profile: Record<string, unknown>) => void;
};

/**
 * First riding profile — embeds PresetWizardShell.
 * On save, finishes onboarding into the app (spotlight tutorial deferred).
 */
export function OnboardingWizardStep({ onProfileCreated }: Props) {
  const {
    onboardingTheme,
    displayName,
    wizardDone,
    skipAll,
  } = useOnboarding();

  const name = displayName || 'there';
  const dark = onboardingTheme === 'dark';
  const bg = dark ? '#1c1c1e' : '#ffffff';
  const muted = dark ? '#a1a1aa' : '#71717a';

  const handleCreated = useCallback((profile: Record<string, unknown>) => {
    onProfileCreated?.(profile);
    wizardDone(profile);
  }, [onProfileCreated, wizardDone]);

  return (
    <View style={[styles.root, { backgroundColor: bg }]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Skip"
        onPress={skipAll}
        hitSlop={10}
        style={styles.skip}
      >
        <Text style={[styles.skipText, { color: muted }]}>Skip</Text>
      </Pressable>

      <View style={styles.intro}>
        <Text style={[styles.introText, { color: muted }]}>
          {`Hey ${name}, let's build your first riding profile so the algorithm knows exactly how you like your routes.`}
        </Text>
      </View>

      <View style={styles.body}>
        <PresetWizardShell
          themeMode={onboardingTheme}
          onCreated={handleCreated}
          embedded
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    ...StyleSheet.absoluteFill,
  },
  skip: {
    position: 'absolute',
    top: 52,
    left: 20,
    zIndex: 4,
  },
  skipText: {
    fontSize: 12,
    fontWeight: '600',
    textDecorationLine: 'underline',
  },
  intro: {
    paddingTop: 72,
    paddingHorizontal: 24,
    paddingBottom: 8,
  },
  introText: {
    fontSize: 14,
    fontWeight: '500',
    lineHeight: 20,
  },
  body: {
    flex: 1,
    minHeight: 0,
  },
});

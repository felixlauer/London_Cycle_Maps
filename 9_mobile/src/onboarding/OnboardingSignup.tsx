import { useCallback } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { AuthPanel } from '../ui/sidebar/AuthPanel';
import { useOnboarding } from './OnboardingContext';

/** Full-screen signup — AuthPanel without card chrome / tabs. */
export function OnboardingSignup() {
  const {
    onboardingTheme,
    signupDone,
    skipAll,
    setDisplayName,
  } = useOnboarding();

  const handleSuccess = useCallback(({ displayName: name }: { displayName?: string } = {}) => {
    if (name) setDisplayName(name);
    signupDone(name || '');
  }, [setDisplayName, signupDone]);

  const dark = onboardingTheme === 'dark';
  const bg = dark ? '#0a0a0a' : '#f4f4f5';
  const text = dark ? '#fafafa' : '#18181b';
  const muted = dark ? '#a1a1aa' : '#71717a';

  return (
    <View style={[styles.screen, { backgroundColor: bg }]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Skip"
        onPress={skipAll}
        hitSlop={10}
        style={styles.skip}
      >
        <Text style={[styles.skipText, { color: muted }]}>Skip</Text>
      </Pressable>

      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        bounces={false}
      >
        <View style={styles.inner}>
          <Text style={[styles.title, { color: text }]}>Create your account</Text>
          <Text style={[styles.body, { color: muted }]}>
            This is how we'll remember your profiles and preferences. It only takes
            a few seconds.
          </Text>
          <AuthPanel
            variant="onboarding"
            themeMode={onboardingTheme}
            initialTab="signup"
            signupOnly
            visible
            onSuccess={handleSuccess}
          />
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    ...StyleSheet.absoluteFill,
  },
  skip: {
    position: 'absolute',
    top: 52,
    left: 20,
    zIndex: 2,
  },
  skipText: {
    fontSize: 12,
    fontWeight: '600',
    textDecorationLine: 'underline',
  },
  scroll: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 24,
    paddingTop: 72,
  },
  inner: {
    width: '100%',
    maxWidth: 420,
    alignSelf: 'center',
    gap: 14,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    letterSpacing: -0.5,
  },
  body: {
    fontSize: 15,
    fontWeight: '500',
    lineHeight: 23,
    marginBottom: 4,
  },
});

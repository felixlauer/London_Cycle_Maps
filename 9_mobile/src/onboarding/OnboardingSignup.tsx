import { useCallback } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaEdges } from '../lib/safeArea';
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

  const insets = useSafeAreaEdges();
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
        style={[styles.skip, { top: insets.top + 12, left: insets.left + 20 }]}
      >
        <Text style={[styles.skipText, { color: muted }]}>Skip</Text>
      </Pressable>

      <KeyboardAvoidingView
        style={styles.flex}
        // Email and password sit low on the screen; iOS would leave them
        // behind the keyboard without this.
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={[
            styles.scroll,
            { paddingTop: insets.top + 48, paddingBottom: insets.bottom + 24 },
          ]}
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
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    ...StyleSheet.absoluteFill,
  },
  flex: {
    flex: 1,
  },
  skip: {
    position: 'absolute',
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

import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaEdges } from '../lib/safeArea';
import { brand } from '../theme/tokens';
import { useOnboarding } from './OnboardingContext';

/** First-timer fork — sign up + tour, or sign in / continue as guest. */
export function OnboardingWelcome() {
  const {
    onboardingTheme,
    chooseSignup,
    chooseGuest,
    chooseSignIn,
    skipAll,
  } = useOnboarding();

  const insets = useSafeAreaEdges();
  const dark = onboardingTheme === 'dark';
  const bg = dark ? '#0a0a0a' : '#f4f4f5';
  const text = dark ? '#fafafa' : '#18181b';
  const muted = dark ? '#a1a1aa' : '#71717a';

  return (
    <View
      style={[
        styles.screen,
        {
          backgroundColor: bg,
          paddingTop: insets.top + 24,
          paddingBottom: insets.bottom + 24,
        },
      ]}
    >
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Skip"
        onPress={skipAll}
        hitSlop={10}
        style={[styles.skip, { top: insets.top + 12, left: insets.left + 20 }]}
      >
        <Text style={[styles.skipText, { color: muted }]}>Skip</Text>
      </Pressable>

      <View style={styles.flat}>
        <Text style={[styles.title, { color: text }]}>Welcome to TUNE</Text>
        <Text style={[styles.body, { color: muted }]}>
          Get your own personalised cycle route across London, matched to your bike
          and the way you like to ride. Since it's your first time here, let's
          set up an account so we can remember your preferences.
        </Text>
        <View style={styles.actions}>
          <Pressable
            accessibilityRole="button"
            onPress={chooseSignup}
            style={({ pressed }) => [
              styles.primary,
              pressed && { transform: [{ scale: 0.97 }] },
            ]}
          >
            <Text style={styles.primaryText}>Sign up and take the tour</Text>
          </Pressable>
          <Text style={[styles.alt, { color: muted }]}>
            <Text
              style={[styles.link, { color: muted }]}
              onPress={chooseSignIn}
            >
              Log in
            </Text>
            {' or '}
            <Text
              style={[styles.link, { color: muted }]}
              onPress={chooseGuest}
            >
              continue as a guest
            </Text>
          </Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    ...StyleSheet.absoluteFill,
    paddingHorizontal: 24,
    justifyContent: 'center',
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
  flat: {
    width: '100%',
    maxWidth: 440,
    alignSelf: 'center',
    gap: 16,
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
  },
  actions: { gap: 16, marginTop: 8 },
  primary: {
    backgroundColor: brand.fuchsia,
    borderRadius: 999,
    paddingVertical: 14,
    paddingHorizontal: 18,
    alignItems: 'center',
  },
  primaryText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  alt: {
    fontSize: 14,
    fontWeight: '500',
    textAlign: 'center',
    lineHeight: 20,
  },
  link: {
    textDecorationLine: 'underline',
    fontWeight: '600',
  },
});

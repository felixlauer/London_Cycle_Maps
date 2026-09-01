import { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, Text, View } from 'react-native';
import { TriangleAlert } from 'lucide-react-native';
import { useAuth } from '../auth/AuthProvider';
import { BrandLogo } from '../ui/BrandLogo';
import { useOnboarding } from './OnboardingContext';

const EASE_OUT = Easing.bezier(0.23, 1, 0.32, 1);
const EASE_IN = Easing.bezier(0.55, 0.06, 0.68, 0.19);
/** Pulse trough → peak. Peak (== 1) matches the final still logo size. */
const PULSE_MIN = 0.92;
const PULSE_PEAK = 1;

const DEFAULT_SUB = "Let's find a smarter way to ride your routes";
const MAINTENANCE_LINE_1 = 'Server is currently undergoing maintenance';
const MAINTENANCE_LINE_2 = '(expected duration: 5 minutes)';

/**
 * Boot splash — pulsing TUNE logo, then title+subtitle pop in together and hold.
 */
export function OnboardingLoading() {
  const {
    isFirstTimer,
    flagsReady,
    onboardingTheme,
    bootExiting,
    user,
    displayName,
    showMaintenanceHint,
  } = useOnboarding();
  const { isLoading: authLoading } = useAuth();

  const pulse = useRef(new Animated.Value(1)).current;
  const textOpacity = useRef(new Animated.Value(0)).current;
  const textScale = useRef(new Animated.Value(0.9)).current;
  const textY = useRef(new Animated.Value(14)).current;
  const exitOpacity = useRef(new Animated.Value(1)).current;
  const exitY = useRef(new Animated.Value(0)).current;
  const pulseLoopRef = useRef<Animated.CompositeAnimation | null>(null);
  const textShownRef = useRef(false);

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: PULSE_MIN,
          duration: 820,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: PULSE_PEAK,
          duration: 820,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    pulseLoopRef.current = loop;
    loop.start();
    return () => {
      loop.stop();
      pulseLoopRef.current = null;
    };
  }, [pulse]);

  const name = displayName
    || user?.display_name
    || (user?.email ? String(user.email).split('@')[0] : '');

  // Wait for flag + (first-timer | auth settled) so title never flashes the wrong copy.
  const canShowTitle = flagsReady && (
    isFirstTimer
    || !authLoading
  );

  const showNamedWelcome = canShowTitle && !isFirstTimer && Boolean(user) && Boolean(name);
  const showWelcomeBack = canShowTitle && !isFirstTimer && !(user && name);
  const showFirstWelcome = canShowTitle && isFirstTimer;

  // Freeze pulse at peak (= still size), then pop title + subtitle in together.
  useEffect(() => {
    if (!canShowTitle || textShownRef.current) return undefined;
    textShownRef.current = true;

    pulseLoopRef.current?.stop();
    pulseLoopRef.current = null;

    let cancelled = false;
    pulse.stopAnimation((current) => {
      if (cancelled) return;
      const from = typeof current === 'number' ? current : PULSE_PEAK;
      const toPeak = Animated.timing(pulse, {
        toValue: PULSE_PEAK,
        duration: Math.max(140, Math.round(Math.abs(PULSE_PEAK - from) * 900)),
        easing: EASE_OUT,
        useNativeDriver: true,
      });
      const popIn = Animated.parallel([
        Animated.timing(textOpacity, {
          toValue: 1,
          duration: 480,
          easing: EASE_OUT,
          useNativeDriver: true,
        }),
        Animated.timing(textScale, {
          toValue: 1,
          duration: 480,
          easing: EASE_OUT,
          useNativeDriver: true,
        }),
        Animated.timing(textY, {
          toValue: 0,
          duration: 480,
          easing: EASE_OUT,
          useNativeDriver: true,
        }),
      ]);

      // Reach peak (still size), then text pops — title and subtitle share one transform.
      Animated.sequence([toPeak, popIn]).start();
    });

    return () => { cancelled = true; };
  }, [canShowTitle, pulse, textOpacity, textScale, textY]);

  useEffect(() => {
    if (!bootExiting) return;
    Animated.parallel([
      Animated.timing(exitOpacity, {
        toValue: 0,
        duration: 480,
        easing: EASE_IN,
        useNativeDriver: true,
      }),
      Animated.timing(exitY, {
        toValue: -10,
        duration: 480,
        easing: EASE_IN,
        useNativeDriver: true,
      }),
      Animated.timing(textOpacity, {
        toValue: 0,
        duration: 360,
        easing: EASE_IN,
        useNativeDriver: true,
      }),
      Animated.timing(textScale, {
        toValue: 0.94,
        duration: 360,
        easing: EASE_IN,
        useNativeDriver: true,
      }),
      Animated.timing(textY, {
        toValue: -6,
        duration: 360,
        easing: EASE_IN,
        useNativeDriver: true,
      }),
    ]).start();
  }, [bootExiting, exitOpacity, exitY, textOpacity, textScale, textY]);

  // Keep the logo pulsing while waiting on a cold server.
  useEffect(() => {
    if (!showMaintenanceHint || bootExiting || pulseLoopRef.current) return undefined;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: PULSE_MIN,
          duration: 820,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: PULSE_PEAK,
          duration: 820,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    pulseLoopRef.current = loop;
    loop.start();
    return () => {
      loop.stop();
      pulseLoopRef.current = null;
    };
  }, [showMaintenanceHint, bootExiting, pulse]);

  const dark = onboardingTheme === 'dark';
  const bg = dark ? '#0a0a0a' : '#f4f4f5';
  const text = dark ? '#fafafa' : '#18181b';
  const sub = dark ? '#a1a1aa' : '#71717a';

  return (
    <Animated.View
      style={[
        styles.screen,
        { backgroundColor: bg, opacity: exitOpacity, transform: [{ translateY: exitY }] },
      ]}
      accessibilityRole="progressbar"
      accessibilityState={{ busy: !bootExiting }}
    >
      <View style={styles.stack}>
        <Animated.View style={[styles.logoWrap, { transform: [{ scale: pulse }] }]}>
          <BrandLogo size={96} />
        </Animated.View>
        <Animated.View
          style={{
            opacity: textOpacity,
            transform: [{ translateY: textY }, { scale: textScale }],
            alignItems: 'center',
          }}
        >
          <Text style={[styles.title, { color: text }]}>
            {showNamedWelcome ? (
              <>
                {'Welcome back, '}
                <Text style={styles.name}>{name}</Text>
              </>
            ) : showWelcomeBack ? (
              'Welcome back!'
            ) : showFirstWelcome ? (
              'Welcome to TUNE'
            ) : (
              ' '
            )}
          </Text>
          {showMaintenanceHint ? (
            <View style={styles.maintBlock}>
              <Text style={[styles.sub, styles.maintText, { color: sub }]}>
                {MAINTENANCE_LINE_1}
              </Text>
              <Text style={[styles.sub, styles.maintText, { color: sub }]}>
                {MAINTENANCE_LINE_2}
              </Text>
              <View style={styles.maintIcon}>
                <TriangleAlert size={18} strokeWidth={2.2} color={sub} />
              </View>
            </View>
          ) : (
            <Text style={[styles.sub, { color: sub }]}>
              {DEFAULT_SUB}
            </Text>
          )}
        </Animated.View>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  screen: {
    ...StyleSheet.absoluteFill,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  stack: {
    alignItems: 'center',
    maxWidth: 420,
    gap: 14,
  },
  logoWrap: {
    marginBottom: 8,
    shadowColor: '#FF0061',
    shadowOpacity: 0.35,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 0 },
  },
  title: {
    fontSize: 36,
    fontWeight: '600',
    textAlign: 'center',
    letterSpacing: -0.4,
  },
  name: {
    fontStyle: 'italic',
    letterSpacing: 0.4,
  },
  sub: {
    marginTop: 12,
    fontSize: 17,
    fontWeight: '500',
    textAlign: 'center',
    lineHeight: 24,
  },
  maintBlock: {
    marginTop: 12,
    width: '100%',
    alignItems: 'center',
    paddingHorizontal: 8,
    gap: 2,
  },
  maintIcon: {
    marginTop: 8,
  },
  maintText: {
    marginTop: 0,
    fontSize: 15,
    textAlign: 'center',
    lineHeight: 22,
  },
});

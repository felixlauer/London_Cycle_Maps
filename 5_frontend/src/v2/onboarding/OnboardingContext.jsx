/**
 * Onboarding phase machine — loading, welcome, signup, wizard, tutorial, done.
 * Persists completion in localStorage; MapShell mounts underneath and warms up.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useAuth } from '../../auth/AuthProvider';
import { useSidebar } from '../shell/SidebarContext';

export const ONBOARDING_DONE_KEY = 'tuned_onboarding_done';
export const TUTORIAL_DONE_KEY = 'tuned_tutorial_done';

const MIN_BOOT_MS = 1600;
const SAFETY_TIMEOUT_MS = 6000;

/** @typedef {'booting' | 'welcome' | 'signup' | 'wizard' | 'tutorial' | 'done'} OnboardingPhase */

function readFlag(key) {
  try {
    return localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

function writeFlag(key, value = true) {
  try {
    if (value) localStorage.setItem(key, '1');
    else localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

/** Clear onboarding flags. URL: `?onboarding=1` or `?onboarding=reset`. */
export function resetOnboardingFlags() {
  writeFlag(ONBOARDING_DONE_KEY, false);
  writeFlag(TUTORIAL_DONE_KEY, false);
}

function consumeOnboardingQuery() {
  try {
    const url = new URL(window.location.href);
    const flag = (url.searchParams.get('onboarding') || '').toLowerCase();
    if (flag !== '1' && flag !== 'reset' && flag !== 'true') return false;
    resetOnboardingFlags();
    url.searchParams.delete('onboarding');
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
    return true;
  } catch {
    return false;
  }
}

const OnboardingContext = createContext(null);

export function OnboardingProvider({ children }) {
  const { user, isLoading: authLoading } = useAuth();
  const { themeMode, openAuthPanel } = useSidebar();

  const [isFirstTimer] = useState(() => {
    const forced = consumeOnboardingQuery();
    return forced || !readFlag(ONBOARDING_DONE_KEY);
  });
  const [phase, setPhase] = useState(/** @type {OnboardingPhase} */ ('booting'));
  const [displayName, setDisplayName] = useState('');

  const [authReady, setAuthReady] = useState(false);
  const [mapReady, setMapReady] = useState(false);
  const [profilesReady, setProfilesReady] = useState(false);
  const [minElapsed, setMinElapsed] = useState(false);
  const [safetyFired, setSafetyFired] = useState(false);
  const [bootExiting, setBootExiting] = useState(false);

  const bootStartRef = useRef(Date.now());
  const advancedFromBootRef = useRef(false);

  useEffect(() => {
    window.__TUNE_RESET_ONBOARDING__ = () => {
      resetOnboardingFlags();
      window.location.reload();
    };
    return () => {
      try {
        delete window.__TUNE_RESET_ONBOARDING__;
      } catch {
        /* ignore */
      }
    };
  }, []);

  useEffect(() => {
    if (!authLoading) setAuthReady(true);
  }, [authLoading]);

  useEffect(() => {
    const remaining = Math.max(0, MIN_BOOT_MS - (Date.now() - bootStartRef.current));
    const t = window.setTimeout(() => setMinElapsed(true), remaining);
    return () => window.clearTimeout(t);
  }, []);

  useEffect(() => {
    const t = window.setTimeout(() => setSafetyFired(true), SAFETY_TIMEOUT_MS);
    return () => window.clearTimeout(t);
  }, []);

  useEffect(() => {
    if (user?.display_name) {
      setDisplayName(String(user.display_name).trim());
    } else if (user?.email && !displayName) {
      setDisplayName(String(user.email).split('@')[0] || '');
    }
  }, [user?.display_name, user?.email, displayName]);

  const markMapReady = useCallback(() => setMapReady(true), []);
  const markProfilesReady = useCallback(() => setProfilesReady(true), []);

  const ready = (authReady && mapReady && profilesReady && minElapsed) || safetyFired;

  const persistDone = useCallback((tutorialToo = false) => {
    writeFlag(ONBOARDING_DONE_KEY, true);
    if (tutorialToo) writeFlag(TUTORIAL_DONE_KEY, true);
  }, []);

  const finishOnboarding = useCallback((opts = {}) => {
    persistDone(Boolean(opts.tutorialComplete));
    setPhase('done');
  }, [persistDone]);

  const skipAll = useCallback(() => {
    persistDone(false);
    setPhase('done');
  }, [persistDone]);

  const chooseGuest = useCallback(() => {
    persistDone(false);
    setPhase('done');
  }, [persistDone]);

  /** Enter the app with the profile sidebar open on Sign in. */
  const chooseSignIn = useCallback(() => {
    persistDone(false);
    setPhase('done');
    window.setTimeout(() => openAuthPanel('login'), 0);
  }, [persistDone, openAuthPanel]);

  const chooseSignup = useCallback(() => {
    setPhase('signup');
  }, []);

  const signupDone = useCallback((name = '') => {
    if (name) setDisplayName(String(name).trim());
    setPhase('wizard');
  }, []);

  const wizardDone = useCallback(() => {
    setPhase('tutorial');
  }, []);

  const replayTutorial = useCallback(() => {
    setPhase('tutorial');
  }, []);

  // Leave booting once ready.
  // First-timers jump straight to welcome (no fade) so the map never flashes through.
  // Returning users fade the splash out onto the map.
  useEffect(() => {
    if (phase !== 'booting' || !ready || advancedFromBootRef.current) return undefined;
    advancedFromBootRef.current = true;

    if (isFirstTimer) {
      setPhase('welcome');
      return undefined;
    }

    setBootExiting(true);
    const t = window.setTimeout(() => setPhase('done'), 360);
    return () => window.clearTimeout(t);
  }, [phase, ready, isFirstTimer]);

  /** Light surfaces for first-run flow and any tutorial walkthrough (incl. replay). */
  const onboardingTheme = (
    phase === 'tutorial'
    || (isFirstTimer && phase !== 'done')
  ) ? 'light' : themeMode;

  const value = useMemo(() => ({
    phase,
    isFirstTimer,
    displayName,
    setDisplayName,
    onboardingTheme,
    themeMode,
    bootExiting,
    ready,
    user,
    markMapReady,
    markProfilesReady,
    chooseGuest,
    chooseSignIn,
    chooseSignup,
    signupDone,
    wizardDone,
    finishOnboarding,
    skipAll,
    replayTutorial,
  }), [
    phase, isFirstTimer, displayName, onboardingTheme, themeMode, bootExiting, ready, user,
    markMapReady, markProfilesReady, chooseGuest, chooseSignIn, chooseSignup, signupDone, wizardDone,
    finishOnboarding, skipAll, replayTutorial,
  ]);

  return (
    <OnboardingContext.Provider value={value}>
      {children}
    </OnboardingContext.Provider>
  );
}

export function useOnboarding() {
  const ctx = useContext(OnboardingContext);
  if (!ctx) throw new Error('useOnboarding must be used within OnboardingProvider');
  return ctx;
}

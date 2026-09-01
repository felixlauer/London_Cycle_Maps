/**
 * Onboarding phase machine — web OnboardingContext.
 * Phases: booting → welcome → signup → wizard → tutorial → done.
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
import { useAuth } from '../auth/AuthProvider';
import { API_BASE } from '../api/flaskClient';
import { useSidebar } from '../ui/sidebar/SidebarContext';
import type { ThemeMode } from '../theme/resolveAppearance';
import {
  readOnboardingDone,
  writeOnboardingDone,
  writeTutorialDone,
} from './flags';
import type { TutorialSignals } from './tutorial/tutorialSteps';

export type OnboardingPhase =
  | 'booting'
  | 'welcome'
  | 'signup'
  | 'wizard'
  | 'tutorial'
  | 'done';

const MIN_BOOT_MS = 1600;
/** Soft-timeout map/auth only — never skip a cold backend. */
const SAFETY_TIMEOUT_MS = 12000;
const HEALTH_POLL_MS = 2500;
const MAINTENANCE_HINT_MS = 2800;
/** Time the welcome copy stays readable before the splash exits. */
const RETURNING_HOLD_MS = 2000;
const FIRST_TIMER_HOLD_MS = 2000;
const BOOT_EXIT_MS = 480;

async function fetchBackendReady(): Promise<boolean> {
  if (!API_BASE) return false;
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) return false;
    const data = await res.json().catch(() => ({} as { ready?: boolean }));
    return Boolean(data?.ready);
  } catch {
    return false;
  }
}

type OnboardingContextValue = {
  phase: OnboardingPhase;
  isFirstTimer: boolean;
  flagsReady: boolean;
  displayName: string;
  setDisplayName: (name: string) => void;
  onboardingTheme: ThemeMode;
  themeMode: ThemeMode;
  bootExiting: boolean;
  ready: boolean;
  backendReady: boolean;
  showMaintenanceHint: boolean;
  user: ReturnType<typeof useAuth>['user'];
  markMapReady: () => void;
  markProfilesReady: () => void;
  chooseGuest: () => void;
  chooseSignIn: () => void;
  chooseSignup: () => void;
  signupDone: (name?: string) => void;
  wizardDone: (profile?: Record<string, unknown>) => void;
  finishOnboarding: (opts?: { tutorialComplete?: boolean }) => void;
  skipAll: () => void;
  replayTutorial: () => void;
  /** When true during tutorial, MapView gestures stay enabled (start/end step). */
  tutorialMapPass: boolean;
  setTutorialMapPass: (pass: boolean) => void;
  pendingActivateProfile: Record<string, unknown> | null;
  consumePendingProfile: () => void;
  tutorialSignals: TutorialSignals;
  publishTutorialSignals: (next: TutorialSignals) => void;
};

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

export function OnboardingProvider({ children }: { children: React.ReactNode }) {
  const { user, isLoading: authLoading, signOut } = useAuth();
  const { themeMode, openAuthPanel } = useSidebar();

  const [flagsReady, setFlagsReady] = useState(false);
  /** null until SecureStore flag is read — avoids Welcome→Welcome-back flash. */
  const [isFirstTimer, setIsFirstTimer] = useState<boolean | null>(null);
  const [phase, setPhase] = useState<OnboardingPhase>('booting');
  const [displayName, setDisplayName] = useState('');
  const [tutorialSignals, setTutorialSignals] = useState<TutorialSignals>({});
  const [tutorialMapPass, setTutorialMapPass] = useState(false);

  const [authReady, setAuthReady] = useState(false);
  const [mapReady, setMapReady] = useState(false);
  const [profilesReady, setProfilesReady] = useState(false);
  const [backendReady, setBackendReady] = useState(false);
  const [minElapsed, setMinElapsed] = useState(false);
  const [chromeSafety, setChromeSafety] = useState(false);
  const [bootExiting, setBootExiting] = useState(false);
  const [showMaintenanceHint, setShowMaintenanceHint] = useState(false);

  const bootStartRef = useRef(Date.now());
  const advancedFromBootRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const done = await readOnboardingDone();
      if (cancelled) return;
      setIsFirstTimer(!done);
      setFlagsReady(true);
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!authLoading) setAuthReady(true);
  }, [authLoading]);

  useEffect(() => {
    const remaining = Math.max(0, MIN_BOOT_MS - (Date.now() - bootStartRef.current));
    const t = setTimeout(() => setMinElapsed(true), remaining);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    const t = setTimeout(() => setChromeSafety(true), SAFETY_TIMEOUT_MS);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      if (!backendReady) setShowMaintenanceHint(true);
    }, MAINTENANCE_HINT_MS);
    return () => clearTimeout(t);
  }, [backendReady]);

  useEffect(() => {
    if (backendReady) {
      setShowMaintenanceHint(false);
      return undefined;
    }
    let cancelled = false;
    const tick = async () => {
      const ok = await fetchBackendReady();
      if (!cancelled && ok) setBackendReady(true);
    };
    void tick();
    const id = setInterval(() => { void tick(); }, HEALTH_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [backendReady]);

  useEffect(() => {
    if (user?.display_name) {
      setDisplayName(String(user.display_name).trim());
    } else if (user?.email && !displayName) {
      setDisplayName(String(user.email).split('@')[0] || '');
    }
  }, [user?.display_name, user?.email, displayName]);

  const markMapReady = useCallback(() => setMapReady(true), []);
  const markProfilesReady = useCallback(() => setProfilesReady(true), []);

  const chromeReady = (authReady && mapReady && profilesReady && minElapsed) || chromeSafety;
  const ready = Boolean(flagsReady && backendReady && chromeReady);

  const persistDone = useCallback(async (tutorialToo = false) => {
    await writeOnboardingDone(true);
    if (tutorialToo) await writeTutorialDone(true);
  }, []);

  const finishOnboarding = useCallback((opts: { tutorialComplete?: boolean } = {}) => {
    void persistDone(Boolean(opts.tutorialComplete));
    setPhase('done');
  }, [persistDone]);

  const skipAll = useCallback(() => {
    void persistDone(false);
    setPhase('done');
  }, [persistDone]);

  const chooseGuest = useCallback(() => {
    void (async () => {
      try {
        await signOut();
      } catch {
        /* ignore */
      }
      await persistDone(false);
      setPhase('done');
    })();
  }, [persistDone, signOut]);

  const chooseSignIn = useCallback(() => {
    void persistDone(false);
    setPhase('done');
    setTimeout(() => openAuthPanel('login'), 0);
  }, [persistDone, openAuthPanel]);

  const chooseSignup = useCallback(() => {
    setPhase('signup');
  }, []);

  const signupDone = useCallback((name = '') => {
    if (name) setDisplayName(String(name).trim());
    setPhase('wizard');
  }, []);

  const [pendingActivateProfile, setPendingActivateProfile] = useState<Record<string, unknown> | null>(null);

  const wizardDone = useCallback((profile?: Record<string, unknown>) => {
    if (profile) setPendingActivateProfile(profile);
    setPhase('tutorial');
  }, []);

  const replayTutorial = useCallback(() => {
    setPhase('tutorial');
  }, []);

  const consumePendingProfile = useCallback(() => {
    setPendingActivateProfile(null);
  }, []);

  const publishTutorialSignals = useCallback((next: TutorialSignals) => {
    setTutorialSignals(next);
  }, []);

  useEffect(() => {
    if (phase !== 'booting' || !ready || isFirstTimer == null || advancedFromBootRef.current) {
      return undefined;
    }
    // Returning users: wait until auth has settled so the correct title can show.
    if (!isFirstTimer && !authReady) return undefined;

    advancedFromBootRef.current = true;
    // Hold long enough to read title+subtitle after the pop-in (~480ms).
    const hold = isFirstTimer ? FIRST_TIMER_HOLD_MS : RETURNING_HOLD_MS;

    const tHold = setTimeout(() => {
      setBootExiting(true);
      setTimeout(() => {
        setPhase(isFirstTimer ? 'welcome' : 'done');
      }, BOOT_EXIT_MS);
    }, hold);

    return () => clearTimeout(tHold);
  }, [phase, ready, isFirstTimer, authReady]);

  useEffect(() => {
    if (phase !== 'tutorial') setTutorialMapPass(false);
  }, [phase]);

  /** Light surfaces for first-run flow and any tutorial walkthrough (incl. replay). */
  const onboardingTheme: ThemeMode = (
    phase === 'tutorial'
    || (Boolean(isFirstTimer) && phase !== 'done')
  ) ? 'light' : themeMode;

  const value = useMemo(() => ({
    phase,
    isFirstTimer: Boolean(isFirstTimer),
    flagsReady,
    displayName,
    setDisplayName,
    onboardingTheme,
    themeMode,
    bootExiting,
    ready,
    backendReady,
    showMaintenanceHint,
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
    tutorialMapPass,
    setTutorialMapPass,
    pendingActivateProfile,
    consumePendingProfile,
    tutorialSignals,
    publishTutorialSignals,
  }), [
    phase, isFirstTimer, flagsReady, displayName, onboardingTheme, themeMode,
    bootExiting, ready, backendReady, showMaintenanceHint, user, markMapReady, markProfilesReady, chooseGuest,
    chooseSignIn, chooseSignup, signupDone, wizardDone, finishOnboarding, skipAll,
    replayTutorial, tutorialMapPass, pendingActivateProfile, consumePendingProfile,
    tutorialSignals, publishTutorialSignals,
  ]);

  return (
    <OnboardingContext.Provider value={value}>
      {children}
    </OnboardingContext.Provider>
  );
}

export function useOnboarding(): OnboardingContextValue {
  const ctx = useContext(OnboardingContext);
  if (!ctx) throw new Error('useOnboarding must be used within OnboardingProvider');
  return ctx;
}

/** Optional hook for map/screens that may mount outside onboarding in tests. */
export function useOnboardingOptional(): OnboardingContextValue | null {
  return useContext(OnboardingContext);
}

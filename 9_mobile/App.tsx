import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { apiFetch } from './src/api/flaskClient';
import { AuthProvider, useAuth } from './src/auth/AuthProvider';
import { PlanMapScreen } from './src/map/PlanMapScreen';
import { OnboardingLayer } from './src/onboarding/OnboardingLayer';
import { OnboardingProvider, useOnboarding } from './src/onboarding/OnboardingContext';
import { SidebarProvider } from './src/ui/sidebar/SidebarContext';
import { SuggestPortalProvider } from './src/ui/SuggestPortal';

const NIGHT_POLL_MS = 5 * 60 * 1000;

function Root() {
  const { session } = useAuth();
  const [isDarkOutside, setIsDarkOutside] = useState(false);

  useEffect(() => {
    if (!session?.access_token) {
      setIsDarkOutside(false);
      return undefined;
    }
    let cancelled = false;

    const fetchNight = async () => {
      try {
        const res = await apiFetch('/night_status');
        const data = await res.json().catch(() => ({}));
        if (cancelled || !res.ok) return;
        setIsDarkOutside(Boolean(data.is_dark));
      } catch {
        /* non-fatal */
      }
    };

    void fetchNight();
    const id = setInterval(() => { void fetchNight(); }, NIGHT_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [session?.access_token]);

  return (
    <SidebarProvider isDarkOutside={isDarkOutside}>
      <OnboardingProvider>
        <AppShell />
      </OnboardingProvider>
    </SidebarProvider>
  );
}

function AppShell() {
  const { themeMode, onboardingTheme, phase } = useOnboarding();
  const chromeTheme = phase !== 'done' ? onboardingTheme : themeMode;

  const handleProfileCreated = useCallback((_profile: Record<string, unknown>) => {
    /* PlanMapScreen reloads via auth/user change + optional sidebar callbacks */
  }, []);

  return (
    <View style={styles.root}>
      <SuggestPortalProvider>
        <PlanMapScreen />
        <OnboardingLayer onProfileCreated={handleProfileCreated} />
      </SuggestPortalProvider>
      <StatusBar style={chromeTheme === 'dark' ? 'light' : 'dark'} />
    </View>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Root />
    </AuthProvider>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});

/**
 * Chrome tokens + outdoor-dark for overlays/CAE (web shell data-theme + isDarkOutside).
 * During onboarding/tutorial, force the onboarding theme so chrome matches the map.
 */
import { useOnboardingOptional } from '../onboarding/OnboardingContext';
import { useSidebar } from '../ui/sidebar/SidebarContext';
import { chromeForTheme, type ChromeTokens } from './tokens';
import type { ThemeMode } from './resolveAppearance';

export function useChrome(): {
  themeMode: ThemeMode;
  isDarkOutside: boolean;
  c: ChromeTokens;
} {
  const { themeMode: sidebarTheme, isDarkOutside } = useSidebar();
  const onboarding = useOnboardingOptional();

  const themeMode: ThemeMode = (
    onboarding
    && onboarding.phase !== 'done'
    && (
      onboarding.phase === 'tutorial'
      || onboarding.isFirstTimer
    )
  ) ? onboarding.onboardingTheme : sidebarTheme;

  return {
    themeMode,
    isDarkOutside,
    c: chromeForTheme(themeMode),
  };
}

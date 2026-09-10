/**
 * Props shared by every TextInput in the app.
 *
 * iOS draws the keyboard in the system appearance, which clashes when the shell
 * is dark on a light-mode phone (or the reverse) — `keyboardAppearance` follows
 * the resolved chrome theme instead. Android's Material underline fights the
 * bordered field containers, so it is always off; the prop is inert on iOS.
 */
import type { TextInputProps } from 'react-native';
import type { ThemeMode } from './resolveAppearance';
import { useChrome } from './useChrome';

/** @param override surfaces that force their own theme, e.g. onboarding AuthPanel. */
export function useInputChrome(override?: ThemeMode): Pick<
  TextInputProps,
  'keyboardAppearance' | 'underlineColorAndroid'
> {
  const { themeMode } = useChrome();
  return {
    keyboardAppearance: (override ?? themeMode) === 'dark' ? 'dark' : 'light',
    underlineColorAndroid: 'transparent',
  };
}

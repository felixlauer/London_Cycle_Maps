import { Platform, StatusBar } from 'react-native';

/** Avoid extra native deps for Wave A — Android status bar + iOS notch approx. */
export function useSafeAreaTop() {
  if (Platform.OS === 'android') {
    return (StatusBar.currentHeight || 24) + 4;
  }
  // Typical notched iPhone safe top; Wave D can switch to safe-area-context.
  return 52;
}

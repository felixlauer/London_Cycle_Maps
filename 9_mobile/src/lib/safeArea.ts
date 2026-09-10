/**
 * Device safe areas, from react-native-safe-area-context.
 *
 * iOS needs real numbers, not the old constant: the top inset differs between
 * a notch and a Dynamic Island, and the home indicator claims a bottom strip
 * that the island, overlay rail and wizard footer must clear. Android keeps
 * its status-bar behaviour through the same provider.
 *
 * Chrome insets first, Tuned spacing (space.inset) inside what is left.
 */
import { Platform } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

/**
 * Android sat 4 px below the status bar before insets were measured properly.
 * Kept so the Android build — the layout reference for the iOS port — does not
 * shift. iOS uses the measured inset alone.
 */
const ANDROID_TOP_NUDGE = Platform.OS === 'android' ? 4 : 0;

/** Status bar / notch / Dynamic Island. */
export function useSafeAreaTop() {
  return useSafeAreaInsets().top + ANDROID_TOP_NUDGE;
}

/** Home indicator or Android gesture bar. Zero on older hardware. */
export function useSafeAreaBottom() {
  return useSafeAreaInsets().bottom;
}

/** All four edges — landscape is not supported, but left/right stay honest. */
export function useSafeAreaEdges() {
  return useSafeAreaInsets();
}

/**
 * Live Reduce Motion state (iOS Settings → Accessibility → Motion, and the
 * Android equivalent).
 *
 * Riders can flip the switch while the app is open, so this subscribes instead
 * of reading once at mount. Large morphs — the island expanding 108 → 240,
 * the plan ↔ nav face swap — collapse to a short opacity cross-fade when it is
 * on, keeping the same start and end states.
 */
import { useEffect, useState } from 'react';
import { AccessibilityInfo } from 'react-native';

/** Cross-fade length used in place of a geometry morph. */
export const REDUCED_MOTION_MS = 150;

export function useReduceMotion() {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    let cancelled = false;

    AccessibilityInfo.isReduceMotionEnabled()
      .then((on) => {
        if (!cancelled) setEnabled(on);
      })
      .catch(() => undefined);

    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setEnabled);
    return () => {
      cancelled = true;
      sub.remove();
    };
  }, []);

  return enabled;
}

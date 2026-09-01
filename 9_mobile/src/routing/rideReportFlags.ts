/**
 * Build-time flags for in-ride route feedback.
 *
 * EXPO_PUBLIC_* is inlined into the JS bundle at build time, so these are fixed
 * for the life of an installed APK — see scripts/run-android-outdoor.ps1.
 */

/**
 * Test build: reports still upload and still steer *this* rider's own routes,
 * but the backend excludes them from every global aggregate. Use it for outdoor
 * testing so trial taps never change what other people are routed over.
 *
 * Only meaningful when signed in — a personal overlay needs a user id, so a
 * guest report marked personal-only is stored and then ignored by both paths.
 */
export const RIDE_REPORT_PERSONAL_ONLY =
  (process.env.EXPO_PUBLIC_RIDE_REPORT_PERSONAL_ONLY || '').trim() === '1';

/** Desk replay along the route — mirrors the flag useNavSession reads. */
export const RIDE_REPORT_SIMULATE =
  (process.env.EXPO_PUBLIC_NAV_SIMULATE || '').trim() === '1';

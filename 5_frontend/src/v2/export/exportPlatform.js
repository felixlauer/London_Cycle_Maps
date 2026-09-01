/**
 * OS for GPX handoff copy + click behaviour.
 * Viewport `useIsMobile` is layout only — do not reuse it here.
 */

export function detectExportPlatform(ua, hints = {}) {
  const s = String(ua || (typeof navigator !== 'undefined' ? navigator.userAgent : '') || '');
  const touch = hints.touchEnd ?? (typeof window !== 'undefined' && 'ontouchend' in window);
  if (/iPhone|iPad|iPod/i.test(s)) return 'ios';
  // iPadOS 13+ can report as Macintosh
  if (/Macintosh/i.test(s) && touch) return 'ios';
  if (/Android/i.test(s)) return 'android';
  return 'desktop';
}

export function exportSuccessMessage(platform, method) {
  if (platform === 'android') {
    return 'GPX downloaded. Open the file, then Garmin Connect.';
  }
  if (platform === 'ios') {
    if (method === 'share') return 'Choose Garmin Connect if you have it.';
    return 'Saved. In Files, share it to Garmin Connect.';
  }
  return 'GPX downloaded. Import it as a Course on Garmin Connect.';
}

/**
 * Appearance preference → effective light|dark for shell + map.
 * Pref: light | dark | system | auto
 */
export const APPEARANCE_STORAGE_KEY = 'tuned_ui_appearance';

export const APPEARANCE_OPTIONS = [
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
  { id: 'system', label: 'System' },
  { id: 'auto', label: 'Auto' },
];

export function readStoredAppearance() {
  try {
    const v = localStorage.getItem(APPEARANCE_STORAGE_KEY);
    if (v === 'light' || v === 'dark' || v === 'system' || v === 'auto') return v;
  } catch {
    /* ignore */
  }
  return 'auto';
}

export function writeStoredAppearance(pref) {
  try {
    localStorage.setItem(APPEARANCE_STORAGE_KEY, pref);
  } catch {
    /* ignore */
  }
}

export function systemPrefersDark() {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

/**
 * @param {'light'|'dark'|'system'|'auto'} preference
 * @param {{ isDarkOutside?: boolean }} [opts]
 * @returns {'light'|'dark'}
 */
export function resolveEffectiveTheme(preference, opts = {}) {
  const forced = process.env.REACT_APP_FORCE_MODE;
  if (forced === 'day') return 'light';
  if (forced === 'night') return 'dark';

  if (preference === 'light') return 'light';
  if (preference === 'dark') return 'dark';
  if (preference === 'system') return systemPrefersDark() ? 'dark' : 'light';
  // auto — London sunset via /night_status
  return opts.isDarkOutside ? 'dark' : 'light';
}

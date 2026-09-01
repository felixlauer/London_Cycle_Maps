/**
 * Appearance preference → effective light|dark for shell + map.
 * Pref: light | dark | system | auto
 */
import { Appearance } from 'react-native';
import * as SecureStore from 'expo-secure-store';

export const APPEARANCE_STORAGE_KEY = 'tuned_ui_appearance';

export type AppearancePref = 'light' | 'dark' | 'system' | 'auto';
export type ThemeMode = 'light' | 'dark';

export const APPEARANCE_OPTIONS: { id: AppearancePref; label: string }[] = [
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
  { id: 'system', label: 'System' },
  { id: 'auto', label: 'Auto' },
];

let memoryAppearance: AppearancePref | null = null;

export async function loadStoredAppearance(): Promise<AppearancePref> {
  if (memoryAppearance) return memoryAppearance;
  try {
    const v = await SecureStore.getItemAsync(APPEARANCE_STORAGE_KEY);
    if (v === 'light' || v === 'dark' || v === 'system' || v === 'auto') {
      memoryAppearance = v;
      return v;
    }
  } catch {
    /* ignore */
  }
  memoryAppearance = 'auto';
  return 'auto';
}

export function peekAppearance(): AppearancePref {
  return memoryAppearance || 'auto';
}

export async function writeStoredAppearance(pref: AppearancePref): Promise<void> {
  memoryAppearance = pref;
  try {
    await SecureStore.setItemAsync(APPEARANCE_STORAGE_KEY, pref);
  } catch {
    /* ignore */
  }
}

export function systemPrefersDark(): boolean {
  return Appearance.getColorScheme() === 'dark';
}

export function resolveEffectiveTheme(
  preference: AppearancePref,
  opts: { isDarkOutside?: boolean } = {},
): ThemeMode {
  if (preference === 'light') return 'light';
  if (preference === 'dark') return 'dark';
  if (preference === 'system') return systemPrefersDark() ? 'dark' : 'light';
  return opts.isDarkOutside ? 'dark' : 'light';
}

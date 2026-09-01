/**
 * Tuned mobile chrome tokens — BRIEF.md + web v2 shell.
 * Accent reserved for primary actions + profile route.
 */

export const brand = {
  fuchsia: '#FF0061',
  blueBell: '#4D9DE0',
  violet: '#8717BF',
  jungle: '#3BB273',
  banana: '#FDE74C',
  tiger: '#F18805',
} as const;

export type ChromeTokens = {
  shellBg: string;
  shellBorder: string;
  text: string;
  textSub: string;
  icon: string;
  surface: string;
  surfaceHover: string;
  inset: string;
  line: string;
  mapFallback: string;
  danger: string;
  startDot: string;
  badgeFg: string;
  selectedSeg: string;
};

/** Dark floating panel (mobile planner default). */
export const dark: ChromeTokens = {
  shellBg: '#1C1C1E',
  shellBorder: '#3A3A3C',
  text: '#F4F4F5',
  textSub: '#A1A1AA',
  icon: '#A1A1AA',
  surface: '#2C2C2E',
  surfaceHover: '#3A3A3C',
  inset: '#232325',
  line: '#3A3A3C',
  mapFallback: '#0A0A0A',
  danger: '#FF6B6B',
  startDot: '#3DDC97',
  badgeFg: '#2C2C2E',
  selectedSeg: '#1C1C1E',
};

/** Light shell — web map-shell data-theme=light. */
export const light: ChromeTokens = {
  shellBg: '#FFFFFF',
  shellBorder: '#E5E7EB',
  text: '#18181B',
  textSub: '#71717A',
  icon: '#71717A',
  surface: '#F4F4F5',
  surfaceHover: '#E4E4E7',
  inset: '#F4F4F5',
  line: '#E4E4E7',
  mapFallback: '#E8EEF4',
  danger: '#B91C1C',
  startDot: '#3DDC97',
  badgeFg: '#F4F4F5',
  selectedSeg: '#FFFFFF',
};

export function chromeForTheme(mode: 'light' | 'dark'): ChromeTokens {
  return mode === 'light' ? light : dark;
}

export const space = {
  inset: 12,
  panelPad: 14,
  gap: 12,
  radius: 14,
  radiusSm: 10,
  radiusPill: 12,
} as const;

export const motion = {
  pressMs: 160,
  easeOut: 'ease-out' as const,
  menuMs: 180,
  cameraMs: 400,
  fitMs: 500,
} as const;

export const routeColors = {
  profile: brand.fuchsia,
} as const;

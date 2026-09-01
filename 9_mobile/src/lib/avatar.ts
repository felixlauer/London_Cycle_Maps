/** Deterministic avatar colours from email — BRIEF brand accents (RN solid fill). */

type Palette = { from: string; to: string; color: string };

const PALETTES: Palette[] = [
  { from: '#FF0061', to: '#FF4D8F', color: '#fff' },
  { from: '#4D9DE0', to: '#7BB8E8', color: '#fff' },
  { from: '#8717BF', to: '#A855F7', color: '#fff' },
  { from: '#3BB273', to: '#6BC995', color: '#fff' },
  { from: '#F18805', to: '#F5A84A', color: '#fff' },
  { from: '#610345', to: '#9A1A6B', color: '#fff' },
  { from: '#13C2A4', to: '#5EEBD1', color: '#0a2a24' },
  { from: '#FDE74C', to: '#F5C518', color: '#1c1c1e' },
];

function hashString(s: string) {
  let h = 0;
  const str = String(s || '');
  for (let i = 0; i < str.length; i += 1) {
    h = ((h << 5) - h) + str.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
}

export function initialsFromEmail(email?: string | null) {
  if (!email) return '?';
  const local = String(email).split('@')[0] || '';
  const parts = local.split(/[._+-]/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0] || ''}${parts[1][0] || ''}`.toUpperCase();
  }
  return local.slice(0, 2).toUpperCase() || '?';
}

export function initialsFromUser(user?: { display_name?: string | null; email?: string | null } | null) {
  const name = String(user?.display_name || '').trim();
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
      return `${parts[0][0] || ''}${parts[1][0] || ''}`.toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  }
  return initialsFromEmail(user?.email);
}

export function avatarPaletteForEmail(email?: string | null): Palette {
  return PALETTES[hashString(email || '') % PALETTES.length];
}

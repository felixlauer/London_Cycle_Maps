/**
 * Deterministic avatar colours from email — brand accent palette + logo-style gradient.
 */

/** Brand / overlay accents (BRIEF) — fixed per user via hash. */
const PALETTES = [
  { from: '#FF0061', to: '#FF4D8F', color: '#fff' }, // Hot Fuchsia
  { from: '#4D9DE0', to: '#7BB8E8', color: '#fff' }, // Blue Bell
  { from: '#8717BF', to: '#A855F7', color: '#fff' }, // Violet
  { from: '#3BB273', to: '#6BC995', color: '#fff' }, // Jungle Green
  { from: '#F18805', to: '#F5A84A', color: '#fff' }, // Tiger Orange
  { from: '#610345', to: '#9A1A6B', color: '#fff' }, // Crimson Violet
  { from: '#13C2A4', to: '#5EEBD1', color: '#0a2a24' }, // Turquoise
  { from: '#FDE74C', to: '#F5C518', color: '#1c1c1e' }, // Banana Cream
];

function hashString(s) {
  let h = 0;
  const str = String(s || '');
  for (let i = 0; i < str.length; i += 1) {
    h = ((h << 5) - h) + str.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
}

export function initialsFromEmail(email) {
  if (!email) return '?';
  const local = String(email).split('@')[0] || '';
  const parts = local.split(/[._+-]/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0] || ''}${parts[1][0] || ''}`.toUpperCase();
  }
  return local.slice(0, 2).toUpperCase() || '?';
}

/** Initials from display name, falling back to email local-part. */
export function initialsFromUser(user) {
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

/** Display name from email local-part (e.g. jon.alishon → Jon Alishon). */
export function displayNameFromEmail(email) {
  if (!email) return 'Guest';
  const local = String(email).split('@')[0] || '';
  const parts = local.split(/[._+-]/).filter(Boolean);
  if (!parts.length) return local || 'Account';
  return parts
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1).toLowerCase())
    .join(' ');
}

/** Prefer saved display_name; otherwise email heuristic. */
export function displayNameFromUser(user) {
  const name = String(user?.display_name || '').trim();
  if (name) return name;
  return displayNameFromEmail(user?.email);
}

export function avatarStyleForEmail(email) {
  const palette = PALETTES[hashString(email) % PALETTES.length];
  return {
    background: `linear-gradient(135deg, ${palette.from}, ${palette.to})`,
    color: palette.color,
  };
}

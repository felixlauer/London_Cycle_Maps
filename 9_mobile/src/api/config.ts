/** Resolve Flask API origin for the mobile client. */
export function resolveApiBase(): string {
  return (process.env.EXPO_PUBLIC_API_BASE || '').trim().replace(/\/$/, '');
}

export const API_BASE = resolveApiBase();

/** Soft UI limit so custom names fit the routing mode pill. Backend allows up to 22. */
export const MAX_PROFILE_NAME_LEN = 8;

export function validateProfileName(name) {
  const trimmed = (name || '').trim();
  if (!trimmed) return 'Give your profile a name.';
  if (trimmed.length > MAX_PROFILE_NAME_LEN) {
    return `Max ${MAX_PROFILE_NAME_LEN} characters.`;
  }
  return '';
}

/** Soft profile name validation — web v2/wizard/profileName.js */

export const MAX_PROFILE_NAME_LEN = 8;

export function validateProfileName(name: string): string {
  const trimmed = (name || '').trim();
  if (!trimmed) return 'Give your profile a name.';
  if (trimmed.length > MAX_PROFILE_NAME_LEN) {
    return `Max ${MAX_PROFILE_NAME_LEN} characters.`;
  }
  return '';
}

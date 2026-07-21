import { validateProfileName, MAX_PROFILE_NAME_LEN } from './profileName';

describe('validateProfileName', () => {
  it('rejects empty names', () => {
    expect(validateProfileName('')).toBe('Give your profile a name.');
    expect(validateProfileName('   ')).toBe('Give your profile a name.');
  });

  it('rejects names longer than the mode pill limit', () => {
    const long = 'a'.repeat(MAX_PROFILE_NAME_LEN + 1);
    expect(validateProfileName(long)).toMatch(/Max 8 characters/);
  });

  it('accepts short names', () => {
    expect(validateProfileName('Commute')).toBe('');
    expect(validateProfileName('a'.repeat(MAX_PROFILE_NAME_LEN))).toBe('');
  });
});

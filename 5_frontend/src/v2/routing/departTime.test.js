import { formatDepartHm, maskTimeDigits, parseDepartTime } from './departTime';

describe('formatDepartHm', () => {
  it('zero-pads hour and minute', () => {
    expect(formatDepartHm(9, 5)).toBe('09:05');
    expect(formatDepartHm(14, 30)).toBe('14:30');
  });
});

describe('parseDepartTime', () => {
  it('parses colon, dot, and compact forms', () => {
    expect(parseDepartTime('14:30')).toEqual({ hour: 14, minute: 30 });
    expect(parseDepartTime('14.30')).toEqual({ hour: 14, minute: 30 });
    expect(parseDepartTime('1430')).toEqual({ hour: 14, minute: 30 });
    expect(parseDepartTime('9:05')).toEqual({ hour: 9, minute: 5 });
    expect(parseDepartTime('905')).toEqual({ hour: 9, minute: 5 });
  });

  it('treats a bare hour as HH:00 on blur', () => {
    expect(parseDepartTime('14')).toEqual({ hour: 14, minute: 0 });
    expect(parseDepartTime('7')).toEqual({ hour: 7, minute: 0 });
  });

  it('rejects incomplete hour-only when hourOnlyOnShort is false', () => {
    expect(parseDepartTime('14', { hourOnlyOnShort: false })).toBe(null);
  });

  it('rejects out-of-range values', () => {
    expect(parseDepartTime('24:00')).toBe(null);
    expect(parseDepartTime('14:60')).toBe(null);
    expect(parseDepartTime('')).toBe(null);
    expect(parseDepartTime('ab')).toBe(null);
  });
});

describe('maskTimeDigits', () => {
  it('strips non-digits and inserts a colon', () => {
    expect(maskTimeDigits('1')).toBe('1');
    expect(maskTimeDigits('14')).toBe('14');
    expect(maskTimeDigits('143')).toBe('14:3');
    expect(maskTimeDigits('1430')).toBe('14:30');
    expect(maskTimeDigits('14:30')).toBe('14:30');
    expect(maskTimeDigits('14.30 extra')).toBe('14:30');
  });

  it('caps at four digits', () => {
    expect(maskTimeDigits('143059')).toBe('14:30');
  });
});

/** Parse / mask 24-hour departure times (HH:MM). Shared by DepartAtControl. */

export function formatDepartHm(hour: number, minute: number) {
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

function validHm(hour: number, minute: number) {
  if (!Number.isInteger(hour) || !Number.isInteger(minute)) return null;
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return { hour, minute };
}

/**
 * Accepts 14:30, 14.30, 1430, 9:05, 905, or a bare hour (14 → 14:00).
 */
export function parseDepartTime(
  raw: string,
  { hourOnlyOnShort = true }: { hourOnlyOnShort?: boolean } = {},
) {
  const s = String(raw ?? '').trim();
  if (!s) return null;

  const sep = s.match(/^(\d{1,2})[:.hH](\d{1,2})$/);
  if (sep) return validHm(Number(sep[1]), Number(sep[2]));

  const digits = s.replace(/\D/g, '');
  if (digits.length === 4) {
    return validHm(Number(digits.slice(0, 2)), Number(digits.slice(2, 4)));
  }
  if (digits.length === 3) {
    return validHm(Number(digits.slice(0, 1)), Number(digits.slice(1)));
  }
  if (hourOnlyOnShort && (digits.length === 1 || digits.length === 2)) {
    return validHm(Number(digits), 0);
  }
  return null;
}

/** Keep at most 4 digits and insert a colon after the hour. */
export function maskTimeDigits(raw: string) {
  const digits = String(raw ?? '').replace(/\D/g, '').slice(0, 4);
  if (digits.length <= 2) return digits;
  return `${digits.slice(0, 2)}:${digits.slice(2)}`;
}

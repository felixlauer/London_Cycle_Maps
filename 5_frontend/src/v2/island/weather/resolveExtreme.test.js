import { resolveExtremeWarning } from './resolveExtreme';

const base = {
  weather_code: 2,
  is_day: true,
  wind_speed_ms: 3,
  wind_dir_deg: 45,
  temp_c: 18,
  uv_index: 2,
};

describe('resolveExtremeWarning', () => {
  test('returns null for mild conditions', () => {
    expect(resolveExtremeWarning(base)).toBeNull();
    expect(resolveExtremeWarning(null)).toBeNull();
  });

  test('thunderstorm beats strong wind', () => {
    const w = resolveExtremeWarning({
      ...base,
      weather_code: 95,
      wind_speed_ms: 15,
    });
    expect(w.kind).toBe('thunderstorm');
    expect(w.title).toBe('Thunderstorm');
    expect(w.action).toMatch(/shelter/i);
  });

  test('thunder + hail copy', () => {
    const w = resolveExtremeWarning({ ...base, weather_code: 96 });
    expect(w.title).toBe('Thunder + hail');
    expect(w.detail).toMatch(/hail/i);
  });

  test('black ice', () => {
    const w = resolveExtremeWarning({ ...base, weather_code: 66, temp_c: 0 });
    expect(w.kind).toBe('blackIce');
    expect(w.title).toBe('Black ice risk');
    expect(w.detail).toContain('0°C');
  });

  test('heavy snow', () => {
    expect(resolveExtremeWarning({ ...base, weather_code: 75 }).title).toBe('Heavy snow');
  });

  test('violent rain', () => {
    expect(resolveExtremeWarning({ ...base, weather_code: 82 }).title).toBe('Violent rain');
  });

  test('dense fog detail includes visibility', () => {
    const w = resolveExtremeWarning({ ...base, weather_code: 45 });
    expect(w.kind).toBe('denseFog');
    expect(w.detail).toContain('200 m');
    expect(w.action).toMatch(/lights/i);
  });

  test('strong wind detail includes speed and direction', () => {
    const w = resolveExtremeWarning({
      ...base,
      wind_speed_ms: 12.4,
      wind_dir_deg: 270,
    });
    expect(w.kind).toBe('strongWind');
    expect(w.detail).toBe('12 m/s · W');
  });

  test('heat only when day and hot', () => {
    expect(resolveExtremeWarning({ ...base, temp_c: 30, is_day: false })).toBeNull();
    const w = resolveExtremeWarning({ ...base, temp_c: 30, is_day: true, uv_index: 6 });
    expect(w.kind).toBe('heat');
    expect(w.title).toBe('Extreme heat');
    expect(w.detail).toBe('30°C · UV 6');
  });

  test('violent rain beats strong wind', () => {
    const w = resolveExtremeWarning({
      ...base,
      weather_code: 65,
      wind_speed_ms: 20,
    });
    expect(w.kind).toBe('violentRain');
  });
});

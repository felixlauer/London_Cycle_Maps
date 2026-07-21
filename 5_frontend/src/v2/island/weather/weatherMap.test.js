import {
  wmoToMeteocon,
  classifyWind,
  classifyTemp,
  compassFromDeg,
  windArrowRotateDeg,
  formatUvCaption,
} from './weatherMap';

describe('weatherMap', () => {
  test('wmo clear day/night', () => {
    expect(wmoToMeteocon(0, true).label).toBe('Clear');
    expect(wmoToMeteocon(0, false).label).toBe('Clear');
    expect(wmoToMeteocon(61, true).label).toBe('Rain');
    expect(wmoToMeteocon(95, true).label).toBe('Thunderstorm');
  });

  test('classifyWind bands', () => {
    expect(classifyWind(0).band).toBe('calm');
    expect(classifyWind(1.4).band).toBe('calm');
    expect(classifyWind(5).band).toBe('moderate');
    expect(classifyWind(10.1).band).toBe('extreme');
  });

  test('classifyTemp warnings', () => {
    expect(classifyTemp(3).warn).toBe('cold');
    expect(classifyTemp(18).warn).toBe(null);
    expect(classifyTemp(30).warn).toBe('hot');
    expect(classifyTemp(18).thermometer).toBe('plain');
  });

  test('formatUvCaption', () => {
    expect(formatUvCaption(4.2, true)).toBe('UV 4.2');
    expect(formatUvCaption(5, true)).toBe('UV 5');
    expect(formatUvCaption(0, true)).toBe('No UV');
    expect(formatUvCaption(3, false)).toBe('No UV');
  });

  test('compass and arrow rotation', () => {
    expect(compassFromDeg(0)).toBe('N');
    expect(compassFromDeg(270)).toBe('W');
    expect(windArrowRotateDeg(0)).toBe(-45);
    expect(windArrowRotateDeg(45)).toBe(0);
  });
});

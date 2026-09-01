import { buildGpxTrack, escapeXml, gpxFilename, gpxTrackName } from './gpx';
import { detectExportPlatform, exportSuccessMessage } from './exportPlatform';

describe('gpxFilename', () => {
  it('slugs labels into a .gpx name', () => {
    expect(gpxFilename("King's Cross", 'Soho')).toBe('tuned-kings-cross-to-soho.gpx');
  });

  it('falls back when labels are empty', () => {
    expect(gpxFilename('', '')).toBe('tuned-route-to-route.gpx');
  });
});

describe('buildGpxTrack', () => {
  const path = [
    [51.53, -0.12],
    [51.52, -0.13],
  ];

  it('writes a GPX 1.1 track with lat/lon in Tuned order', () => {
    const xml = buildGpxTrack({ path, name: 'A to B' });
    expect(xml).toContain('<?xml version="1.0" encoding="UTF-8"?>');
    expect(xml).toContain('gpx version="1.1"');
    expect(xml).toContain('<name>A to B</name>');
    expect(xml).toContain('<trkpt lat="51.53" lon="-0.12">');
    expect(xml).toContain('<trkpt lat="51.52" lon="-0.13">');
    expect(xml).not.toContain('<rte>');
  });

  it('escapes track names', () => {
    const xml = buildGpxTrack({ path, name: 'A & B <test>' });
    expect(xml).toContain('<name>A &amp; B &lt;test&gt;</name>');
  });

  it('rejects a short path', () => {
    expect(() => buildGpxTrack({ path: [[51, 0]] })).toThrow(/too short/);
  });
});

describe('escapeXml / gpxTrackName', () => {
  it('escapes XML entities', () => {
    expect(escapeXml(`a&b<"'>`)).toBe('a&amp;b&lt;&quot;&apos;&gt;');
  });

  it('joins start and end for the track title', () => {
    expect(gpxTrackName('Camden', 'Soho')).toBe('Camden to Soho');
  });
});

describe('detectExportPlatform', () => {
  it('detects iOS, Android, and desktop', () => {
    expect(detectExportPlatform('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)')).toBe('ios');
    expect(detectExportPlatform('Mozilla/5.0 (Linux; Android 14)')).toBe('android');
    expect(detectExportPlatform('Mozilla/5.0 (Windows NT 10.0; Win64; x64)')).toBe('desktop');
  });

  it('treats iPadOS desktop UA with touch as iOS', () => {
    expect(detectExportPlatform(
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
      { touchEnd: true },
    )).toBe('ios');
  });
});

describe('exportSuccessMessage', () => {
  it('varies by platform and method', () => {
    expect(exportSuccessMessage('desktop', 'download')).toMatch(/Course on Garmin Connect/);
    expect(exportSuccessMessage('android', 'download')).toMatch(/Open the file/);
    expect(exportSuccessMessage('ios', 'share')).toMatch(/Choose Garmin Connect/);
    expect(exportSuccessMessage('ios', 'download')).toMatch(/Files/);
  });
});

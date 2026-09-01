import { buildRideReport, withCategory, type RideReportInput } from './rideReportPayload';

function input(overrides: Partial<RideReportInput> = {}): RideReportInput {
  return {
    clientEventId: '11111111-2222-3333-4444-555555555555',
    category: 'general',
    deviceId: 'dev-abc',
    personalOnly: false,
    simulate: false,
    progress: {
      legIndex: 0,
      stepIndex: 2,
      upcomingLegIndex: 0,
      upcomingStepIndex: 3,
      distanceRemaining: 1200,
      durationRemaining: 400,
      stepDistanceRemaining: 80,
      fractionTraveled: 0.25,
      latitude: 51.5074,
      longitude: -0.1278,
      speed: 4.2,
      bearing: 91,
      distanceFromRoute: 3.1,
      hasHeading: true,
      altitude: 18.5,
      hAccuracyM: 6,
      puckSource: 'gps',
      gpsEpochMs: 1_700_000_000_000,
      mocked: false,
    },
    nav: {
      rerouting: false,
      tracking: true,
      overviewActive: false,
      muted: false,
      cyclewaysVisible: true,
      startedAtMs: 1_000,
    },
    route: {},
    profile: {},
    device: { platform: 'android' },
    night: { isDark: false },
    timing: { tappedAtMs: 61_000, elapsedMsIntoPicker: 0 },
    ...overrides,
  };
}

describe('buildRideReport', () => {
  it('lifts the fix position onto the envelope for the backend to index', () => {
    const envelope = buildRideReport(input())!;
    expect(envelope.lat).toBe(51.5074);
    expect(envelope.lon).toBe(-0.1278);
    expect(envelope.source).toBe('tbt_island');
  });

  it('keeps every top-level block so old rows stay comparable', () => {
    const { payload } = buildRideReport(input())!;
    expect(Object.keys(payload).sort()).toEqual([
      'category', 'client_event_id', 'device', 'device_id', 'extra', 'fix',
      'nav', 'night', 'personal_only', 'profile', 'route', 'schema',
      'simulate', 'source', 'timing',
    ]);
    expect(payload.schema).toBe(1);
  });

  it('carries the fix quality that decides whether a report is trustworthy', () => {
    const { payload } = buildRideReport(input())!;
    expect(payload.fix).toMatchObject({
      h_acc_m: 6,
      alt_m: 18.5,
      speed_mps: 4.2,
      puck_source: 'gps',
      mocked: false,
    });
  });

  it('measures time into the ride from the session start, not the app start', () => {
    const { payload } = buildRideReport(input())!;
    expect(payload.nav.elapsed_ms_into_nav).toBe(60_000);
  });

  it('falls back to the last known position when no fix has arrived', () => {
    const envelope = buildRideReport(
      input({ progress: null, fallbackLocation: [51.5, -0.1] }),
    )!;
    expect(envelope.lat).toBe(51.5);
    expect(envelope.payload.fix.h_acc_m).toBeNull();
  });

  it('returns null rather than a placeless report', () => {
    expect(buildRideReport(input({ progress: null, fallbackLocation: null }))).toBeNull();
  });

  it('propagates the personal-only test flag to both levels', () => {
    const envelope = buildRideReport(input({ personalOnly: true }))!;
    expect(envelope.personal_only).toBe(true);
    expect(envelope.payload.personal_only).toBe(true);
  });
});

describe('withCategory', () => {
  it('patches the category in both places and records the decision time', () => {
    const stub = buildRideReport(input())!;
    const patched = withCategory(stub, 'impassable', 1400);

    expect(patched.category).toBe('impassable');
    expect(patched.payload.category).toBe('impassable');
    expect(patched.payload.timing.elapsed_ms_into_picker).toBe(1400);
    // The id is the idempotency key — patching must never mint a new one.
    expect(patched.client_event_id).toBe(stub.client_event_id);
  });

  it('leaves the original untouched', () => {
    const stub = buildRideReport(input())!;
    withCategory(stub, 'surface', 900);
    expect(stub.category).toBe('general');
  });
});

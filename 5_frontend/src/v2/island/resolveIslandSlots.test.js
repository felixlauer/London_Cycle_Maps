import { resolveIslandSlots, profileWantsLight } from './resolveIslandSlots';

const KM = 1000;

function makeSafest({ trafficM = 0, roughPct = 0 } = {}) {
  return {
    stats: { length_m: 10 * KM, rough_pct: roughPct },
    disruption_typed: trafficM > 0
      ? [{ kind: 'traffic', length_m: trafficM, run_id: 'jam-0', path: [] }]
      : [],
  };
}

const litProfile = { toggles: { light_night: true }, weights: { light_weight: 2 } };
const noLitProfile = { toggles: { light_night: false }, weights: { light_weight: 0 } };

describe('profileWantsLight', () => {
  it('is on with toggle or positive weight, off otherwise', () => {
    expect(profileWantsLight(litProfile)).toBe(true);
    expect(profileWantsLight({ weights: { light_weight: 1 } })).toBe(true);
    expect(profileWantsLight(noLitProfile)).toBe(false);
    expect(profileWantsLight(null)).toBe(false);
  });
});

describe('resolveIslandSlots', () => {
  it('defaults: elevation left, overlay donut right, bars [overlay, cycle]', () => {
    const r = resolveIslandSlots({
      safest: makeSafest(),
      overlayMode: 'green',
      bikeType: 'standard',
    });
    expect(r.left).toEqual({ type: 'elevation' });
    expect(r.right).toEqual({ type: 'donut', modeId: 'green' });
    expect(r.bars).toEqual(['green', 'cycle']);
  });

  it('hills overlay falls back to cycleways donut', () => {
    const r = resolveIslandSlots({
      safest: makeSafest(),
      overlayMode: 'hills',
      bikeType: 'standard',
    });
    expect(r.right.modeId).toBe('cycle');
    expect(r.bars).toEqual(['cycle', 'green']);
  });

  it('traffic takes the right slot; left follows overlay', () => {
    const r = resolveIslandSlots({
      safest: makeSafest({ trafficM: 500 }),
      overlayMode: 'green',
      bikeType: 'standard',
    });
    expect(r.right.modeId).toBe('traffic');
    expect(r.left).toEqual({ type: 'donut', modeId: 'green' });
    expect(r.bars).toEqual(['traffic', 'green']);
  });

  it('traffic + hills overlay: left is elevation chart, not cycleways', () => {
    const r = resolveIslandSlots({
      safest: makeSafest({ trafficM: 500 }),
      overlayMode: 'hills',
      bikeType: 'standard',
    });
    expect(r.right.modeId).toBe('traffic');
    expect(r.left).toEqual({ type: 'elevation' });
  });

  it('traffic + cycle overlay: left stays cycleways donut', () => {
    const r = resolveIslandSlots({
      safest: makeSafest({ trafficM: 500 }),
      overlayMode: 'cycle',
      bikeType: 'standard',
    });
    expect(r.right.modeId).toBe('traffic');
    expect(r.left).toEqual({ type: 'donut', modeId: 'cycle' });
  });

  it('night + wants light: right = light, left follows overlay', () => {
    const r = resolveIslandSlots({
      safest: makeSafest(),
      overlayMode: 'green',
      bikeType: 'standard',
      isDarkOutside: true,
      profile: litProfile,
    });
    expect(r.right.modeId).toBe('light');
    expect(r.left).toEqual({ type: 'donut', modeId: 'green' });
  });

  it('night + traffic + light overlay default: traffic right, light left', () => {
    const r = resolveIslandSlots({
      safest: makeSafest({ trafficM: 400 }),
      overlayMode: 'light',
      bikeType: 'standard',
      isDarkOutside: true,
      profile: litProfile,
    });
    expect(r.right.modeId).toBe('traffic');
    expect(r.left).toEqual({ type: 'donut', modeId: 'light' });
    expect(r.bars).toEqual(['traffic', 'light']);
  });

  it('night, no traffic, overlay = light: right light, left bike default', () => {
    const r = resolveIslandSlots({
      safest: makeSafest(),
      overlayMode: 'light',
      bikeType: 'standard',
      isDarkOutside: true,
      profile: litProfile,
    });
    expect(r.right.modeId).toBe('light');
    expect(r.left).toEqual({ type: 'elevation' });
  });

  it('night without lit preference behaves like day', () => {
    const r = resolveIslandSlots({
      safest: makeSafest(),
      overlayMode: 'green',
      bikeType: 'standard',
      isDarkOutside: true,
      profile: noLitProfile,
    });
    expect(r.right.modeId).toBe('green');
    expect(r.left).toEqual({ type: 'elevation' });
  });

  it.each(['ebike', 'cargo'])('%s: left cycleways, no elevation', (bike) => {
    const r = resolveIslandSlots({
      safest: makeSafest(),
      overlayMode: 'green',
      bikeType: bike,
    });
    expect(r.left).toEqual({ type: 'donut', modeId: 'cycle' });
    expect(r.right.modeId).toBe('green');
  });

  it('power bike with cycle overlay: right stays cycle, left = attractions', () => {
    const r = resolveIslandSlots({
      safest: makeSafest(),
      overlayMode: 'cycle',
      bikeType: 'ebike',
    });
    expect(r.right.modeId).toBe('cycle');
    expect(r.left).toEqual({ type: 'donut', modeId: 'green' });
    expect(r.bars).toEqual(['cycle', 'green']);
  });

  it('road bike + rough surface: left = surface donut', () => {
    const r = resolveIslandSlots({
      safest: makeSafest({ roughPct: 12 }),
      overlayMode: 'green',
      bikeType: 'road',
    });
    expect(r.left).toEqual({ type: 'donut', modeId: 'surface' });
  });

  it('road bike + rough but surface already right: left = elevation', () => {
    const r = resolveIslandSlots({
      safest: makeSafest({ roughPct: 12 }),
      overlayMode: 'surface',
      bikeType: 'road',
    });
    expect(r.right.modeId).toBe('surface');
    expect(r.left).toEqual({ type: 'elevation' });
  });

  it('road bike without rough surface: left = elevation', () => {
    const r = resolveIslandSlots({
      safest: makeSafest({ roughPct: 0 }),
      overlayMode: 'green',
      bikeType: 'road',
    });
    expect(r.left).toEqual({ type: 'elevation' });
  });

  it('bars never duplicate', () => {
    const r = resolveIslandSlots({
      safest: makeSafest(),
      overlayMode: 'cycle',
      bikeType: 'standard',
    });
    expect(r.bars[0]).not.toBe(r.bars[1]);
    expect(r.bars.slice(0, 2)).toEqual(['cycle', 'green']);
  });

  it('adds a third bar chart when budget allows', () => {
    const safest = {
      stats: { length_m: 10000, rough_pct: 8 },
      disruption_typed: [{ kind: 'traffic', length_m: 400, run_id: 'j0', path: [] }],
      cycle_typed: [
        { kind: 'segregated', length_m: 1000, path: [] },
        { kind: 'tfl', length_m: 500, path: [] },
      ],
      green_typed: [
        { kind: 'park', length_m: 800, path: [] },
        { kind: 'river', length_m: 200, path: [] },
      ],
      surface_typed: [{ kind: 'rough', length_m: 300, path: [] }],
    };
    const r = resolveIslandSlots({
      safest,
      overlayMode: 'green',
      bikeType: 'standard',
    });
    expect(r.bars[0]).toBe('traffic');
    expect(r.bars[1]).toBe('green');
    expect(r.bars.length).toBeGreaterThanOrEqual(3);
    expect(r.bars[2]).toBe('cycle');
  });
});

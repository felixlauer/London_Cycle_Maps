import type { NavigationPayload, NavStep } from './types';

export type FlatStep = {
  key: string;
  legIndex: number;
  stepIndex: number;
  instruction: string;
  name: string;
  distance: number;
  type?: string;
  modifier?: string | null;
  bearingBefore?: number | null;
  bearingAfter?: number | null;
  isArrival: boolean;
};

function instructionFor(step: NavStep): string {
  const raw = step.maneuver?.instruction?.trim();
  if (raw) return raw;
  const name = step.name?.trim();
  return name ? `Continue on ${name}` : 'Continue';
}

/** One list for the banner / step list — legs are an implementation detail there. */
export function flattenNavSteps(nav: NavigationPayload | null | undefined): FlatStep[] {
  const legs = nav?.legs || [];
  const out: FlatStep[] = [];
  legs.forEach((leg, legIndex) => {
    (leg.steps || []).forEach((step, stepIndex) => {
      out.push({
        key: `${legIndex}-${stepIndex}`,
        legIndex,
        stepIndex,
        instruction: instructionFor(step),
        name: step.name || '',
        distance: Number(step.distance) || 0,
        type: step.maneuver?.type,
        modifier: step.maneuver?.modifier,
        bearingBefore: step.maneuver?.bearing_before,
        bearingAfter: step.maneuver?.bearing_after,
        isArrival: (step.maneuver?.type || '').toLowerCase() === 'arrive',
      });
    });
  });
  return out;
}

export function flatIndexOf(steps: FlatStep[], legIndex: number, stepIndex: number): number {
  const found = steps.findIndex((s) => s.legIndex === legIndex && s.stepIndex === stepIndex);
  return found >= 0 ? found : 0;
}

/**
 * Vias already passed drop out of a reroute request — the rider is past them.
 * Leg N of the engine route corresponds to via N (legs = vias + 1).
 */
export function remainingViaIndices(legIndex: number, viaCount: number): number[] {
  const out: number[] = [];
  for (let i = legIndex; i < viaCount; i += 1) out.push(i);
  return out;
}

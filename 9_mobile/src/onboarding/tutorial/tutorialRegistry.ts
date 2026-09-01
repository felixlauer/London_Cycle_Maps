/**
 * Anchor registry for spotlight tutorial — measureInWindow by id.
 */
import type { RefObject } from 'react';
import type { View } from 'react-native';

export type TutorialCutoutOpts = {
  ring?: boolean;
  pad?: number;
  capsule?: boolean;
  ringColor?: string | null;
  /** Corner radius when not capsule (e.g. expanded island = 20). */
  radius?: number;
};

export type MeasuredCutout = {
  top: number;
  left: number;
  width: number;
  height: number;
  rx: number;
  ring: boolean;
  ringColor: string | null;
};

type Entry = {
  ref: RefObject<View | null>;
  opts: TutorialCutoutOpts;
};

const anchors = new Map<string, Entry>();
const listeners = new Set<() => void>();

export function registerTutorialAnchor(
  id: string,
  ref: RefObject<View | null>,
  opts: TutorialCutoutOpts = {},
) {
  anchors.set(id, { ref, opts });
  notify();
  return () => {
    const cur = anchors.get(id);
    if (cur?.ref === ref) anchors.delete(id);
    notify();
  };
}

export function bumpTutorialAnchors() {
  notify();
}

function notify() {
  listeners.forEach((l) => l());
}

export function subscribeTutorialAnchors(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function measureRef(
  ref: RefObject<View | null>,
  opts: TutorialCutoutOpts,
): Promise<MeasuredCutout | null> {
  return new Promise((resolve) => {
    const node = ref.current;
    if (!node || typeof node.measureInWindow !== 'function') {
      resolve(null);
      return;
    }
    node.measureInWindow((x, y, width, height) => {
      if (!(width > 0 && height > 0)) {
        resolve(null);
        return;
      }
      const pad = opts.pad ?? 0;
      const capsule = Boolean(opts.capsule);
      const radius = opts.radius ?? 12;
      let rx: number;
      if (capsule || radius >= 999) {
        // True circle / capsule — match the shorter side exactly.
        rx = Math.min(width, height) / 2 + pad;
      } else {
        // Match the control's corner radius; bump slightly so the SVG hole
        // clears the 2px ring (ring radii looked larger than the mask).
        rx = radius < 1 ? Math.min(14, Math.min(width, height) / 2) : radius + 1;
        rx = Math.min(rx + pad, (width + pad * 2) / 2, (height + pad * 2) / 2);
      }
      resolve({
        top: Math.max(0, y - pad),
        left: Math.max(0, x - pad),
        width: width + pad * 2,
        height: height + pad * 2,
        rx,
        ring: opts.ring !== false,
        ringColor: opts.ringColor ?? null,
      });
    });
  });
}

export async function measureTutorialAnchors(
  ids: { id: string; opts?: TutorialCutoutOpts }[],
): Promise<MeasuredCutout[]> {
  const out: MeasuredCutout[] = [];
  for (const spec of ids) {
    const entry = anchors.get(spec.id);
    if (!entry) continue;
    const measured = await measureRef(entry.ref, { ...entry.opts, ...spec.opts });
    if (measured) out.push(measured);
  }
  return out;
}

export function hasTutorialAnchor(id: string) {
  return anchors.has(id);
}

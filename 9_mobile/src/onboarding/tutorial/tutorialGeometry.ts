import type { MeasuredCutout } from './tutorialRegistry';

export const ROUTE_PAD = 14;
export const MARKER_PAD = 22;

export function pointInCutout(x: number, y: number, c: MeasuredCutout) {
  return x >= c.left && x <= c.left + c.width && y >= c.top && y <= c.top + c.height;
}

export function rectsOverlap(
  a: { top: number; left: number; width: number; height: number },
  b: { top: number; left: number; width: number; height: number },
  margin = 8,
) {
  return !(
    a.left + a.width + margin < b.left
    || b.left + b.width + margin < a.left
    || a.top + a.height + margin < b.top
    || b.top + b.height + margin < a.top
  );
}

/** Shrink route bbox so it doesn't collide with island / overlay rings. */
export function clipRouteAwayFromChrome(
  route: MeasuredCutout,
  blockers: MeasuredCutout[],
  gap = 12,
): MeasuredCutout | null {
  // Prefer keeping the full route hole; overlapping chrome holes are separated
  // later via isolateCutouts. Aggressive clipping left a stub that stopped
  // short of route segments under the island / controls.
  void blockers;
  void gap;
  if (!route || route.width < 24 || route.height < 24) return null;
  return route;
}

/**
 * Build opaque blocker rects covering the screen except the given holes.
 * Used so MapView (native gestures) can't be used outside the spotlight.
 */
export function blockerRectsForHoles(
  vw: number,
  vh: number,
  holes: MeasuredCutout[],
): { top: number; left: number; width: number; height: number }[] {
  if (!holes.length) {
    return [{ top: 0, left: 0, width: vw, height: vh }];
  }

  const ys = new Set<number>([0, vh]);
  holes.forEach((h) => {
    ys.add(Math.max(0, Math.min(vh, h.top)));
    ys.add(Math.max(0, Math.min(vh, h.top + h.height)));
  });
  const yBands = [...ys].sort((a, b) => a - b);
  const out: { top: number; left: number; width: number; height: number }[] = [];

  for (let i = 0; i < yBands.length - 1; i += 1) {
    const y0 = yBands[i];
    const y1 = yBands[i + 1];
    const bandH = y1 - y0;
    if (bandH <= 0) continue;

    const midY = (y0 + y1) / 2;
    const active = holes
      .filter((h) => midY >= h.top && midY < h.top + h.height)
      .map((h) => ({
        left: Math.max(0, h.left),
        right: Math.min(vw, h.left + h.width),
      }))
      .filter((h) => h.right > h.left)
      .sort((a, b) => a.left - b.left);

    // Merge overlapping hole intervals in this band.
    const merged: { left: number; right: number }[] = [];
    active.forEach((iv) => {
      const last = merged[merged.length - 1];
      if (!last || iv.left > last.right) merged.push({ ...iv });
      else last.right = Math.max(last.right, iv.right);
    });

    let x = 0;
    merged.forEach((iv) => {
      if (iv.left > x) {
        out.push({ top: y0, left: x, width: iv.left - x, height: bandH });
      }
      x = Math.max(x, iv.right);
    });
    if (x < vw) {
      out.push({ top: y0, left: x, width: vw - x, height: bandH });
    }
  }

  return out.filter((r) => r.width >= 1 && r.height >= 1);
}

export function roundedRectPath(c: MeasuredCutout) {
  const { left: x, top: y, width: w, height: h } = c;
  let rx = Math.min(c.rx || 12, w / 2, h / 2);
  if (rx < 0) rx = 0;
  // Arc corners — Q approximations self-intersect on capsules/circles and
  // evenodd then paints a dark blob inside the hole.
  if (rx <= 0.5) {
    return `M${x},${y}H${x + w}V${y + h}H${x}Z`;
  }
  return [
    `M${x + rx},${y}`,
    `H${x + w - rx}`,
    `A${rx},${rx} 0 0 1 ${x + w},${y + rx}`,
    `V${y + h - rx}`,
    `A${rx},${rx} 0 0 1 ${x + w - rx},${y + h}`,
    `H${x + rx}`,
    `A${rx},${rx} 0 0 1 ${x},${y + h - rx}`,
    `V${y + rx}`,
    `A${rx},${rx} 0 0 1 ${x + rx},${y}`,
    'Z',
  ].join('');
}

/**
 * Evenodd cancels overlapping holes (dark blotches). Nudge later cutouts
 * apart from earlier ones so holes stay clear.
 */
export function isolateCutouts(cutouts: MeasuredCutout[], gap = 4): MeasuredCutout[] {
  const out: MeasuredCutout[] = [];
  cutouts.forEach((raw) => {
    if (!raw || raw.width < 2 || raw.height < 2) return;
    let c = { ...raw };
    out.forEach((prev) => {
      if (!rectsOverlap(c, prev, 0)) return;
      // Prefer shrinking the later cutout away from the earlier one.
      const overlapLeft = (prev.left + prev.width) - c.left;
      const overlapRight = (c.left + c.width) - prev.left;
      const overlapTop = (prev.top + prev.height) - c.top;
      const overlapBottom = (c.top + c.height) - prev.top;
      const minX = Math.min(overlapLeft, overlapRight);
      const minY = Math.min(overlapTop, overlapBottom);
      if (minX <= minY) {
        if (overlapLeft <= overlapRight) {
          const nextLeft = prev.left + prev.width + gap;
          c.width = Math.max(0, c.left + c.width - nextLeft);
          c.left = nextLeft;
        } else {
          c.width = Math.max(0, Math.min(c.width, prev.left - gap - c.left));
        }
      } else if (overlapTop <= overlapBottom) {
        const nextTop = prev.top + prev.height + gap;
        c.height = Math.max(0, c.top + c.height - nextTop);
        c.top = nextTop;
      } else {
        c.height = Math.max(0, Math.min(c.height, prev.top - gap - c.top));
      }
    });
    if (c.width >= 8 && c.height >= 8) {
      c.rx = Math.min(c.rx, c.width / 2, c.height / 2);
      out.push(c);
    }
  });
  return out;
}

export function buildMaskPath(vw: number, vh: number, cutouts: MeasuredCutout[]) {
  const outer = `M0,0H${vw}V${vh}H0Z`;
  const holes = cutouts.map(roundedRectPath).join('');
  return outer + holes;
}

type AnchorRect = {
  top: number;
  left: number;
  width: number;
  height: number;
  bottom: number;
  right: number;
};

export function placeTooltip(
  anchor: AnchorRect | null,
  placement: string | undefined,
  tipW: number,
  tipH: number,
  vw: number,
  vh: number,
  avoidRects: MeasuredCutout[] = [],
) {
  const gap = 18;
  let top: number;
  let left: number;

  if (placement === 'avoid-route' && avoidRects[0]) {
    const routeCutout = avoidRects[0];
    const below = routeCutout.top + routeCutout.height + gap;
    if (below + tipH < vh - 56) {
      top = below;
      left = routeCutout.left + routeCutout.width / 2 - tipW / 2;
    } else if (routeCutout.top - tipH - gap > 16) {
      top = routeCutout.top - tipH - gap;
      left = routeCutout.left + routeCutout.width / 2 - tipW / 2;
    } else {
      top = Math.max(16, vh - tipH - 72);
      left = Math.max(16, (vw - tipW) / 2);
    }
  } else if (placement === 'center' || !anchor) {
    top = Math.max(16, (vh - tipH) / 2);
    left = Math.max(16, (vw - tipW) / 2);
  } else if (placement === 'bottom') {
    top = anchor.bottom + gap;
    left = anchor.left + anchor.width / 2 - tipW / 2;
  } else if (placement === 'screen-bottom') {
    top = Math.max(16, vh - tipH - 28);
    left = Math.max(16, (vw - tipW) / 2);
  } else if (placement === 'top') {
    top = anchor.top - tipH - gap;
    left = anchor.left + anchor.width / 2 - tipW / 2;
  } else if (placement === 'left') {
    top = anchor.top + anchor.height / 2 - tipH / 2;
    left = anchor.left - tipW - gap;
  } else {
    top = anchor.top + anchor.height / 2 - tipH / 2;
    left = anchor.right + gap;
  }

  if (left < 16) left = 16;
  if (left + tipW > vw - 16) left = Math.max(16, vw - tipW - 16);

  const tipRect = () => ({ top, left, width: tipW, height: tipH });

  const pushClear = () => {
    let guard = 0;
    while (guard < 6 && avoidRects.some((c) => rectsOverlap(tipRect(), c))) {
      const hit = avoidRects.find((c) => rectsOverlap(tipRect(), c));
      if (!hit) break;
      top = hit.top + hit.height + gap;
      if (top + tipH > vh - 56) {
        top = Math.max(16, hit.top - tipH - gap);
      }
      if (top < 16) top = 16;
      if (top + tipH > vh - 16) {
        top = Math.max(16, vh - tipH - 72);
        left = Math.max(16, (vw - tipW) / 2);
        break;
      }
      guard += 1;
    }
  };

  if (placement === 'bottom' && anchor) {
    if (top + tipH > vh - 16) {
      top = Math.min(vh - tipH - 16, Math.max(16, anchor.top));
      left = Math.min(vw - tipW - 16, anchor.right + gap);
      if (left < 16) left = Math.max(16, anchor.left - tipW - gap);
    }
  } else {
    if (top + tipH > vh - 16) top = Math.max(16, (anchor?.top || tipH) - tipH - gap);
    if (top < 16) top = Math.min(vh - tipH - 16, (anchor?.bottom || 0) + gap);
  }

  pushClear();
  return { top, left };
}

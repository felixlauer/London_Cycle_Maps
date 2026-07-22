/**
 * Single continuous SVG path for the overlay mode pill.
 * Same command topology always (for Motion morphing).
 *
 * edgeMode:
 *  - 'middle' — top + bottom concave fillets
 *  - 'top'    — no top fillet; arm top blends into pill top outer radius
 *  - 'bottom' — no bottom fillet; arm bottom blends into pill bottom outer radius
 */

const K = 0.5522847498;

function joinCmds(parts) {
  return parts.join(' ');
}

/** Cubic that is effectively a point (morphing placeholder). */
function noopC(x, y) {
  return `C ${x} ${y} ${x} ${y} ${x} ${y}`;
}

/**
 * @param {object} opts
 * @param {'top'|'middle'|'bottom'} [opts.edgeMode]
 */
export function buildOverlayPillPath({
  spineW,
  spineH,
  armExtent,
  armCy,
  armH,
  filletR = 12,
  endR,
  edgeMode = 'middle',
}) {
  const W = spineW;
  const H = spineH;
  const R = endR != null ? endR : W / 2;

  const extent = Math.max(0.02, armExtent);
  const t = Math.min(1, extent / 52);
  // Near collapse, always use middle capsule so top/bottom edge paths
  // don't leave sharp / truncated left corners when the arm is gone.
  const edgeOpen = t > 0.1;
  const isTop = edgeMode === 'top' && edgeOpen;
  const isBottom = edgeMode === 'bottom' && edgeOpen;

  // Arm band grows with extent; top/bottom pins flush to capsule ends
  const halfWant = 0.02 + t * (armH / 2 - 0.02);
  let aTop = isTop ? 0 : armCy - halfWant;
  let aBot = isBottom ? H : armCy + halfWant;

  if (!isTop && !isBottom) {
    const minY = R + 0.5;
    const maxY = H - R - 0.5;
    if (aTop < minY) {
      aBot += minY - aTop;
      aTop = minY;
    }
    if (aBot > maxY) {
      aTop -= aBot - maxY;
      aBot = maxY;
    }
    aTop = Math.max(minY, Math.min(aTop, maxY));
    aBot = Math.max(aTop + 0.04, Math.min(maxY, aBot));
  } else if (isTop) {
    aTop = 0;
    aBot = Math.min(H - R - 0.5, Math.max(armH * t, aTop + 0.04 + t * (armH - 0.04)));
    // Prefer natural arm height from cy when expanded
    if (t > 0.2) {
      aBot = Math.min(H - R - 0.5, Math.max(aBot, armCy + halfWant));
    }
  } else if (isBottom) {
    aBot = H;
    aTop = Math.max(R + 0.5, Math.min(armCy - halfWant, H - 0.04));
    if (t > 0.2) {
      aTop = Math.max(R + 0.5, Math.min(aTop, armCy - halfWant));
    }
    if (aTop > aBot - 0.04) aTop = aBot - 0.04;
  }

  const midY = (aTop + aBot) / 2;
  const halfH = Math.max(0.02, (aBot - aTop) / 2);

  // Fillet radii — zeroed on the omitted side (still emit cubics for topology)
  let fBot = isBottom ? 0.02 : Math.max(0.02, Math.min(filletR, halfH * 0.85, extent * 0.45) * t);
  let fTop = isTop ? 0.02 : Math.max(0.02, Math.min(filletR, halfH * 0.85, extent * 0.45) * t);

  const capR = halfH;
  // Use the larger fillet for inner-length so arm end lines up
  const fJoin = Math.max(fTop, fBot);
  const inner = Math.max(0, extent - capR - (isTop || isBottom ? Math.min(fTop, fBot) : fJoin));
  // For edge modes one fillet is omitted — arm reaches closer to x=0 on that side
  const armLeftInner = -(inner + (isTop ? fBot : isBottom ? fTop : fJoin));

  const parts = [];

  // 1–2 top edge of spine
  parts.push(`M ${R} 0`);
  parts.push(`L ${W - R} 0`);
  // 3 top-right corner
  parts.push(`C ${W - R + K * R} 0 ${W} ${R - K * R} ${W} ${R}`);
  // 4 right side
  parts.push(`L ${W} ${H - R}`);
  // 5 bottom-right corner
  parts.push(`C ${W} ${H - R + K * R} ${W - R + K * R} ${H} ${W - R} ${H}`);

  if (isBottom) {
    // Bottom edge continues straight into the arm (no bottom-left corner / no bottom fillet)
    // 6 along bottom to end-cap
    parts.push(`L ${armLeftInner} ${H}`);
    // 7–8 noop placeholders (replaced bottom-left arc + approach)
    parts.push(noopC(armLeftInner, H));
    parts.push(`L ${armLeftInner} ${H}`);
    // 9 noop bottom fillet
    parts.push(noopC(armLeftInner, H));
    // 10 already at end-cap bottom
    parts.push(`L ${armLeftInner} ${aBot}`);
  } else {
    // 6 bottom edge to bottom-left corner start
    parts.push(`L ${R} ${H}`);
    // 7 bottom-left corner → (0, H-R)
    parts.push(`C ${R - K * R} ${H} 0 ${H - R + K * R} 0 ${H - R}`);
    // 8 up to bottom fillet
    parts.push(`L 0 ${aBot + fBot}`);
    // 9 bottom concave fillet → (-fBot, aBot)
    parts.push(
      `C 0 ${aBot + fBot - K * fBot} ${-fBot + K * fBot} ${aBot} ${-fBot} ${aBot}`,
    );
    // 10 along arm bottom to end-cap
    parts.push(`L ${armLeftInner} ${aBot}`);
  }

  // 11–12 end-cap semicircle (bottom → top)
  {
    const cx = armLeftInner;
    const cy = midY;
    const rr = halfH;
    parts.push(
      `C ${cx - K * rr} ${aBot} ${cx - rr} ${cy + K * rr} ${cx - rr} ${cy}`,
    );
    parts.push(
      `C ${cx - rr} ${cy - K * rr} ${cx - K * rr} ${aTop} ${cx} ${aTop}`,
    );
  }

  if (isTop) {
    // Arm top continues straight into pill top (no top fillet / no top-left corner)
    // 13 along y=0 to start
    parts.push(`L ${R} 0`);
    // 14–17 topology placeholders
    parts.push(noopC(R, 0));
    parts.push(`L ${R} 0`);
    parts.push(`L ${R} 0`);
    parts.push(noopC(R, 0));
  } else {
    // 13 along arm top to top fillet
    parts.push(`L ${-fTop} ${aTop}`);
    // 14 top concave fillet → (0, aTop-fTop)
    parts.push(
      `C ${-fTop + K * fTop} ${aTop} 0 ${aTop - fTop + K * fTop} 0 ${aTop - fTop}`,
    );
    // 15–16 up left side to top-left corner
    parts.push(`L 0 ${aTop - fTop}`);
    parts.push(`L 0 ${R}`);
    // 17 top-left corner → (R, 0)
    parts.push(`C 0 ${R - K * R} ${R - K * R} 0 ${R} 0`);
  }

  parts.push('Z');
  return joinCmds(parts);
}

export function overlayPillMetrics(count, { compact = false } = {}) {
  // Keep spine width identical to .map-ctl__nav (44px) so right edges match.
  const spineW = 44;
  const pad = compact ? 3 : 4;
  const btnH = compact ? 34 : 36;
  const gap = 2;
  const spineH = pad * 2 + count * btnH + Math.max(0, count - 1) * gap;
  const armH = btnH;
  const filletR = compact ? 11 : 12;
  const maxArmExtent = 120;
  const cornerR = compact ? 15 : 16;
  return {
    spineW, pad, btnH, gap, spineH, armH, filletR, maxArmExtent, cornerR,
    iconSize: compact ? 15 : 18,
  };
}

export function armCenterY(index, { pad, btnH, gap }) {
  return pad + index * (btnH + gap) + btnH / 2;
}

/**
 * Arm length for a label. Top/bottom edge modes need less width — the arm
 * is taller / flush, so the old padding read as empty buffer on the left.
 */
export function armExtentForLabel(label, edgeMode = 'middle') {
  const chars = String(label || '').length;
  const base = Math.min(120, Math.max(72, Math.round(chars * 7.4 + 28)));
  if (edgeMode === 'top' || edgeMode === 'bottom') {
    return Math.max(60, base - 16);
  }
  return base;
}

export function edgeModeForIndex(index, length) {
  if (index <= 0) return 'top';
  if (index >= length - 1) return 'bottom';
  return 'middle';
}

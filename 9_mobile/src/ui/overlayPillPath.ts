/**
 * Single continuous SVG path for the overlay mode pill.
 * Port of web v2/shell/zones/overlayPillPath.js — same command topology always.
 */

const K = 0.5522847498;

function joinCmds(parts: string[]) {
  return parts.join(' ');
}

function noopC(x: number, y: number) {
  return `C ${x} ${y} ${x} ${y} ${x} ${y}`;
}

export type EdgeMode = 'top' | 'middle' | 'bottom';

export function buildOverlayPillPath({
  spineW,
  spineH,
  armExtent,
  armCy,
  armH,
  filletR = 12,
  endR,
  edgeMode = 'middle',
}: {
  spineW: number;
  spineH: number;
  armExtent: number;
  armCy: number;
  armH: number;
  filletR?: number;
  endR?: number;
  edgeMode?: EdgeMode;
}) {
  const W = spineW;
  const H = spineH;
  const R = endR != null ? endR : W / 2;

  const extent = Math.max(0.02, armExtent);
  const t = Math.min(1, extent / 52);
  const edgeOpen = t > 0.1;
  const isTop = edgeMode === 'top' && edgeOpen;
  const isBottom = edgeMode === 'bottom' && edgeOpen;

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

  let fBot = isBottom ? 0.02 : Math.max(0.02, Math.min(filletR, halfH * 0.85, extent * 0.45) * t);
  let fTop = isTop ? 0.02 : Math.max(0.02, Math.min(filletR, halfH * 0.85, extent * 0.45) * t);

  const capR = halfH;
  const fJoin = Math.max(fTop, fBot);
  const inner = Math.max(0, extent - capR - (isTop || isBottom ? Math.min(fTop, fBot) : fJoin));
  const armLeftInner = -(inner + (isTop ? fBot : isBottom ? fTop : fJoin));

  const parts: string[] = [];

  parts.push(`M ${R} 0`);
  parts.push(`L ${W - R} 0`);
  parts.push(`C ${W - R + K * R} 0 ${W} ${R - K * R} ${W} ${R}`);
  parts.push(`L ${W} ${H - R}`);
  parts.push(`C ${W} ${H - R + K * R} ${W - R + K * R} ${H} ${W - R} ${H}`);

  if (isBottom) {
    parts.push(`L ${armLeftInner} ${H}`);
    parts.push(noopC(armLeftInner, H));
    parts.push(`L ${armLeftInner} ${H}`);
    parts.push(noopC(armLeftInner, H));
    parts.push(`L ${armLeftInner} ${aBot}`);
  } else {
    parts.push(`L ${R} ${H}`);
    parts.push(`C ${R - K * R} ${H} 0 ${H - R + K * R} 0 ${H - R}`);
    parts.push(`L 0 ${aBot + fBot}`);
    parts.push(
      `C 0 ${aBot + fBot - K * fBot} ${-fBot + K * fBot} ${aBot} ${-fBot} ${aBot}`,
    );
    parts.push(`L ${armLeftInner} ${aBot}`);
  }

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
    parts.push(`L ${R} 0`);
    parts.push(noopC(R, 0));
    parts.push(`L ${R} 0`);
    parts.push(`L ${R} 0`);
    parts.push(noopC(R, 0));
  } else {
    parts.push(`L ${-fTop} ${aTop}`);
    parts.push(
      `C ${-fTop + K * fTop} ${aTop} 0 ${aTop - fTop + K * fTop} 0 ${aTop - fTop}`,
    );
    parts.push(`L 0 ${aTop - fTop}`);
    parts.push(`L 0 ${R}`);
    parts.push(`C 0 ${R - K * R} ${R - K * R} 0 ${R} 0`);
  }

  parts.push('Z');
  return joinCmds(parts);
}

export function overlayPillMetrics(count: number, { compact = false } = {}) {
  const spineW = compact ? 52 : 44;
  const pad = compact ? 3 : 4;
  const btnH = compact ? 40 : 36;
  const gap = 2;
  const spineH = pad * 2 + count * btnH + Math.max(0, count - 1) * gap;
  const armH = btnH;
  const filletR = compact ? 13 : 12;
  // Wider than web 120 so “Cycleways” (and similar) fits without clipping.
  const maxArmExtent = 148;
  const cornerR = compact ? 17 : 16;
  return {
    spineW,
    pad,
    btnH,
    gap,
    spineH,
    armH,
    filletR,
    maxArmExtent,
    cornerR,
    iconSize: 18,
  };
}

export function armCenterY(index: number, { pad, btnH, gap }: { pad: number; btnH: number; gap: number }) {
  return pad + index * (btnH + gap) + btnH / 2;
}

export function armExtentForLabel(label: string, edgeMode: EdgeMode = 'middle') {
  const chars = String(label || '').length;
  const base = Math.min(148, Math.max(80, Math.round(chars * 8.2 + 36)));
  if (edgeMode === 'top' || edgeMode === 'bottom') {
    return Math.max(68, base - 12);
  }
  return base;
}

export function edgeModeForIndex(index: number, length: number): EdgeMode {
  if (index <= 0) return 'top';
  if (index >= length - 1) return 'bottom';
  return 'middle';
}

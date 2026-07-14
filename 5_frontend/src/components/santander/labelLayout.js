/**
 * Santander pin layout: tip at station; card above or below only.
 * Beak sits under the "|" via --beak-along (px from card left edge to tip).
 * Sides chosen once when candidates load.
 */
const SIDE_ORDER = ['bottom', 'top'];

const CARD_W = 112;
const CARD_H = 38;
const EXP_W = 188;
const EXP_H = 118;
const BEAK_H = 11;
/** Distance from compact card left edge to the "|" character. */
export const BEAK_ALONG_COMPACT = 32;
/** Expanded card: under first separator-ish / left block. */
export const BEAK_ALONG_EXPANDED = 36;

function cardSize(expanded) {
  return expanded ? { w: EXP_W, h: EXP_H } : { w: CARD_W, h: CARD_H };
}

function alongPx(expanded) {
  return expanded ? BEAK_ALONG_EXPANDED : BEAK_ALONG_COMPACT;
}

function rectFor(px, py, side, expanded) {
  const { w, h } = cardSize(expanded);
  const along = alongPx(expanded);
  // tip at (px,py); card left = tip - along
  const left = px - along;
  if (side === 'bottom') {
    const bottom = py - BEAK_H;
    const top = bottom - h;
    return { left, top, right: left + w, bottom };
  }
  const top = py + BEAK_H;
  return { left, top, right: left + w, bottom: top + h };
}

function overlaps(a, b, pad = 8) {
  return !(
    a.right + pad < b.left
    || a.left - pad > b.right
    || a.bottom + pad < b.top
    || a.top - pad > b.bottom
  );
}

/**
 * @returns {Record<string,{side:'top'|'bottom', along:number}>}
 */
export function computeSantanderOffsets(items) {
  const placed = [];
  const out = {};
  for (const item of items) {
    let chosenSide = 'bottom';
    let found = false;
    for (const side of SIDE_ORDER) {
      const r = rectFor(item.px, item.py, side, !!item.expanded);
      if (!placed.some((p) => overlaps(p.rect, r))) {
        chosenSide = side;
        placed.push({ rect: r });
        found = true;
        break;
      }
    }
    if (!found) {
      placed.push({
        rect: rectFor(item.px, item.py, chosenSide, !!item.expanded),
      });
    }
    out[item.id] = {
      side: chosenSide,
      along: alongPx(!!item.expanded),
    };
  }
  return out;
}

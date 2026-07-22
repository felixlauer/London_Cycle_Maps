import React, { useRef, useState } from 'react';
import { ChevronUp } from 'lucide-react';
import ElevationSparkline from './ElevationSparkline';
import ModeDonut from './ModeDonut';
import MetricCell from './MetricCell';
import useMeasure from './useMeasure';
import { islandModeMeta } from './modeData';
import { OVERLAY_KIND_META } from '../map/overlayModes';
import { useIsMobile } from '../hooks/useMediaQuery';
import {
  formatDurationParts,
  formatDistanceParts,
  formatTimeDelta,
  formatDistanceDelta,
} from './metrics';

/** Caption under the donut while a kind is hovered (map or local). */
function donutSegmentCaption(modeId, kind) {
  if (modeId === 'cycle') {
    if (kind === 'segregated') return 'Segregated cycleways';
    if (kind === 'bus_shared') return 'Bus shared cycleways';
    if (kind === 'car_shared') return 'Car shared cycleways';
    if (kind === 'tfl') return 'TfL network';
  }
  if (modeId === 'traffic' && kind === 'traffic') return 'Traffic jam';
  return OVERLAY_KIND_META[kind]?.label || kind;
}

const DONUT = 56;
/** Landscape sparkline — width fills the cell; height tracks width. */
const SPARK_ASPECT = 0.42;
const SPARK_SIDE_PAD = 10;
const SPARK_FALLBACK_W = 72;

function ContentSlot({ slot, safest, externalHover, onHoverChange }) {
  const [localKind, setLocalKind] = useState(null);
  const [slotRef, { width: slotW }] = useMeasure();
  const modeId = slot?.modeId;
  const meta = modeId ? islandModeMeta(modeId) : null;
  const activeKind = localKind
    || (modeId && externalHover
      && (externalHover.modeId == null || externalHover.modeId === modeId)
      ? externalHover.kind
      : null);
  const caption = activeKind && modeId
    ? donutSegmentCaption(modeId, activeKind)
    : (meta?.label || modeId);

  if (!slot) return null;
  if (slot.type === 'elevation') {
    const available = slotW > 0 ? slotW : SPARK_FALLBACK_W;
    const plotW = Math.max(40, Math.floor(available - SPARK_SIDE_PAD * 2));
    const plotH = Math.max(22, Math.round(plotW * SPARK_ASPECT));
    return (
      <div className="island-slot island-slot--elevation" ref={slotRef}>
        <div className="island-slot__visual island-slot__visual--spark">
          <ElevationSparkline
            profile={safest?.elevation_profile}
            width={plotW}
            height={plotH}
          />
        </div>
        <span className="island-slot__caption">Elevation</span>
      </div>
    );
  }

  return (
    <div className="island-slot">
      <div className="island-slot__visual" style={{ width: DONUT, height: DONUT }}>
        <ModeDonut
          safest={safest}
          modeId={modeId}
          size={DONUT}
          strokeWidth={5.5}
          externalHover={externalHover}
          onHoverChange={(seg) => {
            setLocalKind(seg?.kind || null);
            onHoverChange?.(seg);
          }}
        />
      </div>
      <span className="island-slot__caption">{caption}</span>
    </div>
  );
}

/**
 * Collapsed island — four equal cells.
 * Mobile: expand via swipe-up or chevron only (not tap-anywhere).
 */
export default function CollapsedIsland({
  safest,
  fastest,
  slots,
  units,
  onExpand,
  legCount = 1,
  externalHover = null,
  onSegmentHover,
}) {
  const isMobile = useIsMobile();
  const touchStartY = useRef(null);
  const sStats = safest?.stats || {};
  const fStats = fastest?.stats || {};
  const multi = legCount > 1;

  const handleExpandClick = (e) => {
    if (isMobile) {
      // Mobile: only the chevron expands (handled separately)
      if (!e.target.closest?.('.island-collapsed__chevron-btn')) return;
    }
    onExpand();
  };

  return (
    <div
      className={`island-collapsed${multi ? ' is-multi' : ''}${isMobile ? ' is-mobile' : ''}`}
      role={isMobile ? 'group' : 'button'}
      tabIndex={isMobile ? undefined : 0}
      aria-label={isMobile ? 'Route summary' : 'Expand route analysis'}
      onClick={isMobile ? undefined : handleExpandClick}
      onKeyDown={isMobile ? undefined : (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onExpand();
        }
      }}
      onTouchStart={(e) => {
        if (!isMobile) return;
        touchStartY.current = e.changedTouches[0].clientY;
      }}
      onTouchEnd={(e) => {
        if (!isMobile || touchStartY.current == null) return;
        const dy = e.changedTouches[0].clientY - touchStartY.current;
        touchStartY.current = null;
        if (dy < -40) onExpand();
      }}
    >
      <div className="island-collapsed__grid">
        <div className="island-collapsed__cell">
          <MetricCell
            ariaLabel="Trip time"
            parts={formatDurationParts(sStats.duration_min)}
            delta={isMobile ? null : formatTimeDelta(sStats.duration_min, fStats.duration_min, { compare: 'non-optimised' })}
            twoLineDelta={!isMobile}
          />
        </div>
        <div className="island-collapsed__cell">
          <MetricCell
            ariaLabel="Trip distance"
            parts={formatDistanceParts(sStats.length_m, units)}
            delta={isMobile ? null : formatDistanceDelta(sStats.length_m, fStats.length_m, units, { compare: 'non-optimised' })}
            twoLineDelta={!isMobile}
          />
        </div>
        <div className="island-collapsed__cell">
          <ContentSlot
            slot={slots.left}
            safest={safest}
            externalHover={externalHover}
            onHoverChange={onSegmentHover}
          />
        </div>
        <div className="island-collapsed__cell">
          <ContentSlot
            slot={slots.right}
            safest={safest}
            externalHover={externalHover}
            onHoverChange={onSegmentHover}
          />
        </div>
      </div>

      <button
        type="button"
        className="island-collapsed__chevron-btn"
        data-tutorial="island-expand"
        aria-label="Expand route analysis"
        onClick={(e) => {
          e.stopPropagation();
          onExpand();
        }}
      >
        <ChevronUp size={16} strokeWidth={2.2} aria-hidden />
      </button>
    </div>
  );
}

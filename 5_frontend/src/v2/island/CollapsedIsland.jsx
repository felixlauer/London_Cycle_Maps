import React, { useState } from 'react';
import { ChevronUp } from 'lucide-react';
import ElevationSparkline from './ElevationSparkline';
import ModeDonut from './ModeDonut';
import MetricCell from './MetricCell';
import { islandModeMeta } from './modeData';
import { OVERLAY_KIND_META } from '../map/overlayModes';
import { formatCollapsedLegParts } from './IslandLegPager';
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

function ContentSlot({ slot, safest, externalHover, onHoverChange }) {
  const [localKind, setLocalKind] = useState(null);
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
    return (
      <div className="island-slot">
        <ElevationSparkline profile={safest?.elevation_profile} width={120} height={44} />
        <span className="island-slot__caption">Elevation</span>
      </div>
    );
  }

  return (
    <div className="island-slot">
      <ModeDonut
        safest={safest}
        modeId={modeId}
        size={56}
        strokeWidth={5.5}
        externalHover={externalHover}
        onHoverChange={(seg) => {
          setLocalKind(seg?.kind || null);
          onHoverChange?.(seg);
        }}
      />
      <span className="island-slot__caption">{caption}</span>
    </div>
  );
}

/**
 * Collapsed island — four equal cells; multi-leg shows part caption + dots.
 */
export default function CollapsedIsland({
  safest,
  fastest,
  slots,
  units,
  onExpand,
  legCount = 1,
  activeLegIndex = 0,
  onChangeLeg,
  viaCount = 0,
  externalHover = null,
  onSegmentHover,
}) {
  const sStats = safest?.stats || {};
  const fStats = fastest?.stats || {};
  const multi = legCount > 1;
  const legParts = multi
    ? formatCollapsedLegParts(activeLegIndex, legCount, viaCount)
    : null;

  return (
    <div
      className={`island-collapsed${multi ? ' is-multi' : ''}`}
      role="button"
      tabIndex={0}
      aria-label="Expand route analysis"
      onClick={(e) => {
        if (e.target.closest?.('.island-collapsed__legs')) return;
        onExpand();
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onExpand();
        }
      }}
    >
      <div className="island-collapsed__cell">
        <MetricCell
          ariaLabel="Trip time"
          parts={formatDurationParts(sStats.duration_min)}
          delta={formatTimeDelta(sStats.duration_min, fStats.duration_min)}
        />
      </div>
      <div className="island-collapsed__cell">
        <MetricCell
          ariaLabel="Trip distance"
          parts={formatDistanceParts(sStats.length_m, units)}
          delta={formatDistanceDelta(sStats.length_m, fStats.length_m, units)}
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

      {legParts && (
        <div
          className="island-collapsed__legs"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        >
          <span className="island-collapsed__leg-caption island-collapsed__leg-caption--left">
            {legParts.viewing}
          </span>
          <div className="island-collapsed__dots" role="tablist" aria-label="Route parts">
            {Array.from({ length: legCount }, (_, i) => (
              <button
                key={i}
                type="button"
                role="tab"
                aria-selected={i === activeLegIndex}
                className={`island-collapsed__dot${i === activeLegIndex ? ' is-active' : ''}`}
                aria-label={`Show part ${i + 1}`}
                onClick={(e) => {
                  e.stopPropagation();
                  onChangeLeg?.(i);
                }}
              />
            ))}
          </div>
          <span className="island-collapsed__leg-caption island-collapsed__leg-caption--right">
            {legParts.part}
          </span>
        </div>
      )}

      <span className="island-collapsed__chevron" aria-hidden>
        <ChevronUp size={16} strokeWidth={2.2} />
      </span>
    </div>
  );
}

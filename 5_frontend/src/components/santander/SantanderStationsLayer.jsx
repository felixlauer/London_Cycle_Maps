import React, { useEffect, useState } from 'react';
import { Marker, useMap } from 'react-map-gl/mapbox';
import { Bike, Footprints } from 'lucide-react';
import {
  computeSantanderOffsets,
  BEAK_ALONG_COMPACT,
  BEAK_ALONG_EXPANDED,
} from './labelLayout';
import './santander.css';

function StationCard({
  station,
  expanded,
  side,
  along,
  confirmLabel,
  showConfirm,
  availabilityNeed,
  onExpand,
  onConfirm,
}) {
  const unavailable = availabilityNeed === 'docks'
    ? !(station.nb_empty > 0)
    : !(station.nb_bikes > 0);
  const walkMin = station.walk_duration_min ?? station.walk_estimate_min ?? 1;
  const walkLabel = station.walk_duration_min != null ? 'walk' : 'estimated walk';
  const alongPx = along ?? (expanded ? BEAK_ALONG_EXPANDED : BEAK_ALONG_COMPACT);

  const handleClick = (e) => {
    e.stopPropagation();
    if (e.target?.closest?.('[data-santander-confirm]')) {
      e.preventDefault();
      onConfirm?.(station);
      return;
    }
    onExpand?.(station);
  };

  return (
    <div
      className="santander-anchor"
      style={{ '--beak-along': `${alongPx}px` }}
      onClick={handleClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') handleClick(e);
      }}
      role="button"
      tabIndex={0}
    >
      <div className={`santander-pin-unit side-${side || 'bottom'}`}>
        <div
          className={
            `santander-card` +
            (unavailable ? ' is-empty' : '') +
            (expanded ? ' is-expanded' : '')
          }
        >
          {expanded ? (
            <>
              <div className="santander-card-top">
                <div className="santander-breakdown">
                  <div className="santander-bd-item">
                    <div className="santander-bd-num">{station.nb_standard}</div>
                    <div className="santander-bd-label">regular</div>
                  </div>
                  <div className="santander-bd-item">
                    <div className="santander-bd-num">{station.nb_ebikes}</div>
                    <div className="santander-bd-label">electric</div>
                  </div>
                  <div className="santander-bd-item">
                    <div className="santander-bd-num is-muted">{station.nb_empty}</div>
                    <div className="santander-bd-label">empty</div>
                  </div>
                </div>
                <div className={`santander-bike-badge${unavailable ? ' is-empty' : ''}`}>
                  <Bike size={18} strokeWidth={2.25} aria-hidden />
                </div>
              </div>
              <div className="santander-walk-row">
                <Footprints
                  className="santander-walk-icon"
                  size={28}
                  strokeWidth={2}
                  aria-hidden
                />
                <div className="santander-walk-text">
                  <strong>{walkMin} minutes</strong>
                  <span>{walkLabel}</span>
                </div>
                {showConfirm && confirmLabel && (
                  <button
                    type="button"
                    className="santander-confirm-btn"
                    data-santander-confirm="1"
                    onClick={(e) => {
                      e.stopPropagation();
                      onConfirm?.(station);
                    }}
                  >
                    {confirmLabel}
                  </button>
                )}
              </div>
            </>
          ) : (
            <>
              <div className="santander-counts">
                {station.nb_bikes}
                <span className="santander-counts__sep">|</span>
                {station.nb_docks}
              </div>
              <div className={`santander-bike-badge${unavailable ? ' is-empty' : ''}`}>
                <Bike size={14} strokeWidth={2.25} aria-hidden />
              </div>
            </>
          )}
        </div>
        <div className="santander-beak" aria-hidden />
      </div>
    </div>
  );
}

function StationMarker({
  station,
  expanded,
  layout,
  confirmLabel,
  showConfirm,
  availabilityNeed,
  onExpand,
  onConfirm,
}) {
  return (
    <Marker
      longitude={station.lon}
      latitude={station.lat}
      anchor="center"
      style={{ zIndex: expanded ? 700 : 400 }}
    >
      <div className="santander-divicon">
        <StationCard
          station={station}
          expanded={expanded}
          side={layout?.side || 'bottom'}
          along={expanded
            ? BEAK_ALONG_EXPANDED
            : (layout?.along ?? BEAK_ALONG_COMPACT)}
          confirmLabel={confirmLabel}
          showConfirm={!!(showConfirm && expanded)}
          availabilityNeed={availabilityNeed}
          onExpand={onExpand}
          onConfirm={onConfirm}
        />
      </div>
    </Marker>
  );
}

function CompactBikeMarker({ station }) {
  return (
    <Marker
      longitude={station.lon}
      latitude={station.lat}
      anchor="center"
      style={{ zIndex: 350 }}
    >
      <div
        className="santander-compact"
        title={station.commonName || station.name || 'Santander'}
      >
        <Bike size={14} strokeWidth={2.4} color="#FF0061" aria-hidden />
      </div>
    </Marker>
  );
}

/**
 * Top/bottom side frozen when the station id set loads (not on zoom).
 * Pill+beak are one silhouette via drop-shadow on the unit.
 * `compact` — pink bike in white disc (post hire selection).
 */
export default function SantanderStationsLayer({
  stations,
  expandedId,
  confirmLabel,
  showConfirm = false,
  availabilityNeed = 'bikes',
  onExpand,
  onConfirm,
  compact = false,
}) {
  const maps = useMap();
  const map = maps.main || maps.current;
  const [layouts, setLayouts] = useState({});
  const list = stations || [];
  const idsKey = list.map((s) => s.id).join(',');

  useEffect(() => {
    if (compact || !list.length || !map) {
      setLayouts({});
      return;
    }
    const items = list.map((s) => {
      const p = map.project([s.lon, s.lat]);
      return { id: s.id, px: p.x, py: p.y, expanded: false };
    });
    setLayouts(computeSantanderOffsets(items));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey, map, compact]);

  if (compact) {
    return (
      <>
        {list.map((s) => (
          <CompactBikeMarker key={s.id} station={s} />
        ))}
      </>
    );
  }

  return (
    <>
      {list.map((s) => (
        <StationMarker
          key={s.id}
          station={s}
          expanded={s.id === expandedId}
          layout={layouts[s.id] || {
            side: 'bottom',
            along: s.id === expandedId ? BEAK_ALONG_EXPANDED : BEAK_ALONG_COMPACT,
          }}
          confirmLabel={confirmLabel}
          showConfirm={showConfirm}
          availabilityNeed={availabilityNeed}
          onExpand={onExpand}
          onConfirm={onConfirm}
        />
      ))}
    </>
  );
}

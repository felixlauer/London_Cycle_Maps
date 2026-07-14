import React, { useEffect, useMemo, useState } from 'react';
import { Marker, useMap } from 'react-leaflet';
import L from 'leaflet';
import bikeUrl from '../../assets/bicycle-9629.svg';
import walkUrl from '../../assets/walking-9075.svg';
import {
  computeSantanderOffsets,
  BEAK_ALONG_COMPACT,
  BEAK_ALONG_EXPANDED,
} from './labelLayout';
import './santander.css';

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function buildPinHtml(station, {
  expanded,
  side,
  along,
  confirmLabel,
  showConfirm,
}) {
  const empty = !(station.nb_bikes > 0);
  const walkMin = station.walk_duration_min ?? station.walk_estimate_min ?? 1;
  const walkLabel = station.walk_duration_min != null ? 'walk' : 'estimated walk';
  const badgeClass = empty ? 'santander-bike-badge is-empty' : 'santander-bike-badge';
  const cardClass = [
    'santander-card',
    empty ? 'is-empty' : '',
    expanded ? 'is-expanded' : '',
  ].filter(Boolean).join(' ');

  const compact = `
    <div class="santander-counts">${escapeHtml(station.nb_bikes)} | ${escapeHtml(station.nb_docks)}</div>
    <div class="${badgeClass}"><div class="santander-icon"></div></div>
  `;

  const confirmBtn = showConfirm && confirmLabel
    ? `<button type="button" class="santander-confirm-btn" data-santander-confirm="1">${escapeHtml(confirmLabel)}</button>`
    : '';

  const expandedBody = `
    <div class="santander-card-top">
      <div class="santander-breakdown">
        <div class="santander-bd-item">
          <div class="santander-bd-num">${escapeHtml(station.nb_standard)}</div>
          <div class="santander-bd-label">regular</div>
        </div>
        <div class="santander-bd-item">
          <div class="santander-bd-num is-electric">${escapeHtml(station.nb_ebikes)}</div>
          <div class="santander-bd-label is-electric">electric</div>
        </div>
        <div class="santander-bd-item">
          <div class="santander-bd-num is-empty-docks">${escapeHtml(station.nb_empty)}</div>
          <div class="santander-bd-label">empty</div>
        </div>
      </div>
      <div class="${badgeClass}"><div class="santander-icon"></div></div>
    </div>
    <div class="santander-walk-row">
      <div class="santander-walk-icon"></div>
      <div class="santander-walk-text">
        <strong>${escapeHtml(walkMin)} minutes</strong>
        <span>${escapeHtml(walkLabel)}</span>
      </div>
      ${confirmBtn}
    </div>
  `;

  const alongPx = along ?? (expanded ? BEAK_ALONG_EXPANDED : BEAK_ALONG_COMPACT);
  const unitClass = `santander-pin-unit side-${side || 'bottom'}`;

  return `
    <div class="santander-anchor" style="--santander-bike-mask:url('${bikeUrl}');--santander-walk-mask:url('${walkUrl}');--beak-along:${alongPx}px;">
      <div class="${unitClass}">
        <div class="${cardClass}">
          ${expanded ? expandedBody : compact}
        </div>
        <div class="santander-beak" aria-hidden="true"></div>
      </div>
    </div>
  `;
}

function makeIcon(station, opts) {
  return L.divIcon({
    className: 'santander-divicon',
    html: buildPinHtml(station, opts),
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  });
}

function StationMarker({
  station,
  expanded,
  layout,
  confirmLabel,
  showConfirm,
  onExpand,
  onConfirm,
}) {
  const icon = useMemo(
    () => makeIcon(station, {
      expanded,
      side: layout?.side || 'bottom',
      along: expanded
        ? BEAK_ALONG_EXPANDED
        : (layout?.along ?? BEAK_ALONG_COMPACT),
      confirmLabel,
      showConfirm: !!(showConfirm && expanded),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [station, expanded, layout?.side, layout?.along, confirmLabel, showConfirm],
  );

  return (
    <Marker
      position={[station.lat, station.lon]}
      icon={icon}
      zIndexOffset={expanded ? 700 : 400}
      eventHandlers={{
        click: (e) => {
          L.DomEvent.stopPropagation(e);
          const target = e.originalEvent?.target;
          if (target && typeof target.closest === 'function'
              && target.closest('[data-santander-confirm]')) {
            e.originalEvent?.preventDefault?.();
            onConfirm?.(station);
            return;
          }
          onExpand?.(station);
        },
      }}
    />
  );
}

/**
 * Top/bottom side frozen when the station id set loads (not on zoom).
 * Pill+beak are one silhouette via drop-shadow on the unit.
 */
export default function SantanderStationsLayer({
  stations,
  expandedId,
  confirmLabel,
  showConfirm = false,
  onExpand,
  onConfirm,
}) {
  const map = useMap();
  const [layouts, setLayouts] = useState({});
  const list = stations || [];
  const idsKey = list.map((s) => s.id).join(',');

  useEffect(() => {
    if (!list.length) {
      setLayouts({});
      return;
    }
    const items = list.map((s) => {
      const p = map.latLngToContainerPoint([s.lat, s.lon]);
      return { id: s.id, px: p.x, py: p.y, expanded: false };
    });
    setLayouts(computeSantanderOffsets(items));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey, map]);

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
          onExpand={onExpand}
          onConfirm={onConfirm}
        />
      ))}
    </>
  );
}

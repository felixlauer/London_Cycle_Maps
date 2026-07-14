/**
 * Google Maps–style route points: start / vias (max 3) / end.
 * Icons on the right; ⇅ swap (disabled when vias exist); ≡ drag to reorder.
 *
 * TODO(later): allow vias on the Santander station→station bike leg instead of
 * mutual exclusion with hire mode.
 */
import React, { useRef, useState } from 'react';
import LocationSearchInput from '../LocationSearchInput';
import addStopIcon from '../assets/add-button-12018.svg';
import './routePoints.css';

export const MAX_VIAS = 3;

/** Build ordered waypoint list from start/end/vias for drag logic. */
export function toWaypointList(start, startLabel, vias, end, endLabel) {
  const list = [
    {
      id: 'start',
      role: 'start',
      coord: start,
      label: startLabel || '',
    },
    ...vias.map((v, i) => ({
      id: v.id || `via-${i}`,
      role: 'via',
      coord: v.coord,
      label: v.label || '',
    })),
    {
      id: 'end',
      role: 'end',
      coord: end,
      label: endLabel || '',
    },
  ];
  return list;
}

export function fromWaypointList(list) {
  const startWp = list.find((w) => w.role === 'start') || list[0];
  const endWp = list.find((w) => w.role === 'end') || list[list.length - 1];
  // After drag, roles may have moved — treat first as start, last as end, middle as vias.
  const ordered = list;
  const first = ordered[0];
  const last = ordered[ordered.length - 1];
  const middle = ordered.slice(1, -1);
  return {
    start: first.coord,
    startLabel: first.label,
    end: last.coord,
    endLabel: last.label,
    vias: middle.map((w, i) => ({
      id: w.id.startsWith('via') ? w.id : `via-${i}-${Date.now()}`,
      coord: w.coord,
      label: w.label,
    })),
  };
}

function SlotIcon({ role }) {
  if (role === 'start') {
    return (
      <span className="rp-icon rp-icon--start" aria-hidden title="Start">
        <svg width="14" height="14" viewBox="0 0 14 14">
          <circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" strokeWidth="1.6" />
        </svg>
      </span>
    );
  }
  if (role === 'end') {
    return (
      <span className="rp-icon rp-icon--end" aria-hidden title="Destination">
        <svg width="14" height="18" viewBox="0 0 14 18">
          <path
            d="M7 1C4 1 1.5 3.4 1.5 6.2c0 3.4 5.5 10.3 5.5 10.3S12.5 9.6 12.5 6.2C12.5 3.4 10 1 7 1z"
            fill="currentColor"
          />
          <circle cx="7" cy="6.2" r="2" fill="#fff" />
        </svg>
      </span>
    );
  }
  return (
    <span className="rp-icon rp-icon--via" aria-hidden title="Stop">
      <svg width="12" height="12" viewBox="0 0 12 12">
        <circle cx="6" cy="6" r="3.5" fill="currentColor" />
      </svg>
    </span>
  );
}

export default function RoutePointsPanel({
  theme,
  start,
  end,
  startLabel,
  endLabel,
  vias,
  onChangeWaypoints,
  onAddVia,
  onRemoveVia,
  onSwapStartEnd,
  santanderMode,
  santanderDisabled,
  onSantanderChange,
  departMode,
}) {
  const [dragIndex, setDragIndex] = useState(null);
  const [overIndex, setOverIndex] = useState(null);
  const dragIndexRef = useRef(null);

  const list = toWaypointList(start, startLabel, vias, end, endLabel);
  const hasVias = vias.length > 0;
  const canAddVia = vias.length < MAX_VIAS;

  const applyReorder = (from, to) => {
    if (from == null || to == null || from === to) return;
    const next = [...list];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChangeWaypoints(fromWaypointList(next));
  };

  const onDragStart = (index) => (e) => {
    dragIndexRef.current = index;
    setDragIndex(index);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(index));
  };

  const onDragOver = (index) => (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setOverIndex(index);
  };

  const onDrop = (index) => (e) => {
    e.preventDefault();
    const from = dragIndexRef.current;
    applyReorder(from, index);
    dragIndexRef.current = null;
    setDragIndex(null);
    setOverIndex(null);
  };

  const onDragEnd = () => {
    dragIndexRef.current = null;
    setDragIndex(null);
    setOverIndex(null);
  };

  const updateAt = (index, { lat, lon, label }) => {
    const next = list.map((w, i) =>
      i === index
        ? { ...w, coord: [lat, lon], label: label || `${lat.toFixed(4)}, ${lon.toFixed(4)}` }
        : w
    );
    onChangeWaypoints(fromWaypointList(next));
  };

  const placeholderFor = (role, idx) => {
    if (role === 'start') return 'Search start location';
    if (role === 'end') return 'Search destination';
    return `Stop ${idx}`;
  };

  return (
    <div className="rp-panel" data-theme={theme?.mode}>
      <ul className="rp-list">
        {list.map((wp, index) => {
          const isVia = index > 0 && index < list.length - 1;
          const viaOrdinal = isVia ? index : null;
          const roleDisplay = index === 0 ? 'start' : index === list.length - 1 ? 'end' : 'via';
          return (
            <React.Fragment key={wp.id}>
              {index === 1 && !hasVias && (
                <li className="rp-swap-row">
                  <div className="rp-swap-row__spacer" aria-hidden />
                  <button
                    type="button"
                    className="rp-swap"
                    onClick={onSwapStartEnd}
                    disabled={!start || !end}
                    title="Swap start and end"
                    aria-label="Swap start and end"
                  >
                    ⇅
                  </button>
                </li>
              )}
              {index >= 1 && hasVias && index < list.length && (
                <li className="rp-gap" aria-hidden />
              )}
              <li
                className={
                  `rp-row rp-row--${roleDisplay}` +
                  (dragIndex === index ? ' is-dragging' : '') +
                  (overIndex === index && dragIndex !== index ? ' is-drop-target' : '')
                }
                draggable={list.length > 2}
                onDragStart={onDragStart(index)}
                onDragOver={onDragOver(index)}
                onDrop={onDrop(index)}
                onDragEnd={onDragEnd}
              >
                <div className="rp-row__input">
                  <LocationSearchInput
                    label=""
                    value={wp.label}
                    placeholder={placeholderFor(roleDisplay, viaOrdinal)}
                    theme={theme}
                    onSelect={({ lat, lon, label }) => updateAt(index, { lat, lon, label })}
                  />
                </div>
                <div className="rp-row__aside">
                  {isVia && (
                    <button
                      type="button"
                      className="rp-remove"
                      onClick={() => onRemoveVia(index - 1)}
                      title="Remove stop"
                      aria-label="Remove stop"
                    >
                      ✕
                    </button>
                  )}
                  {list.length > 2 && (
                    <span className="rp-grip" title="Drag to reorder" aria-hidden>
                      ☰
                    </span>
                  )}
                  <SlotIcon role={roleDisplay} />
                </div>
              </li>
            </React.Fragment>
          );
        })}
      </ul>

      <button
        type="button"
        className="rp-add"
        onClick={onAddVia}
        disabled={!canAddVia}
        title={
          vias.length >= MAX_VIAS
            ? `Maximum ${MAX_VIAS} stops`
            : santanderMode
              ? 'Add a stop (turns off Santander hire)'
              : 'Add a stop'
        }
      >
        <img src={addStopIcon} alt="" className="rp-add__icon" width={18} height={18} />
        Add stop
      </button>

      <label
        className={`santander-toggle${santanderDisabled || hasVias ? ' is-disabled' : ''}`}
        title={
          hasVias
            ? 'Clear via stops to use Santander hire (TODO: vias on hire bike leg)'
            : departMode === 'depart_at'
              ? 'Santander hire needs live dock availability — use Leave now'
              : undefined
        }
      >
        <input
          type="checkbox"
          checked={santanderMode}
          disabled={santanderDisabled || hasVias}
          onChange={(e) => onSantanderChange(e.target.checked)}
        />
        Santander Cycles
      </label>
    </div>
  );
}

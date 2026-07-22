import React, { useRef, useState } from 'react';
import { Circle, MapPin, Equal, X } from 'lucide-react';
import LocationSearchInput from '../../LocationSearchInput';

export function toWaypointList(start, startLabel, vias, end, endLabel) {
  return [
    { id: 'start', role: 'start', coord: start, label: startLabel || '' },
    ...vias.map((v, i) => ({
      id: v.id || `via-${i}`,
      role: 'via',
      coord: v.coord,
      label: v.label || '',
    })),
    { id: 'end', role: 'end', coord: end, label: endLabel || '' },
  ];
}

export function fromWaypointList(list) {
  const first = list[0];
  const last = list[list.length - 1];
  const middle = list.slice(1, -1);
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

function letterAt(index) {
  return String.fromCharCode(65 + index);
}

function SlotIcon({ role, letter }) {
  if (role === 'start') {
    return <Circle size={15} strokeWidth={2.2} className="rc-slot rc-slot--start" aria-hidden />;
  }
  if (role === 'end') {
    return <MapPin size={16} strokeWidth={2.2} className="rc-slot rc-slot--end" aria-hidden />;
  }
  return <span className="rc-letter rc-letter--via" aria-hidden>{letter}</span>;
}

/**
 * Apple Maps structure: all waypoints in one grouped card, permanent grab
 * bars on the right. Start/end use lucide icons; vias use journey letters.
 * Mobile: viasCollapsed hides middle stops behind an Excel-style expand row.
 */
export default function WaypointFields({
  theme,
  start,
  end,
  startLabel,
  endLabel,
  vias,
  onChangeWaypoints,
  onRemoveVia,
  onFlyTo,
  startPlaceholder,
  viasCollapsed = false,
  onExpandVias,
}) {
  const [dragIndex, setDragIndex] = useState(null);
  const [overIndex, setOverIndex] = useState(null);
  const dragIndexRef = useRef(null);

  const list = toWaypointList(start, startLabel, vias, end, endLabel);
  const viaCount = (vias || []).length;
  const hideVias = viasCollapsed && viaCount > 0;

  const applyReorder = (from, to) => {
    if (from == null || to == null || from === to) return;
    const next = [...list];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChangeWaypoints(fromWaypointList(next));
  };

  const updateAt = (index, { lat, lon, label }) => {
    const next = list.map((w, i) =>
      i === index
        ? { ...w, coord: [lat, lon], label: label || `${lat.toFixed(4)}, ${lon.toFixed(4)}` }
        : w,
    );
    onChangeWaypoints(fromWaypointList(next));
    onFlyTo?.([lat, lon]);
  };

  const renderRow = (wp, index) => {
    const isVia = index > 0 && index < list.length - 1;
    const roleDisplay = index === 0 ? 'start' : index === list.length - 1 ? 'end' : 'via';
    const letter = letterAt(index);
    return (
      <React.Fragment key={wp.id}>
        {index > 0 && <div className="rc-wpcard__divider" aria-hidden />}
        <div
          className={
            `rc-wp-row` +
            (dragIndex === index ? ' is-dragging' : '') +
            (overIndex === index && dragIndex !== index ? ' is-drop-target' : '')
          }
          onDragOver={(e) => {
            e.preventDefault();
            setOverIndex(index);
          }}
          onDrop={(e) => {
            e.preventDefault();
            applyReorder(dragIndexRef.current, index);
            dragIndexRef.current = null;
            setDragIndex(null);
            setOverIndex(null);
          }}
        >
          <SlotIcon role={roleDisplay} letter={letter} />
          <div className="rc-wp-input">
            <LocationSearchInput
              label=""
              value={wp.label}
              placeholder={
                roleDisplay === 'start'
                  ? (startPlaceholder || 'Search start')
                  : roleDisplay === 'end'
                    ? 'Search destination'
                    : `Stop ${letter}`
              }
              theme={theme}
              onSelect={({ lat, lon, label }) => updateAt(index, { lat, lon, label })}
            />
          </div>
          {isVia && (
            <button
              type="button"
              className="rc-wp-remove"
              aria-label="Remove stop"
              onClick={() => onRemoveVia(index - 1)}
            >
              <X size={14} strokeWidth={2.2} />
            </button>
          )}
          <span
            className="rc-wp-grip"
            aria-hidden
            draggable
            onDragStart={(e) => {
              dragIndexRef.current = index;
              setDragIndex(index);
              e.dataTransfer.effectAllowed = 'move';
              e.dataTransfer.setData('text/plain', String(index));
            }}
            onDragEnd={() => {
              dragIndexRef.current = null;
              setDragIndex(null);
              setOverIndex(null);
            }}
          >
            <Equal size={16} strokeWidth={2} />
          </span>
        </div>
      </React.Fragment>
    );
  };

  const startWp = list[0];
  const endWp = list[list.length - 1];

  return (
    <div className="rc-waypoints">
      {hideVias ? (
        <div className="rc-wpcard rc-wpcard--vias-hidden">
          {renderRow(startWp, 0)}
          {renderRow(endWp, list.length - 1)}
          <button
            type="button"
            className="rc-wp-hidden-pill"
            aria-label={`Show ${viaCount} hidden stop${viaCount === 1 ? '' : 's'}`}
            onClick={() => onExpandVias?.()}
          >
            {viaCount} stop{viaCount === 1 ? '' : 's'} hidden
          </button>
        </div>
      ) : (
        <div className="rc-wpcard">
          {list.map((wp, index) => renderRow(wp, index))}
        </div>
      )}
    </div>
  );
}

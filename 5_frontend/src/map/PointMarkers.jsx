import React from 'react';
import { Marker } from 'react-map-gl/mapbox';

/** Greyscale pin — letter is journey order (A→B→C→D). */
function Pin({ label }) {
  return (
    <div
      style={{
        width: 24,
        height: 24,
        borderRadius: '50% 50% 50% 0',
        background: '#3f3f46',
        transform: 'rotate(-45deg)',
        border: '2px solid #fff',
        boxShadow: '0 2px 6px rgba(0,0,0,0.32)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      title={label}
    >
      <span
        style={{
          transform: 'rotate(45deg)',
          color: '#fff',
          fontSize: 11,
          fontWeight: 700,
          lineHeight: 1,
        }}
      >
        {label}
      </span>
    </div>
  );
}

function letterAt(index) {
  return String.fromCharCode(65 + index);
}

/**
 * Start / vias / end markers in journey order: A → B → C → D …
 * Positions are app [lat, lon].
 */
export default function PointMarkers({ start, end, vias }) {
  const points = [];
  if (start) points.push({ key: 'start', coord: start });
  (vias || []).forEach((v) => {
    if (v?.coord) points.push({ key: v.id || `via-${points.length}`, coord: v.coord });
  });
  if (end) points.push({ key: 'end', coord: end });

  return (
    <>
      {points.map((p, i) => (
        <Marker
          key={p.key}
          longitude={p.coord[1]}
          latitude={p.coord[0]}
          anchor="bottom"
        >
          <Pin label={letterAt(i)} />
        </Marker>
      ))}
    </>
  );
}

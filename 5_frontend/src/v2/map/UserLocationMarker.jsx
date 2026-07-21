import React from 'react';
import { Marker } from 'react-map-gl/mapbox';

const ACCENT = '#4D9DE0'; // Blue Bell — secondary / location

/**
 * User location — filled secondary disc with white halo (route-line language).
 */
export default function UserLocationMarker({ location }) {
  if (!location?.lat || !location?.lon) return null;
  return (
    <Marker
      longitude={location.lon}
      latitude={location.lat}
      anchor="center"
      style={{ zIndex: 500 }}
    >
      <div
        className="user-loc-marker"
        style={{
          width: 18,
          height: 18,
          borderRadius: '50%',
          background: ACCENT,
          border: '3px solid #fff',
          boxShadow: '0 1px 6px rgba(16, 24, 40, 0.28)',
          boxSizing: 'border-box',
        }}
        title="Your location"
      />
    </Marker>
  );
}

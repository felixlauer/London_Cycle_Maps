import { useEffect } from 'react';
import { useMap } from 'react-leaflet';

/**
 * Fly map viewport to target when it changes (search selection).
 * Render inside MapContainer.
 */
export default function MapFlyTo({ target, zoom = 15 }) {
  const map = useMap();
  useEffect(() => {
    if (target && target.length === 2) {
      map.flyTo(target, zoom, { duration: 0.8 });
    }
  }, [target, zoom, map]);
  return null;
}

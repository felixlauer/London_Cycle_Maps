import { useEffect } from 'react';
import { useMap } from 'react-leaflet';

/**
 * Fly map viewport to target when it changes (search selection / hire steps).
 * Render inside MapContainer.
 * target may be [lat, lon] or { center: [lat, lon], zoom?, duration? }.
 */
export default function MapFlyTo({ target, zoom = 15, duration = 0.8 }) {
  const map = useMap();
  useEffect(() => {
    if (!target) return;
    const center = Array.isArray(target) ? target : target.center;
    if (!center || center.length !== 2) return;
    const z = Array.isArray(target) ? zoom : (target.zoom ?? zoom);
    const d = Array.isArray(target) ? duration : (target.duration ?? duration);
    map.flyTo(center, z, { duration: d });
  }, [target, zoom, duration, map]);
  return null;
}

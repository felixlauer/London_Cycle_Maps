import { useEffect } from 'react';
import { useMap } from 'react-map-gl/mapbox';
import { latLonToLngLat } from './coords';

/**
 * Fly map viewport when target changes (search selection / hire steps).
 * target may be [lat, lon] or { center: [lat, lon], zoom?, duration? }.
 * duration is in seconds (same as legacy MapFlyTo).
 */
export default function MapFlyTo({ target, zoom = 15, duration = 0.8 }) {
  const maps = useMap();
  const map = maps.main || maps.current;

  useEffect(() => {
    if (!target || !map) return;
    const center = Array.isArray(target) ? target : target.center;
    const lngLat = latLonToLngLat(center);
    if (!lngLat) return;
    const z = Array.isArray(target) ? zoom : (target.zoom ?? zoom);
    const dSec = Array.isArray(target) ? duration : (target.duration ?? duration);
    map.flyTo({
      center: lngLat,
      zoom: z,
      duration: Math.max(0, dSec) * 1000,
    });
  }, [target, zoom, duration, map]);

  return null;
}

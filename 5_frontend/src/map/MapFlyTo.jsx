import { useEffect } from 'react';
import { useMap } from 'react-map-gl/mapbox';
import { latLonToLngLat } from './coords';

/**
 * Fly / fit map viewport when target changes (search / hire steps).
 * target may be:
 *   - [lat, lon]
 *   - { center: [lat, lon], zoom?, duration? }
 *   - { bounds: [[west,south],[east,north]] | LngLatBoundsLike, padding?, maxZoom?, duration? }
 * duration is in seconds.
 */
export default function MapFlyTo({ target, zoom = 15, duration = 0.8 }) {
  const maps = useMap();
  const map = maps.main || maps.current;

  useEffect(() => {
    if (!target || !map) return;

    const dSec = Array.isArray(target) ? duration : (target.duration ?? duration);
    const ms = Math.max(0, dSec) * 1000;

    if (!Array.isArray(target) && target.bounds) {
      const pad = target.padding ?? 72;
      map.fitBounds(target.bounds, {
        padding: pad,
        duration: ms,
        maxZoom: target.maxZoom ?? 15.5,
        essential: true,
      });
      return;
    }

    const center = Array.isArray(target) ? target : target.center;
    const lngLat = latLonToLngLat(center);
    if (!lngLat) return;
    const z = Array.isArray(target) ? zoom : (target.zoom ?? zoom);
    map.flyTo({
      center: lngLat,
      zoom: z,
      duration: ms,
    });
  }, [target, zoom, duration, map]);

  return null;
}

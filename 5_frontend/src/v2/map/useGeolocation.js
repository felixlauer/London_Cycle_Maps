import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Greater London planning bbox (S, W, N, E) — same envelope as OSM park fetch.
 * @see 3_pipeline/fetch_osm_park_polygons.py LONDON_BBOX
 */
export const GREATER_LONDON_BBOX = {
  south: 51.2868,
  west: -0.5104,
  north: 51.6918,
  east: 0.3340,
};

export function isInGreaterLondon(lat, lon) {
  return (
    lat >= GREATER_LONDON_BBOX.south
    && lat <= GREATER_LONDON_BBOX.north
    && lon >= GREATER_LONDON_BBOX.west
    && lon <= GREATER_LONDON_BBOX.east
  );
}

/**
 * Browser geolocation for the locate control.
 * Does not write to the server — coords stay in the client until used as a route start.
 * Outside Greater London → error callback + return to inactive.
 */
export function useGeolocation({ onError } = {}) {
  const [active, setActive] = useState(false);
  const [pending, setPending] = useState(false);
  const [location, setLocation] = useState(null);
  const watchIdRef = useRef(null);
  const onErrorRef = useRef(onError);
  useEffect(() => { onErrorRef.current = onError; }, [onError]);

  const clearWatch = useCallback(() => {
    if (watchIdRef.current != null && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchIdRef.current);
      watchIdRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    clearWatch();
    setActive(false);
    setPending(false);
    setLocation(null);
  }, [clearWatch]);

  const rejectOutsideLondon = useCallback(() => {
    clearWatch();
    setPending(false);
    setActive(false);
    setLocation(null);
    onErrorRef.current?.(
      'Location is outside Greater London — routing here is not supported yet',
    );
  }, [clearWatch]);

  const applyPosition = useCallback((pos) => {
    const { latitude: lat, longitude: lon, accuracy } = pos.coords;
    if (!isInGreaterLondon(lat, lon)) {
      rejectOutsideLondon();
      return false;
    }
    setLocation({
      lat,
      lon,
      accuracy,
      label: 'Current location',
      updatedAt: Date.now(),
    });
    setPending(false);
    setActive(true);
    return true;
  }, [rejectOutsideLondon]);

  const fail = useCallback((err) => {
    setPending(false);
    clearWatch();
    setActive(false);
    setLocation(null);
    let message = 'Could not get your location';
    if (err?.code === 1) message = 'Location permission denied';
    else if (err?.code === 2) message = 'Location unavailable';
    else if (err?.code === 3) message = 'Location request timed out';
    else if (typeof window !== 'undefined' && !window.isSecureContext) {
      message = 'Location needs HTTPS (or localhost)';
    }
    onErrorRef.current?.(message);
  }, [clearWatch]);

  const start = useCallback(() => {
    if (!navigator.geolocation) {
      onErrorRef.current?.('Geolocation is not supported in this browser');
      return;
    }
    if (typeof window !== 'undefined' && !window.isSecureContext) {
      onErrorRef.current?.('Location needs HTTPS (or localhost)');
      return;
    }
    setPending(true);
    const opts = { enableHighAccuracy: true, timeout: 12000, maximumAge: 15000 };
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const ok = applyPosition(pos);
        if (!ok) return;
        clearWatch();
        watchIdRef.current = navigator.geolocation.watchPosition(
          (next) => { applyPosition(next); },
          () => { /* keep last good fix; ignore soft watch errors */ },
          opts,
        );
      },
      fail,
      opts,
    );
  }, [applyPosition, clearWatch, fail]);

  const toggle = useCallback(() => {
    if (active || pending) stop();
    else start();
  }, [active, pending, start, stop]);

  useEffect(() => () => clearWatch(), [clearWatch]);

  return { active, pending, location, toggle, stop };
}

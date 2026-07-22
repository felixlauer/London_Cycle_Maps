import { useEffect, useRef } from 'react';
import { useMap } from 'react-map-gl/mapbox';

const VIEW_EASE_MS = 280;
const NORTH_UP_BEARING_EPS = 0.5;
const NORTH_UP_PITCH_EPS = 0.5;

function viewNeedsNorthReset(map) {
  if (!map) return false;
  const bearing = map.getBearing?.() ?? 0;
  const pitch = map.getPitch?.() ?? 0;
  return Math.abs(bearing) > NORTH_UP_BEARING_EPS || Math.abs(pitch) > NORTH_UP_PITCH_EPS;
}

/**
 * Registers zoomIn / zoomOut / resize / resetNorth on a shared api ref (chrome sits outside Map).
 * Also fires onMapReady once when the Mapbox map instance is available.
 */
export default function MapApiBridge({ apiRef, onNorthUpChange, onMapReady }) {
  const maps = useMap();
  const map = maps.main || maps.current;
  const readyFired = useRef(false);

  useEffect(() => {
    if (!map || !onMapReady || readyFired.current) return undefined;
    const m = map.getMap?.() || map;
    const fire = () => {
      if (readyFired.current) return;
      readyFired.current = true;
      onMapReady();
    };
    if (m?.loaded?.()) {
      fire();
      return undefined;
    }
    m?.once?.('load', fire);
    // Fallback if style already loaded
    const t = window.setTimeout(fire, 800);
    return () => {
      m?.off?.('load', fire);
      window.clearTimeout(t);
    };
  }, [map, onMapReady]);

  useEffect(() => {
    if (!apiRef) return undefined;
    apiRef.current = {
      zoomIn: () => {
        map?.zoomIn({ duration: VIEW_EASE_MS });
      },
      zoomOut: () => {
        map?.zoomOut({ duration: VIEW_EASE_MS });
      },
      resize: () => {
        const m = map?.getMap?.() || map;
        m?.resize?.();
      },
      resetNorth: () => {
        if (!map || !viewNeedsNorthReset(map)) return;
        map.easeTo?.({
          bearing: 0,
          pitch: 0,
          duration: VIEW_EASE_MS,
        });
      },
      /** Project [lng, lat] → CSS pixels relative to the map canvas. */
      project: (lngLat) => {
        const m = map?.getMap?.() || map;
        if (!m?.project || !lngLat) return null;
        try {
          return m.project(lngLat);
        } catch {
          return null;
        }
      },
      getContainer: () => {
        const m = map?.getMap?.() || map;
        return m?.getContainer?.() || null;
      },
      getMap: () => map?.getMap?.() || map || null,
      isMoving: () => {
        const m = map?.getMap?.() || map;
        return Boolean(m?.isMoving?.() || m?.isZooming?.() || m?.isEasing?.());
      },
      /** Resolve once the camera is idle (or after timeoutMs). */
      onceIdle: (cb, timeoutMs = 2000) => {
        const m = map?.getMap?.() || map;
        if (!m) {
          const t = window.setTimeout(cb, 0);
          return () => window.clearTimeout(t);
        }
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          cb();
        };
        m.once?.('idle', finish);
        const t = window.setTimeout(finish, timeoutMs);
        return () => {
          settled = true;
          m.off?.('idle', finish);
          window.clearTimeout(t);
        };
      },
    };
    return () => {
      if (apiRef.current) {
        apiRef.current.zoomIn = undefined;
        apiRef.current.zoomOut = undefined;
        apiRef.current.resize = undefined;
        apiRef.current.resetNorth = undefined;
        apiRef.current.project = undefined;
        apiRef.current.getContainer = undefined;
        apiRef.current.getMap = undefined;
        apiRef.current.isMoving = undefined;
        apiRef.current.onceIdle = undefined;
      }
    };
  }, [apiRef, map]);

  useEffect(() => {
    if (!map || !onNorthUpChange) return undefined;

    const report = () => {
      onNorthUpChange(viewNeedsNorthReset(map));
    };

    report();
    map.on('rotate', report);
    map.on('pitch', report);
    map.on('rotateend', report);
    map.on('pitchend', report);

    return () => {
      map.off('rotate', report);
      map.off('pitch', report);
      map.off('rotateend', report);
      map.off('pitchend', report);
    };
  }, [map, onNorthUpChange]);

  return null;
}

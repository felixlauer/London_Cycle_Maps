import React, { useEffect } from 'react';
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
 */
export default function MapApiBridge({ apiRef, onNorthUpChange }) {
  const maps = useMap();
  const map = maps.main || maps.current;

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
    };
    return () => {
      if (apiRef.current) {
        apiRef.current.zoomIn = undefined;
        apiRef.current.zoomOut = undefined;
        apiRef.current.resize = undefined;
        apiRef.current.resetNorth = undefined;
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

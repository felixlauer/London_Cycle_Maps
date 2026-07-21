import { useEffect } from 'react';
import { useMap } from 'react-map-gl/mapbox';
import { lightPresetForTheme } from './styles';

/**
 * Keeps Mapbox Standard lightPreset in sync with shell themeMode.
 * Style URL stays fixed — only the basemap config changes (no dark-v11 swap).
 */
export default function MapLightPreset({ themeMode = 'light' }) {
  const maps = useMap();
  const mapRef = maps.main || maps.current;

  useEffect(() => {
    if (!mapRef) return undefined;
    const map = typeof mapRef.getMap === 'function' ? mapRef.getMap() : mapRef;
    if (!map?.setConfigProperty) return undefined;

    const preset = lightPresetForTheme(themeMode);
    const apply = () => {
      try {
        map.setConfigProperty('basemap', 'lightPreset', preset);
      } catch {
        /* Style import not ready yet */
      }
    };

    apply();
    map.on('style.load', apply);
    return () => {
      map.off('style.load', apply);
    };
  }, [mapRef, themeMode]);

  return null;
}

/** Mapbox Standard style — day/night via lightPreset (not classic dark-v11). */

export const MAP_STYLE = 'mapbox://styles/mapbox/standard';

/** @deprecated Use MAP_STYLE — Standard covers both day and night. */
export const MAP_STYLE_DAY = MAP_STYLE;
/** @deprecated Use MAP_STYLE + lightPresetForTheme('dark'). */
export const MAP_STYLE_NIGHT = MAP_STYLE;

export function lightPresetForTheme(themeMode) {
  return themeMode === 'dark' ? 'night' : 'day';
}

/** Always Standard; appearance is controlled by lightPreset. */
export function mapStyleForTheme(_themeMode) {
  return MAP_STYLE;
}

export function basemapConfigForTheme(themeMode) {
  return {
    basemap: {
      lightPreset: lightPresetForTheme(themeMode),
    },
  };
}

export const MAPBOX_TOKEN = process.env.REACT_APP_MAPBOX_TOKEN || '';

export const DEFAULT_VIEW = {
  longitude: -0.09,
  latitude: 51.505,
  zoom: 13,
};

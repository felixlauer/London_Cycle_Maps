/** Mapbox Standard — day/night via lightPreset (not classic dark-v10). */

export const MAP_STYLE = 'mapbox://styles/mapbox/standard';

export function lightPresetForTheme(themeMode: 'light' | 'dark'): 'day' | 'night' {
  return themeMode === 'dark' ? 'night' : 'day';
}

/** Keep custom lines vivid under Mapbox Standard night lighting (web RouteLayers). */
export const LINE_EMISSIVE = { lineEmissiveStrength: 1 } as const;

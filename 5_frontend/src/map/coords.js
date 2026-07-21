/** App state uses [lat, lon]; Mapbox GeoJSON / center uses [lng, lat]. */

export function latLonToLngLat(latLon) {
  if (!latLon || latLon.length < 2) return null;
  const [lat, lon] = latLon;
  if (lat == null || lon == null) return null;
  return [lon, lat];
}

export function lngLatToLatLon(lngLat) {
  if (!lngLat || lngLat.length < 2) return null;
  const [lng, lat] = lngLat;
  return [lat, lng];
}

/** Leaflet-style path [[lat,lon], ...] → GeoJSON LineString coordinates [[lng,lat], ...] */
export function pathToLineCoords(path) {
  if (!path || path.length < 2) return null;
  const coords = [];
  for (const p of path) {
    const ll = latLonToLngLat(p);
    if (ll) coords.push(ll);
  }
  return coords.length >= 2 ? coords : null;
}

export function pathsToMultiLineGeoJSON(paths) {
  const features = [];
  (paths || []).forEach((path, i) => {
    const coords = pathToLineCoords(path);
    if (coords) {
      features.push({
        type: 'Feature',
        properties: { i },
        geometry: { type: 'LineString', coordinates: coords },
      });
    }
  });
  return { type: 'FeatureCollection', features };
}

/**
 * Typed overlay chunks: { path, kind, length_m, ... } → FeatureCollection.
 * Also accepts legacy bare polylines (arrays).
 */
export function typedChunksToGeoJSON(chunks) {
  const features = [];
  (chunks || []).forEach((chunk, i) => {
    const isTyped = chunk && !Array.isArray(chunk) && Array.isArray(chunk.path);
    const path = isTyped ? chunk.path : chunk;
    const coords = pathToLineCoords(path);
    if (!coords) return;
    const props = isTyped
      ? {
        i,
        kind: chunk.kind || '',
        length_m: Number(chunk.length_m) || 0,
        elev_gain_m: Number(chunk.elev_gain_m) || 0,
        run_id: chunk.run_id || `r-${i}`,
        label: chunk.label || chunk.name || '',
        name: chunk.name || '',
        surface: chunk.surface || '',
        category: chunk.category || '',
        description: chunk.description || '',
        source: chunk.source || '',
      }
      : { i };
    features.push({
      type: 'Feature',
      properties: props,
      geometry: { type: 'LineString', coordinates: coords },
    });
  });
  return { type: 'FeatureCollection', features };
}

/** Midpoint [lng, lat] of a lat/lon path for jam markers. */
export function pathMidLngLat(path) {
  const coords = pathToLineCoords(path);
  if (!coords || !coords.length) return null;
  return coords[Math.floor(coords.length / 2)] || null;
}

export function pathToLineGeoJSON(path, properties = {}) {
  const coords = pathToLineCoords(path);
  if (!coords) return { type: 'FeatureCollection', features: [] };
  return {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      properties,
      geometry: { type: 'LineString', coordinates: coords },
    }],
  };
}

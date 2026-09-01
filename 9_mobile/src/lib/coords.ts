/** App state uses [lat, lon]; Mapbox GeoJSON / center uses [lng, lat]. */

export type LatLon = [number, number];
export type LngLat = [number, number];

export function latLonToLngLat(latLon: LatLon | number[] | null | undefined): LngLat | null {
  if (!latLon || latLon.length < 2) return null;
  const [lat, lon] = latLon;
  if (lat == null || lon == null) return null;
  return [lon, lat];
}

export function lngLatToLatLon(lngLat: LngLat | number[] | null | undefined): LatLon | null {
  if (!lngLat || lngLat.length < 2) return null;
  const [lng, lat] = lngLat;
  return [lat, lng];
}

export function pathToLineCoords(path: number[][] | null | undefined): LngLat[] | null {
  if (!path || path.length < 2) return null;
  const coords: LngLat[] = [];
  for (const p of path) {
    const ll = latLonToLngLat(p);
    if (ll) coords.push(ll);
  }
  return coords.length >= 2 ? coords : null;
}

export function pathToLineGeoJSON(
  path: number[][] | null | undefined,
  properties: Record<string, unknown> = {},
) {
  const coords = pathToLineCoords(path);
  if (!coords) return { type: 'FeatureCollection' as const, features: [] };
  return {
    type: 'FeatureCollection' as const,
    features: [
      {
        type: 'Feature' as const,
        properties,
        geometry: { type: 'LineString' as const, coordinates: coords },
      },
    ],
  };
}

export function pointFeature(latLon: LatLon | null, properties: Record<string, unknown> = {}) {
  const ll = latLonToLngLat(latLon);
  if (!ll) return { type: 'FeatureCollection' as const, features: [] };
  return {
    type: 'FeatureCollection' as const,
    features: [
      {
        type: 'Feature' as const,
        properties,
        geometry: { type: 'Point' as const, coordinates: ll },
      },
    ],
  };
}

/** Rough bounds [[minLng, minLat], [maxLng, maxLat]] from lat/lon paths. */
export function boundsFromPaths(paths: (number[][] | null | undefined)[]) {
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;
  let any = false;
  for (const path of paths) {
    const coords = pathToLineCoords(path);
    if (!coords) continue;
    for (const [lng, lat] of coords) {
      any = true;
      if (lng < minLng) minLng = lng;
      if (lat < minLat) minLat = lat;
      if (lng > maxLng) maxLng = lng;
      if (lat > maxLat) maxLat = lat;
    }
  }
  if (!any) return null;
  return {
    ne: [maxLng, maxLat] as LngLat,
    sw: [minLng, minLat] as LngLat,
  };
}

/** Bounds from lat/lon station points (hire candidates). */
export function boundsFromLatLonPoints(
  points: { lat: number; lon: number }[],
) {
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;
  let any = false;
  for (const p of points) {
    const lat = Number(p.lat);
    const lon = Number(p.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    any = true;
    if (lon < minLng) minLng = lon;
    if (lat < minLat) minLat = lat;
    if (lon > maxLng) maxLng = lon;
    if (lat > maxLat) maxLat = lat;
  }
  if (!any) return null;
  return {
    ne: [maxLng, maxLat] as LngLat,
    sw: [minLng, minLat] as LngLat,
  };
}

export const LONDON_CENTER: LngLat = [-0.1276, 51.5074];

/**
 * Greater London planning bbox (S, W, N, E) — same envelope as OSM park fetch /
 * web `useGeolocation` GREATER_LONDON_BBOX.
 */
export const GREATER_LONDON_BBOX = {
  south: 51.2868,
  west: -0.5104,
  north: 51.6918,
  east: 0.3340,
} as const;

export function isInGreaterLondon(lat: number, lon: number) {
  return (
    lat >= GREATER_LONDON_BBOX.south
    && lat <= GREATER_LONDON_BBOX.north
    && lon >= GREATER_LONDON_BBOX.west
    && lon <= GREATER_LONDON_BBOX.east
  );
}

/**
 * Map chrome pads — right is wider so fitBounds centres in the clear map
 * (overlay + locate/north sit on the right).
 * Order for Camera.fitBounds: [top, right, bottom, left].
 */
export const MAP_FIT_PAD = {
  left: 28,
  right: 78,
} as const;

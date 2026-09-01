/**
 * Shared map↔island hover bus — mirrors web App.jsx routeHover.
 * point is [lng, lat] for Mapbox.
 */
export type RouteHover = {
  source: 'map' | 'island';
  modeId?: string;
  kind?: string;
  runId?: string | null;
  runIds?: (string | null | undefined)[] | null;
  point?: [number, number] | null;
};

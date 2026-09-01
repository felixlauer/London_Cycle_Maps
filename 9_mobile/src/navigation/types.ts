/**
 * OSRM-/MapLibre-shaped navigation payload from Flask `/route?navigate=1`.
 * Exact Tuned geometry — not Map Matching / Directions.
 */
export type NavManeuver = {
  type?: string;
  modifier?: string | null;
  instruction?: string;
  location?: [number, number] | null;
  bearing_before?: number | null;
  bearing_after?: number | null;
};

export type NavStep = {
  distance?: number;
  duration?: number;
  name?: string;
  mode?: string;
  maneuver?: NavManeuver;
  geometry_latlon?: number[][];
  geometry?: { type?: string; coordinates?: number[][] };
  voiceInstructions?: unknown[];
  bannerInstructions?: unknown[];
  tuned?: { gate?: string; kind?: string };
};

export type NavigationPayload = {
  distance?: number;
  duration?: number;
  geometry_latlon?: number[][];
  legs?: { distance?: number; duration?: number; steps?: NavStep[] }[];
  meta?: Record<string, unknown>;
  error?: string;
  debug?: Record<string, unknown>;
};

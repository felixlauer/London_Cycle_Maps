import type { StyleProp, ViewStyle } from 'react-native';

/** Live progress from the MapLibre navigation engine (~1 Hz + on every step change). */
export type RouteProgressEvent = {
  /** Leg / step being ridden. Its maneuver is the one already passed. */
  legIndex: number;
  stepIndex: number;
  /** Leg / step whose maneuver is coming up — what the banner and voice announce. */
  upcomingLegIndex: number;
  upcomingStepIndex: number;
  /** Metres left on the whole route. */
  distanceRemaining: number;
  /** Seconds left on the whole route. */
  durationRemaining: number;
  /** Metres to the upcoming maneuver. */
  stepDistanceRemaining: number;
  fractionTraveled: number;
  latitude: number;
  longitude: number;
  speed: number;
  /** Direction actually ridden, degrees clockwise from north. */
  bearing: number;
  /** Perpendicular metres from the drawn line. */
  distanceFromRoute: number;
  /** Compass usable — puck is the chevron and the map turns with the rider. */
  hasHeading: boolean;

  // Fix quality. Present only when the platform reports it, so a ride report
  // logged on a poor fix can be discounted later. Never assume these exist.
  /** Metres, WGS84. Phone altitude is coarse (±5–20 m) but sanity-checks LIDAR. */
  altitude?: number | null;
  hAccuracyM?: number | null;
  /** API 26+ only. */
  vAccuracyM?: number | null;
  speedAccuracyMps?: number | null;
  bearingAccuracyDeg?: number | null;
  /** Time of the fix itself, not when it was handled. */
  gpsEpochMs?: number | null;
  mocked?: boolean | null;
  /** Magnetometer heading, reported alongside the GPS course rather than instead. */
  compassHeadingDeg?: number | null;
  /** Which sensor owns the bearing: 'gps' | 'compass' | 'replay'. */
  puckSource?: string | null;
};

export type OffRouteEvent = {
  latitude: number;
  longitude: number;
  distanceFromRoute: number;
};

export type TrackingChangedEvent = {
  /** False once the rider pans the map away from the puck. */
  tracking: boolean;
};

export type NavErrorEvent = {
  message: string;
};

export type NavCameraMode = 'follow' | 'overview';

export type TunedMaplibreNavViewProps = {
  /** MapLibre DirectionsResponse JSON. Changing it reroutes in place. */
  directionsJson: string;
  /** Tuned route line as a GeoJSON FeatureCollection string. */
  routeGeoJson?: string;
  /** Traffic segments, each feature carrying a `color` property. */
  trafficGeoJson?: string;
  /** Cycleway segments, each feature carrying a `color` property. */
  cyclewayGeoJson?: string;
  themeMode?: 'light' | 'dark';
  /** Replay GPS along the route (desk testing). */
  simulate?: boolean;
  muted?: boolean;
  /** Greys the line, silences maneuver cues and says "Rerouting" while Flask replans. */
  rerouting?: boolean;
  cyclewaysVisible?: boolean;
  cameraMode?: NavCameraMode;
  /** Bump to re-apply `cameraMode` (recenter while already following). */
  cameraNonce?: number;
  initialLatitude?: number | null;
  initialLongitude?: number | null;
  initialBearing?: number;
  onNavReady?: (event: { nativeEvent: { ready: boolean } }) => void;
  onRouteProgress?: (event: { nativeEvent: RouteProgressEvent }) => void;
  onOffRoute?: (event: { nativeEvent: OffRouteEvent }) => void;
  /** Rider came back to the line — a replan in flight can be abandoned. */
  onRouteRejoined?: (event: { nativeEvent: OffRouteEvent }) => void;
  onArrival?: (event: { nativeEvent: { arrived: boolean } }) => void;
  onTrackingChanged?: (event: { nativeEvent: TrackingChangedEvent }) => void;
  onNavError?: (event: { nativeEvent: NavErrorEvent }) => void;
  style?: StyleProp<ViewStyle>;
};

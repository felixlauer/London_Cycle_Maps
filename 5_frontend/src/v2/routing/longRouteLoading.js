/**
 * Long-route commit feedback — same 10 km straight-line threshold as v1
 * (RouteLoadingBike), shortened for the Get Route button.
 */
import {
  straightLineKm,
  ROUTE_LOADING_MIN_KM,
} from '../../components/RouteLoadingBike';

export { straightLineKm, ROUTE_LOADING_MIN_KM };

/** Short verb labels that fit the routing button (v1 copy, condensed). */
export const LONG_ROUTE_BUTTON_MESSAGES = [
  'Mapping best path',
  'Analyzing lanes',
  'Fine-tuning route',
  'Almost ready',
];

/** Screen-reader-friendly full sentences (v1 originals, trimmed). */
export const LONG_ROUTE_ARIA_MESSAGES = [
  'Long ride — mapping the best path',
  'Analyzing cycle lanes and junctions',
  'Fine-tuning for a smoother journey',
  'Almost ready — adjusting final details',
];

/** When each button message becomes active (ms from calc start). */
export const LONG_ROUTE_MESSAGE_AT_MS = [0, 3000, 6000, 9000];

export const LONG_ROUTE_MESSAGE_FADE_MS = 180;

export function isLongRoute(start, end) {
  return straightLineKm(start, end) > ROUTE_LOADING_MIN_KM;
}

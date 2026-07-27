/**
 * Use Mapbox's CSP UMD build + static worker.
 *
 * CRA webpack exposes the default ESM entry as a Module with read-only
 * workerUrl/workerClass bindings, so react-map-gl's setGlobals crashes when
 * assigning them. The CSP UMD object is mutable and pairs with the static
 * worker we copy into public/ (avoids double-minified blob workers that break
 * Mapbox Standard HD tiles in production).
 */
import mapboxgl from 'mapbox-gl/dist/mapbox-gl-csp.js';
import { mapboxWorkerUrl } from './styles';

const lib = mapboxgl?.default ?? mapboxgl;
lib.workerUrl = mapboxWorkerUrl();

export default lib;

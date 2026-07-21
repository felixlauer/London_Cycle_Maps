import React, { useEffect, useRef, useState } from 'react';
import Map, { NavigationControl, MapProvider } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import { API_BASE } from '../api/flaskClient';
import {
  MAPBOX_TOKEN,
  MAP_STYLE,
  basemapConfigForTheme,
  DEFAULT_VIEW,
} from './styles';
import MapFlyTo from './MapFlyTo';
import MapLightPreset from './MapLightPreset';
import PointMarkers from './PointMarkers';
import {
  MultiLegRouteLayers,
  SingleRouteLayers,
  WalkAndInspectLayers,
} from './RouteLayers';
import './cycleMap.css';

/** Dedup React StrictMode double-mount within one page load. */
let inflightReserve = null;

async function reserveMapLoadOnce() {
  if (!inflightReserve) {
    inflightReserve = (async () => {
      const res = await fetch(`${API_BASE}/mapbox/map_load`, { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const err = new Error(data.error || `Map load quota (${res.status})`);
        err.status = res.status;
        err.data = data;
        throw err;
      }
      return data;
    })().finally(() => { inflightReserve = null; });
  }
  return inflightReserve;
}

/**
 * Full planning map (Mapbox GL). Children (e.g. SantanderStationsLayer) render inside Map.
 * Reserves a monthly map-load via Flask before initializing Map (hard cut with buffer).
 */
export default function CycleMap({
  theme,
  flyTarget,
  start,
  end,
  vias,
  onClick,
  onContextMenu,
  routeRevealed,
  routeLegs,
  activeLegIndex,
  overlayVisibility,
  lightingActive,
  fastestPath,
  safestPath,
  litSegments,
  steepSegments,
  tflCyclewayChunks,
  greenChunks,
  vehicularFreeChunks,
  disruptionChunks,
  nodeHighlights,
  walkStartPath,
  walkEndPath,
  inspectorGeo,
  showNavigationControl = true,
  children,
}) {
  const tokenMissing = !MAPBOX_TOKEN;
  const [gate, setGate] = useState(tokenMissing ? 'token' : 'loading');
  const [quotaMsg, setQuotaMsg] = useState('');
  // Freeze initial lightPreset for Map constructor; later toggles use MapLightPreset.
  const initialBasemapConfig = useRef(basemapConfigForTheme(theme.mode)).current;

  useEffect(() => {
    if (tokenMissing) return undefined;
    let cancelled = false;
    setGate('loading');
    reserveMapLoadOnce()
      .then(() => {
        if (!cancelled) setGate('ok');
      })
      .catch((e) => {
        if (cancelled) return;
        setQuotaMsg(e.message || 'Mapbox map quota exceeded');
        setGate('denied');
      });
    return () => { cancelled = true; };
  }, [tokenMissing]);

  return (
    <MapProvider>
      <div className="cycle-map-root">
        {tokenMissing && (
          <div className="cycle-map-token-banner">
            Set <code>REACT_APP_MAPBOX_TOKEN</code> (public pk. token) in{' '}
            <code>5_frontend/.env</code> and restart npm. See{' '}
            <code>.env.example</code>.
          </div>
        )}
        {gate === 'denied' && (
          <div className="cycle-map-token-banner">
            {quotaMsg || 'Monthly Mapbox map-load limit reached. Try again next month.'}
          </div>
        )}
        {gate === 'loading' && !tokenMissing && (
          <div className="cycle-map-token-banner" style={{ background: '#e8f4fd', color: '#0b3d5c', borderColor: '#b6d9f2' }}>
            Checking map quota…
          </div>
        )}
        {gate === 'ok' && (
          <Map
            id="main"
            mapboxAccessToken={MAPBOX_TOKEN}
            mapStyle={MAP_STYLE}
            config={initialBasemapConfig}
            initialViewState={DEFAULT_VIEW}
            style={{ width: '100%', height: '100%' }}
            attributionControl
            onClick={onClick}
            onContextMenu={onContextMenu}
            cursor="default"
            reuseMaps
          >
            <MapLightPreset themeMode={theme.mode} />
            {showNavigationControl && (
              <NavigationControl position="bottom-right" showCompass={false} />
            )}
            <MapFlyTo target={flyTarget} />
            <PointMarkers start={start} end={end} vias={vias} />
            <WalkAndInspectLayers
              walkStartPath={walkStartPath}
              walkEndPath={walkEndPath}
              inspectorGeo={inspectorGeo}
              theme={theme}
            />
            {routeRevealed && routeLegs && routeLegs.length > 1 ? (
              <MultiLegRouteLayers
                routeLegs={routeLegs}
                activeLegIndex={activeLegIndex}
                theme={theme}
                overlayVisibility={overlayVisibility}
                lightingActive={lightingActive}
              />
            ) : (
              routeRevealed && (
                <SingleRouteLayers
                  fastestPath={fastestPath}
                  safestPath={safestPath}
                  litSegments={litSegments}
                  steepSegments={steepSegments}
                  tflCyclewayChunks={tflCyclewayChunks}
                  greenChunks={greenChunks}
                  vehicularFreeChunks={vehicularFreeChunks}
                  disruptionChunks={disruptionChunks}
                  nodeHighlights={nodeHighlights}
                  overlayVisibility={overlayVisibility}
                  lightingActive={lightingActive}
                  theme={theme}
                />
              )
            )}
            {children}
          </Map>
        )}
      </div>
    </MapProvider>
  );
}

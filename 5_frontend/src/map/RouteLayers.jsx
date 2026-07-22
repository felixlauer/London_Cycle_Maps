import React, { useEffect, useMemo, useState } from 'react';
import { Source, Layer, Popup, useMap } from 'react-map-gl/mapbox';
import { pathsToMultiLineGeoJSON, pathToLineGeoJSON } from './coords';

const EMPTY_FC = { type: 'FeatureCollection', features: [] };

/** Keep custom lines vivid under Mapbox Standard night lighting. */
const EMISSIVE = { 'line-emissive-strength': 1 };

function LineSource({ id, data, color, width, opacity, dashArray }) {
  const paint = {
    'line-color': color,
    'line-width': width,
    'line-opacity': opacity,
    ...EMISSIVE,
  };
  if (dashArray) paint['line-dasharray'] = dashArray;
  return (
    <Source id={id} type="geojson" data={data || EMPTY_FC}>
      <Layer
        id={`${id}-line`}
        type="line"
        paint={paint}
        layout={{ 'line-join': 'round', 'line-cap': 'round' }}
      />
    </Source>
  );
}

/** Beeline-style cased polyline (casing drawn under the core stroke). */
function CasedLineSource({
  id,
  data,
  color,
  casingColor,
  width = 5,
  casingWidth = 13,
  opacity = 1,
  dashArray,
  casingDashArray,
}) {
  const corePaint = {
    'line-color': color,
    'line-width': width,
    'line-opacity': opacity,
    ...EMISSIVE,
  };
  if (dashArray) corePaint['line-dasharray'] = dashArray;
  const casePaint = {
    'line-color': casingColor,
    'line-width': casingWidth,
    'line-opacity': opacity,
    ...EMISSIVE,
  };
  if (casingDashArray) casePaint['line-dasharray'] = casingDashArray;
  return (
    <Source id={id} type="geojson" data={data || EMPTY_FC}>
      <Layer
        id={`${id}-casing`}
        type="line"
        paint={casePaint}
        layout={{ 'line-join': 'round', 'line-cap': 'round' }}
      />
      <Layer
        id={`${id}-line`}
        type="line"
        paint={corePaint}
        layout={{ 'line-join': 'round', 'line-cap': 'round' }}
      />
    </Source>
  );
}

function overlayFc(chunks) {
  return pathsToMultiLineGeoJSON(chunks || []);
}

/** Point overlays (barriers, signals, junctions, calming) with zoom-scaled circles + click popup. */
export function NodeHighlightLayer({
  nodeHighlights,
  showBarriers,
  showSignals,
  showJunctionDanger,
  showCalming,
  theme,
  sourceId = 'node-highlights',
}) {
  const [popup, setPopup] = useState(null);

  const data = useMemo(() => {
    const filtered = (nodeHighlights || []).filter((h) =>
      (h.type === 'barrier' && showBarriers)
      || (h.type === 'signal' && showSignals)
      || ((h.type === 'junction' || h.type === 'junction_danger' || h.type === 'give_way' || h.type === 'stop_sign') && showJunctionDanger)
      || (h.type === 'calming' && showCalming)
    );
    return {
      type: 'FeatureCollection',
      features: filtered.map((h, i) => ({
        type: 'Feature',
        properties: {
          i,
          type: h.type,
          isDanger: h.type === 'junction_danger' ? 1 : 0,
          color:
            h.type === 'barrier' ? theme.nodeBarrier
              : h.type === 'signal' ? theme.nodeSignal
                : h.type === 'calming' ? theme.nodeCalming
                  : theme.nodeJunction,
          details: JSON.stringify(h.details || {}),
        },
        geometry: { type: 'Point', coordinates: [h.lon, h.lat] },
      })),
    };
  }, [nodeHighlights, showBarriers, showSignals, showJunctionDanger, showCalming, theme]);

  const maps = useMap();
  const map = maps.main || maps.current;

  useEffect(() => {
    if (!map) return undefined;
    const layerId = `${sourceId}-circle`;
    const onClick = (e) => {
      const f = e.features?.[0];
      if (!f) return;
      let details = {};
      try { details = JSON.parse(f.properties.details || '{}'); } catch { /* ignore */ }
      setPopup({
        longitude: e.lngLat.lng,
        latitude: e.lngLat.lat,
        type: f.properties.type,
        details,
      });
    };
    map.on('click', layerId, onClick);
    map.on('mouseenter', layerId, () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', layerId, () => { map.getCanvas().style.cursor = ''; });
    return () => {
      map.off('click', layerId, onClick);
      map.off('mouseenter', layerId);
      map.off('mouseleave', layerId);
    };
  }, [map, sourceId]);

  return (
    <>
      <Source id={sourceId} type="geojson" data={data}>
        <Layer
          id={`${sourceId}-circle`}
          type="circle"
          paint={{
            'circle-color': ['get', 'color'],
            'circle-stroke-color': '#333',
            'circle-stroke-width': 1.5,
            'circle-opacity': 0.9,
            'circle-radius': [
              'interpolate', ['linear'], ['zoom'],
              11, ['case', ['==', ['get', 'isDanger'], 1], 4, 3],
              16, ['case', ['==', ['get', 'isDanger'], 1], 12, 9],
            ],
          }}
        />
      </Source>
      {popup && (
        <Popup
          longitude={popup.longitude}
          latitude={popup.latitude}
          anchor="bottom"
          onClose={() => setPopup(null)}
          closeOnClick={false}
        >
          <div style={{ fontSize: '12px', minWidth: '120px', color: '#111' }}>
            <strong style={{ textTransform: 'capitalize' }}>{String(popup.type || '').replace('_', ' ')}</strong>
            {Object.entries(popup.details || {}).map(([k, v]) => (
              <div key={k}><span style={{ color: '#666' }}>{k}:</span> {String(v)}</div>
            ))}
          </div>
        </Popup>
      )}
    </>
  );
}

function ActiveLegOverlays({ safest, overlayVisibility, lightingActive, theme, prefix }) {
  return (
    <>
      {overlayVisibility.lit && lightingActive && (
        <LineSource
          id={`${prefix}-lit`}
          data={overlayFc(safest.lit_chunks)}
          color={theme.litColor}
          width={4}
          opacity={1}
        />
      )}
      {overlayVisibility.steep && !overlayVisibility.lit && (
        <LineSource
          id={`${prefix}-steep`}
          data={overlayFc(safest.steep_chunks)}
          color={theme.steepColor}
          width={5}
          opacity={1}
        />
      )}
      {overlayVisibility.tflCycleway && (
        <LineSource
          id={`${prefix}-tfl`}
          data={overlayFc(safest.tfl_cycleway_chunks)}
          color={theme.tflCyclewayColor}
          width={4}
          opacity={0.9}
        />
      )}
      {overlayVisibility.green && (
        <LineSource
          id={`${prefix}-green`}
          data={overlayFc(safest.green_chunks)}
          color={theme.greenColor}
          width={4}
          opacity={0.9}
        />
      )}
      {overlayVisibility.vehicularFree && (
        <LineSource
          id={`${prefix}-vf`}
          data={overlayFc(safest.vehicular_free_chunks)}
          color={theme.vehicularFreeColor}
          width={4}
          opacity={0.9}
        />
      )}
      {overlayVisibility.disruptions && (
        <LineSource
          id={`${prefix}-dis`}
          data={overlayFc(safest.disruption_chunks)}
          color={theme.disruptionColor}
          width={5}
          opacity={0.9}
        />
      )}
      {(overlayVisibility.barriers || overlayVisibility.signals || overlayVisibility.junctionDanger || overlayVisibility.calming) && (
        <NodeHighlightLayer
          sourceId={`${prefix}-nodes`}
          nodeHighlights={safest.node_highlights || []}
          showBarriers={overlayVisibility.barriers}
          showSignals={overlayVisibility.signals}
          showJunctionDanger={overlayVisibility.junctionDanger}
          showCalming={overlayVisibility.calming}
          theme={theme}
        />
      )}
    </>
  );
}

export function MultiLegRouteLayers({
  routeLegs,
  activeLegIndex,
  theme,
  overlayVisibility,
  lightingActive,
}) {
  const maps = useMap();
  const map = maps.main || maps.current;

  // Pointer cursor on dimmed (inactive) leg strokes.
  useEffect(() => {
    if (!map || !routeLegs || routeLegs.length <= 1) return undefined;
    const onEnter = () => { map.getCanvas().style.cursor = 'pointer'; };
    const onLeave = () => { map.getCanvas().style.cursor = ''; };
    let attached = [];

    const sync = () => {
      attached.forEach((id) => {
        map.off('mouseenter', id, onEnter);
        map.off('mouseleave', id, onLeave);
      });
      attached = [];
      routeLegs.forEach((_, i) => {
        if (i === activeLegIndex) return;
        ['safe', 'fast'].forEach((kind) => {
          ['casing', 'line'].forEach((part) => {
            const id = `${kind}-${i}-${part}`;
            if (!map.getLayer(id)) return;
            map.on('mouseenter', id, onEnter);
            map.on('mouseleave', id, onLeave);
            attached.push(id);
          });
        });
        const hitId = `safe-${i}-hit`;
        if (map.getLayer(hitId)) {
          map.on('mouseenter', hitId, onEnter);
          map.on('mouseleave', hitId, onLeave);
          attached.push(hitId);
        }
      });
    };

    sync();
    map.once('idle', sync);
    return () => {
      map.off('idle', sync);
      attached.forEach((id) => {
        map.off('mouseenter', id, onEnter);
        map.off('mouseleave', id, onLeave);
      });
      map.getCanvas().style.cursor = '';
    };
  }, [map, routeLegs, activeLegIndex]);

  return (routeLegs || []).map((leg, i) => {
    const active = i === activeLegIndex;
    const safest = leg?.safest || {};
    return (
      <React.Fragment key={`leg-${i}`}>
        {leg?.fastest?.path?.length > 1 && (
          <CasedLineSource
            id={`fast-${i}`}
            data={pathToLineGeoJSON(leg.fastest.path)}
            color={theme.routeFastestCore || '#d4d4d8'}
            casingColor={theme.routeFastestCasing || '#52525b'}
            width={active ? 4 : 3}
            casingWidth={active ? 8 : 6}
            opacity={active ? 0.85 : 0.28}
          />
        )}
        {safest.path?.length > 1 && (
          <CasedLineSource
            id={`safe-${i}`}
            data={pathToLineGeoJSON(safest.path)}
            color={theme.routeOptimized}
            casingColor={theme.routeOptimizedCasing || '#ffffff'}
            width={active ? 5 : 4}
            casingWidth={active ? 13 : 10}
            opacity={active ? 1.0 : 0.4}
          />
        )}
        {!active && safest.path?.length > 1 && (
          <Source id={`safe-${i}-hit`} type="geojson" data={pathToLineGeoJSON(safest.path)}>
            <Layer
              id={`safe-${i}-hit`}
              type="line"
              paint={{
                'line-color': '#000',
                'line-width': 18,
                'line-opacity': 0,
              }}
              layout={{ 'line-join': 'round', 'line-cap': 'round' }}
            />
          </Source>
        )}
        {active && (
          <ActiveLegOverlays
            safest={safest}
            overlayVisibility={overlayVisibility}
            lightingActive={lightingActive}
            theme={theme}
            prefix={`leg-${i}`}
          />
        )}
      </React.Fragment>
    );
  });
}

/**
 * Hit-test a map click against dimmed multi-leg strokes.
 * Returns the leg index, or null if the click missed inactive legs.
 */
export function pickInactiveLegIndex(map, point, routeLegs, activeLegIndex) {
  if (!map?.queryRenderedFeatures || !point || !routeLegs || routeLegs.length <= 1) {
    return null;
  }
  const layers = [];
  for (let i = 0; i < routeLegs.length; i += 1) {
    if (i === activeLegIndex) continue;
    ['safe', 'fast'].forEach((kind) => {
      ['casing', 'line'].forEach((part) => {
        const id = `${kind}-${i}-${part}`;
        if (map.getLayer(id)) layers.push(id);
      });
    });
    const hitId = `safe-${i}-hit`;
    if (map.getLayer(hitId)) layers.push(hitId);
  }
  if (!layers.length) return null;
  const hits = map.queryRenderedFeatures(point, { layers });
  if (!hits.length) return null;
  const match = String(hits[0].layer?.id || '').match(/^(?:safe|fast)-(\d+)/);
  return match ? Number(match[1]) : null;
}

export function SingleRouteLayers({
  fastestPath,
  safestPath,
  litSegments,
  steepSegments,
  tflCyclewayChunks,
  greenChunks,
  vehicularFreeChunks,
  disruptionChunks,
  nodeHighlights,
  overlayVisibility,
  lightingActive,
  theme,
}) {
  return (
    <>
      {fastestPath?.length > 1 && (
        <CasedLineSource
          id="fast-single"
          data={pathToLineGeoJSON(fastestPath)}
          color={theme.routeFastestCore || '#d4d4d8'}
          casingColor={theme.routeFastestCasing || '#52525b'}
          width={4}
          casingWidth={8}
          opacity={0.85}
        />
      )}
      {safestPath?.length > 1 && (
        <CasedLineSource
          id="safe-single"
          data={pathToLineGeoJSON(safestPath)}
          color={theme.routeOptimized}
          casingColor={theme.routeOptimizedCasing || '#ffffff'}
          width={5}
          casingWidth={13}
          opacity={1}
        />
      )}
      <ActiveLegOverlays
        safest={{
          lit_chunks: litSegments,
          steep_chunks: steepSegments,
          tfl_cycleway_chunks: tflCyclewayChunks,
          green_chunks: greenChunks,
          vehicular_free_chunks: vehicularFreeChunks,
          disruption_chunks: disruptionChunks,
          node_highlights: nodeHighlights,
        }}
        overlayVisibility={overlayVisibility}
        lightingActive={lightingActive}
        theme={theme}
        prefix="single"
      />
    </>
  );
}

export function WalkAndInspectLayers({ walkStartPath, walkEndPath, inspectorGeo, theme }) {
  const primary = theme?.routeOptimized || '#FF0061';
  const casing = theme?.routeOptimizedCasing || '#ffffff';
  // Dash lengths in px, converted per line-width so casing + core stay aligned.
  const dashPx = 14;
  const gapPx = 10;
  const coreW = 5;
  const caseW = 13;
  const coreDash = [dashPx / coreW, gapPx / coreW];
  const caseDash = [dashPx / caseW, gapPx / caseW];
  return (
    <>
      {walkStartPath?.length > 1 && (
        <CasedLineSource
          id="walk-start"
          data={pathToLineGeoJSON(walkStartPath)}
          color={primary}
          casingColor={casing}
          width={coreW}
          casingWidth={caseW}
          opacity={0.95}
          dashArray={coreDash}
          casingDashArray={caseDash}
        />
      )}
      {walkEndPath?.length > 1 && (
        <CasedLineSource
          id="walk-end"
          data={pathToLineGeoJSON(walkEndPath)}
          color={primary}
          casingColor={casing}
          width={coreW}
          casingWidth={caseW}
          opacity={0.95}
          dashArray={coreDash}
          casingDashArray={caseDash}
        />
      )}
      {inspectorGeo?.length > 1 && (
        <LineSource
          id="inspect-seg"
          data={pathToLineGeoJSON(inspectorGeo)}
          color="red"
          width={6}
          opacity={0.8}
        />
      )}
    </>
  );
}

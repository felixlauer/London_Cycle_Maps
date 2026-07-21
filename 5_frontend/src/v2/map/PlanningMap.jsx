import React, { useMemo } from 'react';
import CycleMap from '../../map/CycleMap';
import { emptyOverlayVisibility } from '../../routeOverlayCatalog';
import SantanderStationsLayer from '../../components/santander/SantanderStationsLayer';
import { themeForMode } from './theme';
import MapApiBridge from './MapApiBridge';
import UserLocationMarker from './UserLocationMarker';
import V2OverlayLayers from './V2OverlayLayers';

const noop = () => {};

/**
 * Planning map for v2 — routes, markers, Santander hire pins, locate, overlays.
 */
export default function PlanningMap({
  themeMode = 'light',
  flyTarget = null,
  start = null,
  end = null,
  vias = [],
  onClick = noop,
  routeRevealed = false,
  routeLegs = null,
  activeLegIndex = 0,
  fastestPath = null,
  safestPath = null,
  safestData = null,
  walkStartPath = null,
  walkEndPath = null,
  hireStations = [],
  hireStep = 'idle',
  hireNeed = 'bikes',
  pickupStation = null,
  dropoffStation = null,
  expandedStationId = null,
  onStationExpand = noop,
  onStationConfirm = noop,
  mapApiRef = null,
  onNorthUpChange = noop,
  userLocation = null,
  overlayMode = 'cycle',
  units = 'metric',
  routeHover = null,
  onRouteHoverChange = noop,
}) {
  const theme = useMemo(() => themeForMode(themeMode), [themeMode]);
  const overlayVisibility = useMemo(() => emptyOverlayVisibility(), []);

  const showCandidates = (hireStep === 'pickup' || hireStep === 'dropoff')
    && hireStations.length > 0;

  const activeSafest = useMemo(() => {
    if (routeLegs && routeLegs.length > 1) {
      return routeLegs[activeLegIndex]?.safest || safestData;
    }
    return safestData;
  }, [routeLegs, activeLegIndex, safestData]);

  return (
    <CycleMap
      theme={theme}
      flyTarget={flyTarget}
      start={start}
      end={end}
      vias={vias}
      onClick={onClick}
      onContextMenu={noop}
      routeRevealed={routeRevealed}
      routeLegs={routeLegs}
      activeLegIndex={activeLegIndex}
      overlayVisibility={overlayVisibility}
      lightingActive={false}
      fastestPath={fastestPath}
      safestPath={safestPath}
      litSegments={null}
      steepSegments={null}
      tflCyclewayChunks={null}
      greenChunks={null}
      vehicularFreeChunks={null}
      disruptionChunks={null}
      nodeHighlights={null}
      walkStartPath={walkStartPath}
      walkEndPath={walkEndPath}
      inspectorGeo={null}
      showNavigationControl={false}
    >
      <MapApiBridge apiRef={mapApiRef} onNorthUpChange={onNorthUpChange} />
      {userLocation && <UserLocationMarker location={userLocation} />}
      {routeRevealed && activeSafest && (
        <V2OverlayLayers
          safest={activeSafest}
          modeId={overlayMode}
          prefix="v2"
          units={units}
          externalHover={routeHover?.source === 'island' ? routeHover : null}
          onHoverChange={onRouteHoverChange}
        />
      )}
      {hireStep === 'dropoff' && pickupStation && (
        <SantanderStationsLayer
          stations={[pickupStation]}
          expandedId={null}
          showConfirm={false}
          availabilityNeed="bikes"
        />
      )}
      {showCandidates && (
        <SantanderStationsLayer
          stations={hireStations}
          expandedId={expandedStationId}
          onExpand={onStationExpand}
          onConfirm={onStationConfirm}
          confirmLabel={hireStep === 'pickup' ? 'Pick up here' : 'Drop off here'}
          showConfirm
          availabilityNeed={hireNeed}
        />
      )}
      {hireStep === 'done' && (pickupStation || dropoffStation) && (
        <SantanderStationsLayer
          stations={[pickupStation, dropoffStation].filter(Boolean)}
          compact
        />
      )}
    </CycleMap>
  );
}

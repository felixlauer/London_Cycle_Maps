import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
} from 'react';
import CollapsedIsland from '../../island/CollapsedIsland';
import ExpandedIsland from '../../island/ExpandedIsland';
import IslandLegLatch, { formatLegLabel } from '../../island/IslandLegPager';
import { resolveIslandSlots } from '../../island/resolveIslandSlots';
import { buildDistanceIndex, lngLatAtDistance } from '../../island/routeGeometry';
import { useIsMobile } from '../../hooks/useMediaQuery';
import '../../island/island.css';

/**
 * Bottom-center Dynamic Island — hidden without a route, collapsed pill
 * once one is ready, Beeline-style sheet when expanded. Overlay only:
 * the map canvas never resizes with it.
 */
export default function DynamicIslandZone({
  visible = false,
  safest = null,
  fastest = null,
  overlayMode = null,
  bikeType = 'standard',
  isDarkOutside = false,
  profile = null,
  units = 'metric',
  expanded = false,
  onExpandedChange,
  routeHover = null,
  onIslandHover,
  santander = false,
  pickupStation = null,
  dropoffStation = null,
  walkStats = null,
  legCount = 1,
  activeLegIndex = 0,
  onChangeLeg,
  viaCount = 0,
  startCoord = null,
  departAtIso = null,
}) {
  const zoneRef = useRef(null);
  const segRef = useRef(null);
  const pointRef = useRef(null);
  const isMobile = useIsMobile();

  const slots = useMemo(
    () => resolveIslandSlots({
      safest,
      overlayMode,
      bikeType,
      isDarkOutside,
      profile,
      // Mobile expanded page has less vertical room — keep charts scannable.
      maxBarCharts: isMobile ? 2 : undefined,
      barBudget: isMobile ? 5 : undefined,
    }),
    [safest, overlayMode, bikeType, isDarkOutside, profile, isMobile],
  );

  const index = useMemo(
    () => (safest?.path?.length ? buildDistanceIndex(safest.path) : null),
    [safest],
  );

  const mapHover = routeHover?.source === 'map' ? routeHover : null;

  const pushHover = useCallback(() => {
    if (!onIslandHover) return;
    const seg = segRef.current;
    const point = pointRef.current;
    if (!seg && !point) {
      onIslandHover(null);
      return;
    }
    onIslandHover({ source: 'island', ...(seg || {}), point });
  }, [onIslandHover]);

  const handleSegmentHover = useCallback((seg) => {
    segRef.current = seg
      ? {
        modeId: seg.modeId,
        kind: seg.kind,
        runIds: seg.runIds || null,
        runId: seg.runIds?.length === 1 ? seg.runIds[0] : null,
      }
      : null;
    pushHover();
  }, [pushHover]);

  const handleScrub = useCallback((d) => {
    pointRef.current = d != null && index ? lngLatAtDistance(index, d) : null;
    pushHover();
  }, [index, pushHover]);

  useEffect(() => {
    if (!visible) {
      segRef.current = null;
      pointRef.current = null;
      pushHover();
      return;
    }
    segRef.current = null;
    pointRef.current = null;
    pushHover();
  }, [visible, expanded, pushHover]);

  useEffect(() => {
    segRef.current = null;
    pointRef.current = null;
    pushHover();
  }, [activeLegIndex, pushHover]);

  if (!visible || !safest) return null;

  const multi = legCount > 1;

  return (
    <section
      ref={zoneRef}
      className={`shell-zone shell-zone--island${expanded ? ' is-expanded' : ''}${santander ? ' is-santander' : ''}${multi ? ' is-multi' : ''}`}
      aria-label="Route analysis"
      data-zone="dynamic-island"
    >
      {multi && (
        <>
          <IslandLegLatch
            legCount={legCount}
            activeLegIndex={activeLegIndex}
            onChangeLeg={onChangeLeg}
          />
          <span className="sr-only">{formatLegLabel(activeLegIndex, legCount, viaCount)}</span>
        </>
      )}
      <div className="island-body">
        <div className="island-layer island-layer--collapsed" aria-hidden={expanded}>
          <CollapsedIsland
            safest={safest}
            fastest={fastest}
            slots={slots}
            units={units}
            onExpand={() => onExpandedChange?.(true)}
            legCount={legCount}
            activeLegIndex={activeLegIndex}
            onChangeLeg={onChangeLeg}
            externalHover={mapHover}
            onSegmentHover={handleSegmentHover}
          />
        </div>
        <div className="island-layer island-layer--expanded" aria-hidden={!expanded}>
          {expanded && (
            <ExpandedIsland
              safest={safest}
              fastest={fastest}
              units={units}
              overlayMode={overlayMode}
              barModes={slots.bars}
              index={index}
              externalHover={mapHover}
              onSegmentHover={handleSegmentHover}
              onScrub={handleScrub}
              onCollapse={() => onExpandedChange?.(false)}
              santander={santander}
              pickupStation={pickupStation}
              dropoffStation={dropoffStation}
              walkStats={walkStats}
              legCount={legCount}
              activeLegIndex={activeLegIndex}
              onChangeLeg={onChangeLeg}
              viaCount={viaCount}
              startCoord={startCoord}
              departAtIso={departAtIso}
            />
          )}
        </div>
      </div>
    </section>
  );
}

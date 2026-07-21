import React, { useCallback, useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { OVERLAY_KIND_META } from '../map/overlayModes';
import MetricCell from './MetricCell';
import ElevationChart from './ElevationChart';
import ModeBarCharts from './ModeBarCharts';
import IslandHireStations from './IslandHireStations';
import IslandLegPager, { formatLegLabel } from './IslandLegPager';
import WeatherPanel from './weather/WeatherPanel';
import useRouteWeather from './weather/useRouteWeather';
import { resolveExtremeWarning } from './weather/resolveExtreme';
import { modeChunksFor } from './modeData';
import { buildSlices } from './routeGeometry';
import {
  formatDurationParts,
  formatDistanceParts,
  formatTimeDelta,
  formatDistanceDelta,
  formatWalkParts,
} from './metrics';

const NODE_TYPES = new Set(['barrier', 'signal', 'calming']);

function toSlices(chunks, index, modeId) {
  return buildSlices(chunks, index).map((s, i) => ({
    ...s,
    modeId,
    color: OVERLAY_KIND_META[s.kind]?.color || '#a1a1aa',
    key: `${modeId}-${s.kind}-${i}`,
  }));
}

function nodeLabel(n) {
  const details = n.details || {};
  if (n.type === 'barrier') {
    const raw = String(details.barrier || 'barrier').replace(/_/g, ' ');
    return `Barrier: ${raw}`;
  }
  if (n.type === 'signal') return 'Traffic signals';
  if (n.type === 'calming') {
    const raw = String(details.traffic_calming || 'calming').replace(/_/g, ' ');
    return `Traffic calming: ${raw}`;
  }
  return n.type;
}

/**
 * Expanded sheet — metrics | elevation chart | bar charts.
 * Santander: left quarter splits into stacked metrics + hire station cards.
 * Non-Santander: full metrics; only on extreme weather → stacked metrics + warning.
 * Multi-leg: top pager switches the active leg (charts/map follow).
 */
export default function ExpandedIsland({
  safest,
  fastest,
  units,
  overlayMode,
  barModes,
  index,
  externalHover,
  onSegmentHover,
  onScrub,
  onCollapse,
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
  const [sheetHover, setSheetHover] = useState(null);
  const sStats = safest?.stats || {};
  const fStats = fastest?.stats || {};
  const totalM = index?.totalM || Number(sStats.length_m) || 0;

  const chartHover = sheetHover || externalHover || null;
  const walkParts = santander
    ? formatWalkParts(walkStats?.duration_min, walkStats?.distance_m, units)
    : null;

  const weatherEnabled = !santander && Boolean(startCoord);
  const { data: weather, ready: weatherReady } = useRouteWeather({
    lat: startCoord?.[0],
    lon: startCoord?.[1],
    atIso: departAtIso || null,
    enabled: weatherEnabled,
  });

  const extremeWarning = useMemo(() => {
    if (!weatherReady || !weather) return null;
    return resolveExtremeWarning(weather);
  }, [weatherReady, weather]);

  const handleHover = useCallback((seg) => {
    setSheetHover(seg);
    onSegmentHover?.(seg);
  }, [onSegmentHover]);

  const modeSlices = useMemo(() => {
    if (!overlayMode || !index) return [];
    return toSlices(modeChunksFor(safest, overlayMode), index, overlayMode);
  }, [safest, overlayMode, index]);

  const slices = useMemo(() => {
    const hoverMode = chartHover?.modeId;
    if (!hoverMode || !index || hoverMode === overlayMode || hoverMode === 'traffic') {
      return modeSlices;
    }
    const extra = toSlices(modeChunksFor(safest, hoverMode), index, hoverMode)
      .filter((s) => !chartHover.kind || s.kind === chartHover.kind);
    return [...modeSlices, ...extra];
  }, [modeSlices, chartHover, safest, overlayMode, index]);

  const trafficSlices = useMemo(() => {
    if (!index) return [];
    return toSlices(modeChunksFor(safest, 'traffic'), index, 'traffic');
  }, [safest, index]);

  const nodeMarkers = useMemo(() => {
    if (!barModes?.includes('cycle') || !index) return [];
    const raw = (safest?.node_highlights || [])
      .filter((n) => NODE_TYPES.has(n.type))
      .map((n, i) => ({
        key: `${n.type}-${i}`,
        type: n.type,
        label: nodeLabel(n),
        d: index.nearestDist(Number(n.lat), Number(n.lon)),
      }))
      .sort((a, b) => a.d - b.d);
    const minGap = Math.max(1, index.totalM * 0.025);
    const kept = [];
    raw.forEach((m) => {
      if (!kept.length || m.d - kept[kept.length - 1].d >= minGap) kept.push(m);
    });
    return kept;
  }, [safest, barModes, index]);

  const showExtremeSlot = Boolean(extremeWarning);
  const metricsStacked = santander || showExtremeSlot;

  const metricsBlock = (
    <div className={`island-expanded__metrics${metricsStacked ? ' is-stacked' : ''}`}>
      <div className="island-expanded__metric-block">
        {walkParts?.time && <div className="island-metric__walk">{walkParts.time}</div>}
        <MetricCell
          ariaLabel="Trip time"
          parts={formatDurationParts(sStats.duration_min)}
          delta={formatTimeDelta(sStats.duration_min, fStats.duration_min)}
        />
      </div>
      <div className="island-expanded__metric-block">
        {walkParts?.distance && <div className="island-metric__walk">{walkParts.distance}</div>}
        <MetricCell
          ariaLabel="Trip distance"
          parts={formatDistanceParts(sStats.length_m, units)}
          delta={formatDistanceDelta(sStats.length_m, fStats.length_m, units)}
        />
      </div>
    </div>
  );

  const leftColumn = showExtremeSlot ? (
    <div className="island-expanded__left">
      {metricsBlock}
      <div className="island-expanded__weather">
        <WeatherPanel warning={extremeWarning} />
      </div>
    </div>
  ) : (
    metricsBlock
  );

  const body = (
    <div className={`island-expanded__grid${santander ? ' is-santander' : ''}`}>
      {leftColumn}
      {santander && (
        <div className="island-expanded__hire">
          <IslandHireStations pickup={pickupStation} dropoff={dropoffStation} />
        </div>
      )}
      <div className="island-expanded__chart">
        <ElevationChart
          profile={safest?.elevation_profile}
          totalM={totalM}
          slices={slices}
          trafficSlices={trafficSlices}
          nodeMarkers={nodeMarkers}
          units={units}
          externalHover={chartHover}
          onSegmentHover={handleHover}
          onScrub={onScrub}
        />
      </div>
      <div className="island-expanded__bars">
        <ModeBarCharts
          safest={safest}
          modes={barModes}
          externalHover={chartHover}
          onHoverChange={handleHover}
        />
      </div>
    </div>
  );

  return (
    <div className={`island-expanded${santander ? ' is-santander' : ''}`}>
      <button
        type="button"
        className="island-expanded__collapse"
        aria-label="Collapse route analysis"
        onClick={onCollapse}
      >
        <ChevronDown size={16} strokeWidth={2.2} aria-hidden />
      </button>

      <IslandLegPager
        legCount={legCount}
        activeLegIndex={activeLegIndex}
        onChangeLeg={onChangeLeg}
        legLabel={formatLegLabel(activeLegIndex, legCount, viaCount)}
      >
        {body}
      </IslandLegPager>
    </div>
  );
}

import React, { useCallback, useMemo, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { OVERLAY_KIND_META } from '../map/overlayModes';
import MetricCell from './MetricCell';
import ElevationChart from './ElevationChart';
import ModeBarCharts from './ModeBarCharts';
import IslandHireStations from './IslandHireStations';
import WeatherPanel from './weather/WeatherPanel';
import useRouteWeather from './weather/useRouteWeather';
import { resolveExtremeWarning } from './weather/resolveExtreme';
import { modeChunksFor } from './modeData';
import { buildSlices } from './routeGeometry';
import { useIsMobile } from '../hooks/useMediaQuery';
import {
  formatDurationParts,
  formatDistanceParts,
  formatTimeDelta,
  formatDistanceDelta,
  formatWalkParts,
} from './metrics';

const NODE_TYPES = new Set(['barrier', 'signal', 'calming']);
const PAGE_METRICS = 0;
const PAGE_CHART = 1;
const PAGE_BARS = 2;
const PAGE_LABELS = ['Core metrics', 'Chart overview', 'Detailed analysis'];

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
 * Expanded sheet — desktop 3-col grid; mobile swipe pages (metrics | chart | bars).
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
  const isMobile = useIsMobile();
  const [sheetHover, setSheetHover] = useState(null);
  const [page, setPage] = useState(PAGE_CHART);
  const touchStart = useRef(null);
  const sStats = safest?.stats || {};
  const fStats = fastest?.stats || {};
  const totalM = index?.totalM || Number(sStats.length_m) || 0;

  const chartHover = sheetHover || externalHover || null;
  const walkParts = santander
    ? formatWalkParts(walkStats?.duration_min, walkStats?.distance_m, units)
    : null;

  const weatherEnabled = !isMobile && !santander && Boolean(startCoord);
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

  const showExtremeSlot = !isMobile && Boolean(extremeWarning);
  const metricsStacked = santander || showExtremeSlot;
  const deltaCompare = isMobile ? 'non-tuned' : 'shortest';

  const metricsBlock = (
    <div className={`island-expanded__metrics${metricsStacked ? ' is-stacked' : ''}`}>
      <div className="island-expanded__metric-block">
        {walkParts?.time && <div className="island-metric__walk">{walkParts.time}</div>}
        <MetricCell
          ariaLabel="Trip time"
          parts={formatDurationParts(sStats.duration_min)}
          delta={formatTimeDelta(sStats.duration_min, fStats.duration_min, { compare: deltaCompare })}
        />
      </div>
      <div className="island-expanded__metric-block">
        {walkParts?.distance && <div className="island-metric__walk">{walkParts.distance}</div>}
        <MetricCell
          ariaLabel="Trip distance"
          parts={formatDistanceParts(sStats.length_m, units)}
          delta={formatDistanceDelta(sStats.length_m, fStats.length_m, units, { compare: deltaCompare })}
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

  const metricsPage = santander ? (
    <div className="island-expanded__page island-expanded__page--metrics is-santander">
      {metricsBlock}
      <div className="island-expanded__hire">
        <IslandHireStations pickup={pickupStation} dropoff={dropoffStation} />
      </div>
    </div>
  ) : leftColumn;

  const chartPage = (
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
  );

  const barsPage = (
    <div className="island-expanded__bars">
      <ModeBarCharts
        safest={safest}
        modes={barModes || []}
        externalHover={chartHover}
        onHoverChange={handleHover}
        maxKindsPerChart={isMobile ? 4 : Infinity}
        showOverlayHint={isMobile}
      />
    </div>
  );

  const desktopBody = (
    <div className={`island-expanded__grid${santander ? ' is-santander' : ''}`}>
      {leftColumn}
      {santander && (
        <div className="island-expanded__hire">
          <IslandHireStations pickup={pickupStation} dropoff={dropoffStation} />
        </div>
      )}
      {chartPage}
      {barsPage}
    </div>
  );

  const pages = [metricsPage, chartPage, barsPage];

  const onTouchStart = (e) => {
    touchStart.current = {
      x: e.changedTouches[0].clientX,
      y: e.changedTouches[0].clientY,
    };
  };

  const onTouchEnd = (e) => {
    if (!touchStart.current) return;
    const dx = e.changedTouches[0].clientX - touchStart.current.x;
    const dy = e.changedTouches[0].clientY - touchStart.current.y;
    touchStart.current = null;
    if (Math.abs(dy) > Math.abs(dx) && dy > 50) {
      onCollapse?.();
      return;
    }
    if (Math.abs(dx) < 40) return;
    if (dx < 0) setPage((p) => Math.min(PAGE_BARS, p + 1));
    else setPage((p) => Math.max(PAGE_METRICS, p - 1));
  };

  return (
    <div
      className={`island-expanded${santander ? ' is-santander' : ''}${isMobile ? ' is-mobile' : ''}`}
      onTouchStart={isMobile ? onTouchStart : undefined}
      onTouchEnd={isMobile ? onTouchEnd : undefined}
    >
      <button
        type="button"
        className="island-expanded__collapse"
        aria-label="Collapse route analysis"
        onClick={onCollapse}
      >
        <ChevronDown size={16} strokeWidth={2.2} aria-hidden />
      </button>

      {isMobile ? (
        <>
          <div className="island-expanded__pages" data-page={page}>
            {pages[page]}
          </div>
          <div className="island-expanded__progress" role="tablist" aria-label="Island panels">
            {[PAGE_METRICS, PAGE_CHART, PAGE_BARS].map((i) => (
              <button
                key={i}
                type="button"
                role="tab"
                aria-selected={page === i}
                className={`island-expanded__progress-item${page === i ? ' is-active' : ''}`}
                onClick={() => setPage(i)}
              >
                <span className="island-expanded__progress-label">
                  {PAGE_LABELS[i]}
                </span>
                <span
                  className={`island-expanded__progress-seg${page === i ? ' is-active' : ''}`}
                  aria-hidden
                />
              </button>
            ))}
          </div>
        </>
      ) : (
        desktopBody
      )}
    </div>
  );
}

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  onOverlayHintClick,
  onPageChange,
}) {
  const isMobile = useIsMobile();
  const [sheetHover, setSheetHover] = useState(null);
  const [page, setPage] = useState(PAGE_CHART);
  const [dragX, setDragX] = useState(0);
  const [swiping, setSwiping] = useState(false);
  const touchStart = useRef(null);
  const viewportRef = useRef(null);
  const SWIPE_EASE = '320ms cubic-bezier(0.23, 1, 0.32, 1)';

  useEffect(() => {
    onPageChange?.(page);
  }, [page, onPageChange]);

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
  const deltaCompare = isMobile ? 'non-tuned' : 'non-optimised';

  const metricsBlock = (
    <div className={`island-expanded__metrics${metricsStacked ? ' is-stacked' : ''}`}>
      <div className="island-expanded__metric-block">
        {walkParts?.time && <div className="island-metric__walk">{walkParts.time}</div>}
        <MetricCell
          ariaLabel="Trip time"
          parts={formatDurationParts(sStats.duration_min)}
          delta={formatTimeDelta(sStats.duration_min, fStats.duration_min, { compare: deltaCompare })}
          twoLineDelta={!isMobile}
        />
      </div>
      <div className="island-expanded__metric-block">
        {walkParts?.distance && <div className="island-metric__walk">{walkParts.distance}</div>}
        <MetricCell
          ariaLabel="Trip distance"
          parts={formatDistanceParts(sStats.length_m, units)}
          delta={formatDistanceDelta(sStats.length_m, fStats.length_m, units, { compare: deltaCompare })}
          twoLineDelta={!isMobile}
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
        maxKindsPerChart={isMobile ? 3 : Infinity}
        showOverlayHint={isMobile}
        onOverlayHintClick={onOverlayHintClick}
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

  useEffect(() => {
    setDragX(0);
    setSwiping(false);
  }, [page]);

  const onTouchStart = (e) => {
    const t = e.touches?.[0];
    if (!t) return;
    touchStart.current = {
      x: t.clientX,
      y: t.clientY,
      // Chart owns scrub; only steal once horizontal intent is clear.
      fromChart: Boolean(e.target?.closest?.('.island-chart')),
      locked: null, // 'page' | 'chart' | 'collapse'
    };
  };

  const onTouchMove = (e) => {
    if (!touchStart.current) return;
    const t = e.touches?.[0];
    if (!t) return;
    const dx = t.clientX - touchStart.current.x;
    const dy = t.clientY - touchStart.current.y;
    const absX = Math.abs(dx);
    const absY = Math.abs(dy);

    if (!touchStart.current.locked) {
      if (absX < 8 && absY < 8) return;
      if (touchStart.current.fromChart) {
        // Prefer chart scrub unless the gesture is clearly horizontal.
        if (absX > absY * 1.15 && absX > 18) {
          touchStart.current.locked = 'page';
        } else {
          touchStart.current.locked = 'chart';
          touchStart.current = null;
          setSwiping(false);
          setDragX(0);
          return;
        }
      } else if (absY > absX && absY > 16) {
        touchStart.current.locked = 'collapse';
      } else {
        touchStart.current.locked = 'page';
      }
    }

    if (touchStart.current.locked === 'chart') return;
    if (touchStart.current.locked === 'collapse') return;
    setSwiping(true);
    setDragX(dx);
  };

  const onTouchEnd = (e) => {
    if (!touchStart.current) return;
    const t = e.changedTouches?.[0];
    const dx = t ? t.clientX - touchStart.current.x : dragX;
    const dy = t ? t.clientY - touchStart.current.y : 0;
    const locked = touchStart.current.locked;
    touchStart.current = null;
    setSwiping(false);
    setDragX(0);

    if (locked === 'chart') return;
    if ((locked === 'collapse' || (Math.abs(dy) > Math.abs(dx) && dy > 50))) {
      if (dy > 50) onCollapse?.();
      return;
    }
    if (Math.abs(dx) < 40) return;
    if (dx < 0) setPage((p) => Math.min(PAGE_BARS, p + 1));
    else setPage((p) => Math.max(PAGE_METRICS, p - 1));
  };

  // Content swipe left (dx < 0) → next page → thumb moves right. Match by
  // converting finger delta to a fraction of the viewport width.
  const vw = viewportRef.current?.offsetWidth || 1;
  const thumbPage = page + (swiping ? (-dragX / vw) : 0);

  const trackStyle = isMobile
    ? {
      transform: `translateX(calc(${-page * 100}% + ${dragX}px))`,
      transition: swiping ? 'none' : `transform ${SWIPE_EASE}`,
    }
    : undefined;

  return (
    <div
      className={`island-expanded${santander ? ' is-santander' : ''}${isMobile ? ' is-mobile' : ''}`}
      onTouchStart={isMobile ? onTouchStart : undefined}
      onTouchMove={isMobile ? onTouchMove : undefined}
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
          <div className="island-expanded__viewport" ref={viewportRef}>
            <div className="island-expanded__track" style={trackStyle}>
              {pages.map((p, i) => (
                <div
                  key={PAGE_LABELS[i]}
                  className={`island-expanded__slide${i === page ? ' is-active' : ''}`}
                  aria-hidden={i !== page}
                >
                  {p}
                </div>
              ))}
            </div>
          </div>
          <div className="island-expanded__progress" role="tablist" aria-label="Island panels">
            <span
              className="island-expanded__progress-thumb"
              style={{
                width: 'calc((100% - 16px) / 3)',
                left: `calc(${thumbPage} * ((100% - 16px) / 3 + 8px))`,
                transition: swiping ? 'none' : `left ${SWIPE_EASE}`,
              }}
              aria-hidden
            />
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
                <span className="island-expanded__progress-seg" aria-hidden />
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

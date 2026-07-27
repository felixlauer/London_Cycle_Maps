import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Source, Layer, useMap } from 'react-map-gl/mapbox';
import { pathToLineGeoJSON } from '../../map/coords';
import { formatDurationParts, formatDistanceParts } from '../island/metrics';
import { useIsMobile } from '../hooks/useMediaQuery';
import './nonTunedHint.css';

const EMPTY_FC = { type: 'FeatureCollection', features: [] };
const HIT_ID = 'nontuned-hit';
const HIT_LAYER = 'nontuned-hit-line';

function collectLayerIds(map, ids) {
  return ids.filter((id) => map.getLayer(id));
}

function fastLayerIds(routeLegs, activeLegIndex) {
  if (routeLegs?.length > 1) {
    const i = activeLegIndex;
    return [`fast-${i}-casing`, `fast-${i}-line`, HIT_LAYER];
  }
  return ['fast-single-casing', 'fast-single-line', HIT_LAYER];
}

function safeLayerIds(routeLegs, activeLegIndex) {
  if (routeLegs?.length > 1) {
    const i = activeLegIndex;
    return [`safe-${i}-casing`, `safe-${i}-line`, `safe-${i}-hit`];
  }
  return ['safe-single-casing', 'safe-single-line'];
}

function formatStatsLine(stats, units) {
  if (!stats) return null;
  const time = formatDurationParts(stats.duration_min);
  const dist = formatDistanceParts(stats.length_m, units);
  if (!time?.value || !dist?.value) return null;
  return `${time.value} ${time.unit} · ${dist.value} ${dist.unit}`;
}

/**
 * Hover (desktop/tablet) or tap (mobile) the grey baseline route → chip with
 * "non-tuned route" + time / distance.
 */
export default function NonTunedRouteHint({
  path = null,
  stats = null,
  units = 'metric',
  routeLegs = null,
  activeLegIndex = 0,
  enabled = true,
}) {
  const maps = useMap();
  const map = maps.main || maps.current;
  const isMobile = useIsMobile();
  const [tip, setTip] = useState(null);
  const tipVisibleRef = useRef(false);

  const hitData = useMemo(
    () => (path?.length > 1 ? pathToLineGeoJSON(path) : EMPTY_FC),
    [path],
  );
  const statsLine = useMemo(() => formatStatsLine(stats, units), [stats, units]);

  useEffect(() => {
    tipVisibleRef.current = false;
    setTip(null);
  }, [path, stats, activeLegIndex, enabled]);

  useEffect(() => {
    if (!map || !enabled || !path?.length || !statsLine) return undefined;

    const probe = (point) => {
      const safeIds = collectLayerIds(map, safeLayerIds(routeLegs, activeLegIndex));
      if (safeIds.length) {
        const onPink = map.queryRenderedFeatures(point, { layers: safeIds });
        if (onPink?.length) return false;
      }
      const fastIds = collectLayerIds(map, fastLayerIds(routeLegs, activeLegIndex));
      if (!fastIds.length) return false;
      const onGrey = map.queryRenderedFeatures(point, { layers: fastIds });
      return Boolean(onGrey?.length);
    };

    const showAt = (point) => {
      tipVisibleRef.current = true;
      setTip({ x: point.x, y: point.y });
      map.getCanvas().style.cursor = 'pointer';
    };

    const clearTip = ({ resetCursor = false } = {}) => {
      const wasVisible = tipVisibleRef.current;
      tipVisibleRef.current = false;
      setTip(null);
      if (resetCursor && wasVisible) map.getCanvas().style.cursor = '';
    };

    if (isMobile) {
      const onClick = (e) => {
        if (probe(e.point)) {
          showAt(e.point);
        } else {
          clearTip();
        }
      };
      map.on('click', onClick);
      return () => {
        map.off('click', onClick);
      };
    }

    const onMove = (e) => {
      if (probe(e.point)) {
        showAt(e.point);
      } else {
        clearTip();
      }
    };
    const onLeave = () => clearTip({ resetCursor: true });

    map.on('mousemove', onMove);
    map.getCanvas().addEventListener('mouseleave', onLeave);
    return () => {
      map.off('mousemove', onMove);
      map.getCanvas().removeEventListener('mouseleave', onLeave);
    };
  }, [map, enabled, path, statsLine, routeLegs, activeLegIndex, isMobile]);

  if (!enabled || !(path?.length > 1) || !statsLine) return null;

  return (
    <>
      <Source id={HIT_ID} type="geojson" data={hitData}>
        <Layer
          id={HIT_LAYER}
          type="line"
          paint={{
            'line-color': '#000',
            'line-width': 20,
            'line-opacity': 0,
          }}
          layout={{ 'line-join': 'round', 'line-cap': 'round' }}
        />
      </Source>
      {tip && (
        <div
          className="nontuned-hint-chip"
          style={{ left: tip.x + 14, top: tip.y + 14 }}
          role="status"
        >
          <span className="nontuned-hint-chip__swatch" aria-hidden />
          <span className="nontuned-hint-chip__label">non-tuned route</span>
          <span className="nontuned-hint-chip__stats">{statsLine}</span>
        </div>
      )}
    </>
  );
}

import React, { useEffect, useMemo, useRef, useState } from 'react';
import WeatherPanel from '../../island/weather/WeatherPanel';
import useRouteWeather from '../../island/weather/useRouteWeather';
import { resolveExtremeWarning } from '../../island/weather/resolveExtreme';
import cloudy from '@meteocons/svg-static/fill/cloudy.svg';

/**
 * Mobile-only extreme weather control — top-left under the routing panel.
 * Non-interactive until an extreme warning fires; then accent border + expand.
 */
export default function WeatherControlZone({
  visible = false,
  startCoord = null,
  departAtIso = null,
  santander = false,
  onExtremeDetected,
}) {
  const [expanded, setExpanded] = useState(false);
  const [hadExtreme, setHadExtreme] = useState(false);
  const notifiedKind = useRef(null);

  const enabled = visible && !santander && Boolean(startCoord);
  const { data: weather, ready: weatherReady } = useRouteWeather({
    lat: startCoord?.[0],
    lon: startCoord?.[1],
    atIso: departAtIso || null,
    enabled,
  });

  const extremeWarning = useMemo(() => {
    if (!weatherReady || !weather) return null;
    return resolveExtremeWarning(weather);
  }, [weatherReady, weather]);

  useEffect(() => {
    if (!visible) {
      setExpanded(false);
      setHadExtreme(false);
      notifiedKind.current = null;
      return;
    }
    if (!extremeWarning) {
      setHadExtreme(false);
      setExpanded(false);
      notifiedKind.current = null;
      return;
    }
    setHadExtreme(true);
    if (notifiedKind.current !== extremeWarning.kind) {
      notifiedKind.current = extremeWarning.kind;
      onExtremeDetected?.(extremeWarning);
    }
  }, [visible, extremeWarning, onExtremeDetected]);

  if (!visible) return null;
  // Only show the control once extreme weather is detected (or was for this route).
  if (!extremeWarning && !hadExtreme) return null;

  const iconSrc = extremeWarning?.iconSrc || cloudy;

  return (
    <div
      className={
        `weather-ctl is-accent` +
        (extremeWarning ? ' is-pulse' : '') +
        (expanded ? ' is-expanded' : '')
      }
      data-zone="weather-control"
    >
      <button
        type="button"
        className="weather-ctl__btn"
        aria-label={
          extremeWarning
            ? (expanded ? 'Collapse extreme weather alert' : 'Show extreme weather alert')
            : 'Extreme weather'
        }
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
      >
        <img
          className="weather-ctl__icon"
          src={iconSrc}
          alt=""
          width={28}
          height={28}
          draggable={false}
        />
      </button>
      {expanded && extremeWarning && (
        <div className="weather-ctl__panel">
          <WeatherPanel warning={extremeWarning} />
        </div>
      )}
    </div>
  );
}

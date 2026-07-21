import React, { useMemo } from 'react';
import { TriangleAlert } from 'lucide-react';
import { resolveExtremeWarning } from './resolveExtreme';

const ALERT_LABEL = 'Extreme weather alert';

/**
 * Extreme-only warning — banner, hero icon, condition copy, action line.
 */
export default function WeatherPanel({ warning = null, weather = null }) {
  const view = useMemo(() => {
    if (warning) return warning;
    return resolveExtremeWarning(weather);
  }, [warning, weather]);

  if (!view) return null;

  return (
    <div className="island-weather" aria-label={`${ALERT_LABEL}: ${view.title}`}>
      <div className="island-weather__banner">
        <TriangleAlert size={13} strokeWidth={2.4} aria-hidden />
        <span>{ALERT_LABEL}</span>
      </div>

      <img
        className="island-weather__hero"
        src={view.iconSrc}
        alt=""
        width={140}
        height={140}
        draggable={false}
      />

      <div className="island-weather__copy">
        <p className="island-weather__title">{view.title}</p>
        <p className="island-weather__detail">{view.detail}</p>
        <p className="island-weather__action">{view.action}</p>
      </div>
    </div>
  );
}

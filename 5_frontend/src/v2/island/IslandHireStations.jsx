import React from 'react';
import { Bike, Footprints } from 'lucide-react';

/**
 * Compact hire-station strip for the expanded island (pickup / drop-off).
 * Mirrors map overlay cards: slot breakdown + exact walk (not estimate).
 */
function IslandHireCard({ station, role }) {
  if (!station) return null;
  const walkMin = station.walk_duration_min != null
    ? Math.max(1, Math.round(Number(station.walk_duration_min)))
    : null;
  const name = station.name || 'Station';
  const regular = station.nb_standard ?? null;
  const ebikes = station.nb_ebikes ?? null;
  const empty = station.nb_empty ?? station.nb_docks ?? 0;
  const hasBreakdown = regular != null && ebikes != null;

  return (
    <div className="island-hire-item">
      <div className="island-hire-item__role">{role}</div>
      <div className="island-hire-card">
        <div className="island-hire-card__badge" aria-hidden>
          <Bike size={13} strokeWidth={2.25} />
        </div>
        <div className="island-hire-card__info">
          <div className="island-hire-card__name" title={name}>{name}</div>
          {hasBreakdown ? (
            <div className="island-hire-card__breakdown" aria-label="Bike availability">
              <div className="island-hire-card__bd">
                <strong>{regular}</strong>
                <span>regular</span>
              </div>
              <div className="island-hire-card__bd">
                <strong>{ebikes}</strong>
                <span>electric</span>
              </div>
              <div className="island-hire-card__bd is-muted">
                <strong>{empty}</strong>
                <span>empty</span>
              </div>
            </div>
          ) : (
            <div className="island-hire-card__counts">
              <span>{station.nb_bikes ?? 0}</span>
              <span className="island-hire-card__sep">|</span>
              <span>{empty}</span>
              <span className="island-hire-card__hint">bikes · docks</span>
            </div>
          )}
        </div>
        {walkMin != null && (
          <div className="island-hire-card__walk">
            <Footprints size={12} strokeWidth={2.2} aria-hidden />
            <strong>{walkMin} min</strong>
            <span>walk</span>
          </div>
        )}
      </div>
    </div>
  );
}

export default function IslandHireStations({ pickup, dropoff }) {
  return (
    <div className="island-hire">
      <IslandHireCard station={pickup} role="Pick up" />
      <IslandHireCard station={dropoff} role="Drop off" />
    </div>
  );
}

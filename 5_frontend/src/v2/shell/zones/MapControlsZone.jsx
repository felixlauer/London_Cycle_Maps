import React from 'react';
import { Plus, Minus, LocateFixed, Navigation2 } from 'lucide-react';
import OverlayModeRail from './OverlayModeRail';
import './mapControls.css';

/**
 * Bottom-right stack: overlay pill + Apple-style zoom + locate.
 * Free-floating — no outer chrome box.
 */
export default function MapControlsZone({
  onZoomIn,
  onZoomOut,
  locateActive,
  locatePending,
  onLocateToggle,
  northNeedsReset = false,
  onResetNorth,
  routeRevealed = false,
  overlayMode,
  isDark = false,
  onSelectOverlayMode,
}) {
  return (
    <section
      className="map-ctl"
      aria-label="Map controls"
      data-zone="map-controls"
    >
      <OverlayModeRail
        activeMode={overlayMode}
        isDark={isDark}
        inactive={!routeRevealed}
        onSelectMode={onSelectOverlayMode}
      />

      <div className="map-ctl__zoom" role="group" aria-label="Zoom">
        <button
          type="button"
          className="map-ctl__zoom-btn"
          aria-label="Zoom in"
          onClick={onZoomIn}
        >
          <Plus size={18} strokeWidth={2.25} aria-hidden />
        </button>
        <span className="map-ctl__zoom-rule" aria-hidden />
        <button
          type="button"
          className="map-ctl__zoom-btn"
          aria-label="Zoom out"
          onClick={onZoomOut}
        >
          <Minus size={18} strokeWidth={2.25} aria-hidden />
        </button>
      </div>

      <button
        type="button"
        className={
          `map-ctl__btn` +
          (locateActive ? ' is-active' : '') +
          (locatePending ? ' is-pending' : '')
        }
        aria-label={locateActive ? 'Stop using my location' : 'Use my location'}
        aria-pressed={locateActive}
        disabled={locatePending}
        onClick={onLocateToggle}
      >
        <LocateFixed size={18} strokeWidth={2.25} aria-hidden />
      </button>

      <button
        type="button"
        className={
          `map-ctl__btn map-ctl__btn--north` +
          (northNeedsReset ? ' is-active' : '')
        }
        aria-label="Reset map to north and flat view"
        aria-disabled={!northNeedsReset || undefined}
        onClick={northNeedsReset ? onResetNorth : undefined}
      >
        <span className="map-ctl__north" aria-hidden>
          <Navigation2 className="map-ctl__north-icon" size={16} strokeWidth={2.25} />
          <span className="map-ctl__north-n">N</span>
        </span>
      </button>
    </section>
  );
}

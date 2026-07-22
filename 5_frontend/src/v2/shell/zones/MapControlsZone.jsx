import React from 'react';
import { Plus, Minus, LocateFixed, Navigation2 } from 'lucide-react';
import OverlayModeRail from './OverlayModeRail';
import './mapControls.css';

/**
 * Map controls stack: overlay rail + zoom + locate/north combo.
 * Mobile: top-right under routing (no zoom). Desktop: bottom-right.
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
  compact = false,
}) {
  return (
    <section
      className={`map-ctl${compact ? ' map-ctl--compact' : ''}`}
      aria-label="Map controls"
      data-zone="map-controls"
    >
      <OverlayModeRail
        activeMode={overlayMode}
        isDark={isDark}
        inactive={!routeRevealed}
        onSelectMode={onSelectOverlayMode}
        compact={compact}
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

      <div className="map-ctl__nav" role="group" aria-label="Location and orientation">
        <button
          type="button"
          className={
            `map-ctl__nav-btn` +
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
        <span className="map-ctl__zoom-rule" aria-hidden />
        <button
          type="button"
          className={
            `map-ctl__nav-btn map-ctl__nav-btn--north` +
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
      </div>
    </section>
  );
}

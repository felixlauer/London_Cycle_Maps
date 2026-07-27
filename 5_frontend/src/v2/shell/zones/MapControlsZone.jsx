import React, { useLayoutEffect, useRef, useState } from 'react';
import { Plus, Minus, LocateFixed, Navigation2 } from 'lucide-react';
import OverlayModeRail from './OverlayModeRail';
import './mapControls.css';

const STACK_GAP = 6;
/** Keep a little air between the stacked controls and the island top. */
const ISLAND_CLEARANCE = 12;

/**
 * Map controls stack: overlay rail + zoom + locate/north combo.
 * Mobile: top-right under routing (no zoom). Desktop: bottom-right.
 * When the island is expanded and the usual vertical stack would hit it,
 * pack nav beside the overlay; otherwise keep the stacked layout.
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
  overlayPulse = false,
  islandExpanded = false,
}) {
  const rootRef = useRef(null);
  const [packBeside, setPackBeside] = useState(false);

  useLayoutEffect(() => {
    if (!compact || !islandExpanded) {
      setPackBeside(false);
      return undefined;
    }

    const ctl = rootRef.current;
    if (!ctl) return undefined;

    const measure = () => {
      const shell = ctl.closest('.map-shell');
      const nav = ctl.querySelector('.map-ctl__nav');
      const pill = ctl.querySelector('.overlay-pill');
      const island = shell?.querySelector('[data-zone="dynamic-island"]');
      if (!nav || !pill || !island) {
        setPackBeside(false);
        return;
      }

      // Intrinsic stacked height — independent of current flex direction,
      // so packing cannot flip the decision and oscillate.
      const stackedH = nav.offsetHeight + STACK_GAP + pill.offsetHeight;
      const ctlTop = ctl.getBoundingClientRect().top;
      const islandTop = island.getBoundingClientRect().top;
      const available = islandTop - ctlTop - ISLAND_CLEARANCE;
      setPackBeside(stackedH > available);
    };

    measure();
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    ro?.observe(ctl);
    const island = ctl.closest('.map-shell')?.querySelector('[data-zone="dynamic-island"]');
    if (island) ro?.observe(island);
    window.addEventListener('resize', measure);
    return () => {
      ro?.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [compact, islandExpanded, overlayMode, routeRevealed]);

  return (
    <section
      ref={rootRef}
      className={
        `map-ctl` +
        (compact ? ' map-ctl--compact' : '') +
        (overlayPulse ? ' is-overlay-pulse' : '') +
        (packBeside ? ' is-ctl-packed' : '')
      }
      aria-label="Map controls"
      data-zone="map-controls"
    >
      <OverlayModeRail
        activeMode={overlayMode}
        isDark={isDark}
        inactive={!routeRevealed}
        onSelectMode={onSelectOverlayMode}
        compact={compact}
        pulse={overlayPulse}
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

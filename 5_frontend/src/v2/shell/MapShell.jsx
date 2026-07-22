import React, { useLayoutEffect, useState } from 'react';
import PlanningMap from '../map/PlanningMap';
import RoutingCoreZone from './zones/RoutingCoreZone';
import ProfileZone from './zones/ProfileZone';
import AlertPillZone from './zones/AlertPillZone';
import DynamicIslandZone from './zones/DynamicIslandZone';
import MapControlsZone from './zones/MapControlsZone';
import WeatherControlZone from './zones/WeatherControlZone';
import ProfileSidebar from './sidebar/ProfileSidebar';
import { useSidebar } from './SidebarContext';
import { useIsMobile } from '../hooks/useMediaQuery';
import './shell.css';

/**
 * Full-viewport shell: map + floating zones + profile drawer.
 */
export default function MapShell({
  themeMode = 'light',
  alert,
  onAlertAction,
  routingProps,
  mapProps,
  mapControlsProps,
  islandProps,
  weatherControlProps,
  sidebarProfiles,
  activeProfileId,
  onDeleteProfile,
  onProfileCreated,
  onProfileUpdated,
}) {
  const { shellRef, open, view } = useSidebar();
  const isMobile = useIsMobile();
  const islandExpanded = Boolean(islandProps?.expanded && islandProps?.visible);
  const islandMulti = Boolean(islandProps?.visible && (islandProps?.legCount || 0) > 1);
  const [routingBottom, setRoutingBottom] = useState(0);
  const [ctlColliding, setCtlColliding] = useState(false);

  useLayoutEffect(() => {
    const shell = shellRef?.current;
    if (!shell) return undefined;

    const measure = () => {
      const panel = shell.querySelector('[data-zone="routing-core"]');
      if (panel) {
        setRoutingBottom(Math.round(panel.getBoundingClientRect().bottom));
      }

      if (!isMobile || !islandExpanded) {
        setCtlColliding(false);
        return;
      }
      const overlay = shell.querySelector('[data-zone="map-controls"] .overlay-pill');
      const island = shell.querySelector('[data-zone="dynamic-island"]');
      if (!overlay || !island) {
        setCtlColliding(false);
        return;
      }
      const a = overlay.getBoundingClientRect();
      const b = island.getBoundingClientRect();
      const overlap = !(a.bottom < b.top || a.top > b.bottom || a.right < b.left || a.left > b.right);
      setCtlColliding(overlap);
    };

    measure();
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    const panel = shell.querySelector('[data-zone="routing-core"]');
    const island = shell.querySelector('[data-zone="dynamic-island"]');
    const overlay = shell.querySelector('[data-zone="map-controls"] .overlay-pill');
    if (panel) ro?.observe(panel);
    if (island) ro?.observe(island);
    if (overlay) ro?.observe(overlay);
    window.addEventListener('resize', measure);
    return () => {
      ro?.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [shellRef, routingProps, open, view, isMobile, islandExpanded, islandProps]);

  const underPanelTop = routingBottom > 0
    ? `${routingBottom + 10}px`
    : undefined;

  return (
    <div
      ref={shellRef}
      className={[
        'map-shell',
        open ? 'is-sidebar-open' : '',
        view === 'wizard' ? 'is-wizard-open' : '',
        islandExpanded ? 'is-island-expanded' : '',
        islandMulti ? 'is-island-multi' : '',
        ctlColliding ? 'is-ctl-colliding' : '',
      ].filter(Boolean).join(' ')}
      data-theme={themeMode}
      style={underPanelTop ? {
        '--mc-mobile-top': underPanelTop,
        '--wc-mobile-top': underPanelTop,
        '--alert-mobile-top': underPanelTop,
      } : undefined}
    >
      <div className="map-shell__map">
        <PlanningMap {...mapProps} themeMode={themeMode} />
      </div>

      <div className="map-shell__chrome">
        <RoutingCoreZone {...routingProps} />
        <AlertPillZone alert={alert} onAction={onAlertAction} />
        <ProfileZone />
        {isMobile && (
          <WeatherControlZone {...(weatherControlProps || {})} />
        )}
        <DynamicIslandZone {...islandProps} />
        <MapControlsZone {...mapControlsProps} compact={isMobile} />
        <ProfileSidebar
          profiles={sidebarProfiles}
          activeProfileId={activeProfileId}
          onDeleteProfile={onDeleteProfile}
          onProfileCreated={onProfileCreated}
          onProfileUpdated={onProfileUpdated}
        />
      </div>
    </div>
  );
}

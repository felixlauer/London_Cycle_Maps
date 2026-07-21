import React from 'react';
import PlanningMap from '../map/PlanningMap';
import RoutingCoreZone from './zones/RoutingCoreZone';
import ProfileZone from './zones/ProfileZone';
import AlertPillZone from './zones/AlertPillZone';
import DynamicIslandZone from './zones/DynamicIslandZone';
import MapControlsZone from './zones/MapControlsZone';
import ProfileSidebar from './sidebar/ProfileSidebar';
import { useSidebar } from './SidebarContext';
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
  sidebarProfiles,
  activeProfileId,
  onDeleteProfile,
  onProfileCreated,
  onProfileUpdated,
}) {
  const { shellRef, open, view } = useSidebar();
  const islandExpanded = Boolean(islandProps?.expanded && islandProps?.visible);
  const islandMulti = Boolean(islandProps?.visible && (islandProps?.legCount || 0) > 1);

  return (
    <div
      ref={shellRef}
      className={[
        'map-shell',
        open ? 'is-sidebar-open' : '',
        view === 'wizard' ? 'is-wizard-open' : '',
        islandExpanded ? 'is-island-expanded' : '',
        islandMulti ? 'is-island-multi' : '',
      ].filter(Boolean).join(' ')}
      data-theme={themeMode}
    >
      <div className="map-shell__map">
        <PlanningMap {...mapProps} themeMode={themeMode} />
      </div>

      <div className="map-shell__chrome">
        <RoutingCoreZone {...routingProps} />
        <AlertPillZone alert={alert} onAction={onAlertAction} />
        <ProfileZone />
        <DynamicIslandZone {...islandProps} />
        <MapControlsZone {...mapControlsProps} />
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

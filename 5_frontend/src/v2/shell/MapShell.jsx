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

const ALERT_SIDE_GAP = 8;
const ALERT_ZONE_SELECTORS = [
  '[data-zone="routing-core"]',
  '[data-zone="weather-control"]',
  '[data-zone="map-controls"]',
  '[data-zone="profile"]',
];

function readInsetPx(shell) {
  try {
    const raw = getComputedStyle(shell).getPropertyValue('--shell-inset').trim();
    const n = parseFloat(raw);
    return Number.isFinite(n) ? n : 12;
  } catch {
    return 12;
  }
}

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
  onSelectProfile,
  onDeleteProfile,
  onProfileCreated,
  onProfileUpdated,
  onMapReady,
}) {
  const { shellRef, open, view } = useSidebar();
  const isMobile = useIsMobile();
  const islandExpanded = Boolean(islandProps?.expanded && islandProps?.visible);
  const islandMulti = Boolean(islandProps?.visible && (islandProps?.legCount || 0) > 1);
  const [routingBottom, setRoutingBottom] = useState(0);
  const [alertPad, setAlertPad] = useState({ left: 12, right: 12 });

  useLayoutEffect(() => {
    const shell = shellRef?.current;
    if (!shell) return undefined;

    const observed = new Set();
    let ro = null;

    const observeZones = () => {
      for (const sel of ALERT_ZONE_SELECTORS) {
        const el = shell.querySelector(sel);
        if (el && !observed.has(el)) {
          observed.add(el);
          ro?.observe(el);
        }
      }
    };

    const measure = () => {
      observeZones();
      const shellRect = shell.getBoundingClientRect();
      const inset = readInsetPx(shell);
      let leftPad = inset;
      let rightPad = inset;

      const panel = shell.querySelector('[data-zone="routing-core"]');
      if (panel) {
        const panelRect = panel.getBoundingClientRect();
        setRoutingBottom(Math.round(panelRect.bottom));
        // Desktop/tablet: routing sits left of the alert band.
        if (!isMobile && panelRect.width > 2) {
          leftPad = Math.max(
            leftPad,
            Math.round(panelRect.right - shellRect.left + ALERT_SIDE_GAP),
          );
        }
      }

      const weather = shell.querySelector('[data-zone="weather-control"]');
      if (weather) {
        const r = weather.getBoundingClientRect();
        if (r.width > 2 && r.height > 2) {
          leftPad = Math.max(leftPad, Math.round(r.right - shellRect.left + ALERT_SIDE_GAP));
        }
      }

      if (isMobile) {
        const mapCtl = shell.querySelector('[data-zone="map-controls"]');
        if (mapCtl) {
          const r = mapCtl.getBoundingClientRect();
          if (r.width > 2 && r.height > 2) {
            rightPad = Math.max(rightPad, Math.round(shellRect.right - r.left + ALERT_SIDE_GAP));
          }
        }
      } else {
        const profile = shell.querySelector('[data-zone="profile"]');
        if (profile) {
          const r = profile.getBoundingClientRect();
          if (r.width > 2 && r.height > 2) {
            rightPad = Math.max(rightPad, Math.round(shellRect.right - r.left + ALERT_SIDE_GAP));
          }
        }
      }

      setAlertPad((prev) => (
        prev.left === leftPad && prev.right === rightPad
          ? prev
          : { left: leftPad, right: rightPad }
      ));
    };

    ro = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(measure)
      : null;

    measure();
    const chrome = shell.querySelector('.map-shell__chrome') || shell;
    const mo = typeof MutationObserver !== 'undefined'
      ? new MutationObserver(measure)
      : null;
    mo?.observe(chrome, { childList: true, subtree: true });
    window.addEventListener('resize', measure);
    return () => {
      ro?.disconnect();
      mo?.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [
    shellRef, routingProps, open, view, isMobile, islandExpanded, islandProps,
    weatherControlProps, alert,
  ]);

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
      ].filter(Boolean).join(' ')}
      data-theme={themeMode}
      style={{
        ...(underPanelTop ? {
          '--mc-mobile-top': underPanelTop,
          '--wc-mobile-top': underPanelTop,
          '--alert-mobile-top': underPanelTop,
        } : {}),
        '--alert-pad-left': `${alertPad.left}px`,
        '--alert-pad-right': `${alertPad.right}px`,
      }}
    >
      <div className="map-shell__map">
        <PlanningMap {...mapProps} themeMode={themeMode} onMapReady={onMapReady} />
      </div>

      <div className="map-shell__chrome">
        <RoutingCoreZone {...routingProps} />
        <AlertPillZone alert={alert} onAction={onAlertAction} />
        <ProfileZone />
        {isMobile && (
          <WeatherControlZone {...(weatherControlProps || {})} />
        )}
        <DynamicIslandZone {...islandProps} />
        <MapControlsZone
          {...mapControlsProps}
          compact={isMobile}
          islandExpanded={islandExpanded}
        />
        <ProfileSidebar
          profiles={sidebarProfiles}
          activeProfileId={activeProfileId}
          onSelectProfile={onSelectProfile}
          onDeleteProfile={onDeleteProfile}
          onProfileCreated={onProfileCreated}
          onProfileUpdated={onProfileUpdated}
        />
      </div>
    </div>
  );
}

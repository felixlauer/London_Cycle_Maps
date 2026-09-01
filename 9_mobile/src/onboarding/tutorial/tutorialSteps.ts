/**
 * Spotlight tutorial steps — mobile web parity (≤767px filter).
 * Targets use TutorialAnchor ids instead of DOM selectors.
 */

import type { TutorialCutoutOpts } from './tutorialRegistry';

export type TutorialTargetSpec = {
  id: string;
  opts?: TutorialCutoutOpts;
};

export type TutorialSignals = {
  routeRevealed?: boolean;
  overlayMode?: string | null;
  islandExpanded?: boolean;
  islandPage?: number;
  start?: [number, number] | null;
  end?: [number, number] | null;
  activeProfileId?: string | null;
  sessionBikeType?: string | null;
  sidebarOpen?: boolean;
  safestPath?: number[][] | null;
  /** Project [lng, lat] → window point { x, y }. */
  projectToWindow?: (lngLat: [number, number]) => Promise<{ x: number; y: number } | null>;
  mapReady?: boolean;
  profileMenuOpened?: boolean;
  bikeMenuOpened?: boolean;
  bikeChanged?: boolean;
  profileChanged?: boolean;
  overlayChangedWhileExpanded?: boolean;
  rightSwipesSinceBars?: number;
  markBikeMenuOpened?: () => void;
  markProfileMenuOpened?: () => void;
};

export type TutorialStep = {
  id: string;
  title: string;
  body: string;
  placement: string;
  targets: TutorialTargetSpec[];
  /** Tip/emphasis anchor id (no extra ring). */
  primaryTargetId?: string;
  ringColor?: string;
  mapInteract?: boolean;
  routeBounds?: boolean;
  routeBoundsAlongside?: boolean;
  advance: {
    type: 'button' | 'auto';
    require?: (s: TutorialSignals) => boolean;
    when?: (s: TutorialSignals) => boolean;
    finish?: boolean;
    finishLabel?: string;
  };
};

export function buildMobileTutorialSteps(): TutorialStep[] {
  const islandOpts: TutorialCutoutOpts = { ring: true, radius: 999 };
  const islandExpandedOpts: TutorialCutoutOpts = { ring: true, radius: 20 };

  return [
    {
      id: 'profile-selector',
      title: 'Your riding profile',
      body: "This is your riding profile. We've set the one you just created as your default. Switch between saved profiles here whenever you like.",
      placement: 'bottom',
      targets: [
        { id: 'tut-profile-pill', opts: { ring: true, capsule: true } },
        { id: 'tut-profile-menu', opts: { ring: true, radius: 11 } },
      ],
      advance: {
        type: 'button',
        require: (signals) => Boolean(signals.profileMenuOpened),
      },
    },
    {
      id: 'bike-type',
      title: 'Bike type',
      body: "Pick the bike you're on - it changes how routes are scored. Heads up: turning on Santander mode auto-switches this to a matching hire bike.",
      placement: 'bottom',
      targets: [
        { id: 'tut-bike-pill', opts: { ring: true, capsule: true } },
        { id: 'tut-bike-menu', opts: { ring: true, radius: 11 } },
      ],
      advance: {
        type: 'button',
        require: (signals) => Boolean(signals.bikeMenuOpened || signals.bikeChanged),
      },
    },
    {
      id: 'start-end',
      title: 'Start and destination',
      body: "Set where you're starting and where you're headed. Search an address or drop a pin on the map - both work for either field.",
      placement: 'screen-bottom',
      mapInteract: true,
      targets: [
        { id: 'tut-waypoint-card', opts: { ring: true, radius: 14 } },
        { id: 'tut-suggest-dropdown', opts: { ring: true, radius: 8 } },
      ],
      advance: {
        type: 'auto',
        when: (s) => Boolean(s.start && s.end),
      },
    },
    {
      id: 'get-route',
      title: 'Get your route',
      body: 'Now press Get Route. Longer routes take a little longer to compute, up to about 10 seconds, so give it a moment.',
      placement: 'bottom',
      ringColor: '#ffffff',
      targets: [
        { id: 'tut-get-route', opts: { ring: true, ringColor: '#ffffff', radius: 12 } },
      ],
      advance: {
        type: 'auto',
        when: (s) => Boolean(s.routeRevealed),
      },
    },
    {
      id: 'route-on-map',
      title: 'Your tuned route',
      body: "Here's your tuned route. The coloured line is your recommended path, wrapped in a white casing so it stays readable over the map.",
      placement: 'avoid-route',
      targets: [],
      routeBounds: true,
      advance: { type: 'button' },
    },
    {
      id: 'island-collapsed',
      title: 'Trip at a glance',
      body: "Your trip at a glance: time, distance and a quick preview of the ride's shape.",
      placement: 'top',
      targets: [
        { id: 'tut-island', opts: islandOpts },
      ],
      routeBoundsAlongside: true,
      advance: { type: 'button' },
    },
    {
      id: 'overlay-attractions',
      title: 'Map overlays',
      body: 'Switch the map overlay to Attractions. Watch the map, this selector and the panel below update together.',
      placement: 'screen-bottom',
      targets: [
        { id: 'tut-overlay-rail', opts: { ring: true, capsule: true } },
        { id: 'tut-island', opts: islandOpts },
      ],
      primaryTargetId: 'tut-overlay-attractions',
      routeBoundsAlongside: true,
      advance: {
        type: 'auto',
        when: (s) => s.overlayMode === 'green',
      },
    },
    {
      id: 'island-expand-mobile',
      title: 'Open the analysis panel',
      body: 'Open the panel to see more detail about your ride.',
      placement: 'top',
      targets: [
        { id: 'tut-island', opts: islandOpts },
        { id: 'tut-overlay-rail', opts: { ring: true, capsule: true } },
      ],
      primaryTargetId: 'tut-island-expand',
      advance: {
        type: 'button',
        require: (s) => Boolean(s.islandExpanded),
      },
    },
    {
      id: 'island-swipe-left',
      title: 'Elevation chart',
      body: 'This is your elevation chart. Swipe left to see your ride analysis.',
      placement: 'top',
      targets: [
        { id: 'tut-island', opts: islandExpandedOpts },
        { id: 'tut-overlay-rail', opts: { ring: true, capsule: true } },
      ],
      routeBoundsAlongside: true,
      advance: {
        type: 'auto',
        when: (s) => s.islandPage === 2,
      },
    },
    {
      id: 'island-swipe-right',
      title: 'Swipe through the pages',
      body: 'Nice. Now swipe right twice to move back through the pages.',
      placement: 'top',
      targets: [
        { id: 'tut-island', opts: islandExpandedOpts },
        { id: 'tut-overlay-rail', opts: { ring: true, capsule: true } },
      ],
      routeBoundsAlongside: true,
      advance: {
        type: 'auto',
        when: (s) => s.islandPage === 0 && (s.rightSwipesSinceBars || 0) >= 2,
      },
    },
    {
      id: 'open-sidebar',
      title: 'Your space',
      body: 'Open your profile to reach your space.',
      placement: 'bottom',
      targets: [
        { id: 'tut-mobile-avatar', opts: { ring: true, capsule: true, radius: 999 } },
      ],
      advance: {
        type: 'auto',
        when: (s) => Boolean(s.sidebarOpen),
      },
    },
    {
      id: 'sidebar-overview',
      title: 'Profiles and settings',
      body: 'This is where you manage profiles and adjust account and system settings.',
      placement: 'left',
      targets: [
        { id: 'tut-sidebar-panel', opts: { ring: true, radius: 0 } },
      ],
      advance: { type: 'button' },
    },
    {
      id: 'sidebar-help',
      title: 'Help when you need it',
      body: 'Replay this tour anytime from Revisit tutorial, or tap Report a bug if something feels off — bug reports are greatly appreciated and help us improve TUNE. While navigating, the orange flag lets you report a problem with the road itself in one tap.',
      placement: 'left',
      targets: [
        { id: 'tut-sidebar-help', opts: { ring: true, radius: 8 } },
      ],
      advance: { type: 'button', finish: true, finishLabel: 'Finish tutorial' },
    },
  ];
}

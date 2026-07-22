/**
 * Spotlight tutorial step registry.
 * Each step: id, title, body, targets(), advance, optional platform / onEnter.
 *
 * targets() may return Elements or descriptor objects:
 *   { el, ring?: boolean, pad?: number }
 */

function q(sel, root = document) {
  try {
    return root.querySelector(sel);
  } catch {
    return null;
  }
}

function el(sel) {
  const node = q(sel);
  return node ? [node] : [];
}

function els(...sels) {
  return sels.map((s) => q(s)).filter(Boolean);
}

function desc(elNode, opts = {}) {
  if (!elNode) return null;
  return { el: elNode, ...opts };
}

export function buildTutorialSteps({ isMobile }) {
  const getRouteSel = isMobile
    ? '[data-zone="routing-core"] .rc-route-pill'
    : '[data-zone="routing-core"] .rc-get-route';
  const spaceSel = isMobile
    ? '[data-zone="routing-core"] .rc-mobile-avatar'
    : '[data-zone="profile"] .profile-pill__chrome';

  const islandEl = () => q('[data-zone="dynamic-island"]');
  const overlayEl = () => q('[data-zone="map-controls"] .overlay-pill');

  const steps = [
    {
      id: 'profile-selector',
      platform: 'all',
      title: 'Your riding profile',
      body: "This is your riding profile. We've set the one you just created as your default. Switch between saved profiles here whenever you like.",
      placement: 'bottom',
      targets: () => {
        const pill = q('[data-zone="routing-core"] .rc-quick__slot:first-child .rc-pill');
        const menu = q('[data-zone="routing-core"] .rc-quick__slot:first-child .rc-menu');
        const out = [];
        // Ring the visible pill (slot itself has radius 0).
        if (pill) out.push(desc(pill, { ring: true, capsule: true }));
        if (menu) out.push(desc(menu, { ring: true }));
        return out;
      },
      advance: {
        type: 'button',
        // Opening the dropdown is enough — no need to change profile.
        require: (signals) => Boolean(signals.profileMenuOpened),
      },
      onEnter: (signals) => {
        const pill = q('[data-zone="routing-core"] .rc-quick__slot:first-child .rc-pill');
        if (!pill || signals._profileListenAttached) return;
        signals._profileListenAttached = true;
        const onClick = () => {
          signals.markProfileMenuOpened?.();
        };
        pill.addEventListener('click', onClick, { once: false });
        signals._profileCleanup = () => pill.removeEventListener('click', onClick);
      },
    },
    {
      id: 'bike-type',
      platform: 'all',
      title: 'Bike type',
      body: "Pick the bike you're on - it changes how routes are scored. Heads up: turning on Santander mode auto-switches this to a matching hire bike.",
      placement: 'bottom',
      targets: () => {
        const pill = q('[data-zone="routing-core"] .rc-quick__slot:nth-child(2) .rc-pill');
        const menu = q('[data-zone="routing-core"] .rc-quick__slot:nth-child(2) .rc-menu');
        const out = [];
        if (pill) out.push(desc(pill, { ring: true, capsule: true }));
        // Separate hole for the open menu — never pad the pill into Get Route.
        if (menu) out.push(desc(menu, { ring: true }));
        return out;
      },
      advance: {
        type: 'button',
        require: (signals) => Boolean(signals.bikeMenuOpened || signals.bikeChanged),
      },
      onEnter: (signals) => {
        const slot = q('[data-zone="routing-core"] .rc-quick__slot:nth-child(2) .rc-pill');
        if (!slot || signals._bikeListenAttached) return;
        signals._bikeListenAttached = true;
        const onClick = () => {
          signals.markBikeMenuOpened?.();
        };
        slot.addEventListener('click', onClick, { once: false });
        signals._bikeCleanup = () => slot.removeEventListener('click', onClick);
      },
    },
    {
      id: 'start-end',
      platform: 'all',
      title: 'Start and destination',
      body: "Set where you're starting and where you're headed. Search an address or drop a pin on the map - both work for either field.",
      placement: 'bottom',
      /** Dim is visual-only so map clicks still register (map is full-bleed under chrome). */
      mapInteract: true,
      targets: () => {
        const out = [];
        const card = q('[data-zone="routing-core"] .rc-wpcard');
        if (card) out.push(desc(card, { ring: true }));
        else {
          els(
            '[data-zone="routing-core"] .rc-wp-row:has(.rc-slot--start)',
            '[data-zone="routing-core"] .rc-wp-row:has(.rc-slot--end)',
          ).forEach((n) => out.push(desc(n, { ring: true })));
        }
        document.querySelectorAll('[data-zone="routing-core"] .rc-suggest, [data-zone="routing-core"] .rc-autocomplete').forEach((n) => {
          out.push(desc(n, { ring: true }));
        });
        return out;
      },
      advance: {
        type: 'auto',
        when: (s) => Boolean(s.start && s.end),
      },
    },
    {
      id: 'get-route',
      platform: 'all',
      title: 'Get your route',
      body: 'Now press Get Route. Longer routes take a little longer to compute, up to about 10 seconds, so give it a moment.',
      placement: 'bottom',
      ringColor: '#ffffff',
      targets: () => {
        const btn = q(getRouteSel);
        return btn ? [desc(btn, { ring: true, ringColor: '#ffffff' })] : [];
      },
      advance: {
        type: 'auto',
        when: (s) => Boolean(s.routeRevealed),
      },
    },
    {
      id: 'route-on-map',
      platform: 'all',
      title: 'Your tuned route',
      body: "Here's your tuned route. The coloured line is your recommended path, wrapped in a white casing so it stays readable over the map.",
      placement: 'avoid-route',
      /** Screen bbox of path + markers, computed in TutorialController. */
      targets: () => [],
      routeBounds: true,
      advance: { type: 'button' },
    },
    {
      id: 'island-collapsed',
      platform: 'all',
      title: 'Trip at a glance',
      body: "Your trip at a glance: time, distance and a quick preview of the ride's shape.",
      placement: 'top',
      targets: () => {
        const out = [];
        const island = islandEl();
        if (island) out.push(desc(island, { ring: true }));
        // Route bbox hole added in controller when routeBoundsAlongside is set
        return out;
      },
      routeBoundsAlongside: true,
      advance: { type: 'button' },
    },
    {
      id: 'overlay-attractions',
      platform: 'all',
      title: 'Map overlays',
      body: 'Switch the map overlay to Attractions. Watch the map, this selector and the panel below update together.',
      placement: 'left',
      targets: () => {
        const out = [];
        const overlay = overlayEl();
        const island = islandEl();
        if (overlay) out.push(desc(overlay, { ring: true, capsule: true }));
        if (island) out.push(desc(island, { ring: true }));
        return out;
      },
      routeBoundsAlongside: true,
      primaryTarget: () => q('[data-tutorial="attractions"]')
        || q('[data-zone="map-controls"] .overlay-pill__btn[aria-label="Attractions"]'),
      advance: {
        type: 'auto',
        when: (s) => s.overlayMode === 'green',
      },
    },
    {
      id: 'island-expand-desktop',
      platform: 'desktop',
      title: 'Open the analysis panel',
      body: "Open the panel for the full picture: elevation, ride analysis and more. Try the overlay selector again to change what's shown here.",
      placement: 'top',
      targets: () => {
        const out = [];
        const overlay = overlayEl();
        const island = islandEl();
        if (island) out.push(desc(island, { ring: true }));
        if (overlay) out.push(desc(overlay, { ring: true, capsule: true }));
        return out;
      },
      primaryTarget: () => q('[data-tutorial="island-expand"]')
        || q('[data-zone="dynamic-island"] .island-collapsed__chevron-btn'),
      advance: {
        type: 'button',
        require: (s) => Boolean(s.islandExpanded),
      },
    },
    {
      id: 'island-expand-mobile',
      platform: 'mobile',
      title: 'Open the analysis panel',
      body: 'Open the panel to see more detail about your ride.',
      placement: 'top',
      targets: () => {
        const out = [];
        const island = islandEl();
        const overlay = overlayEl();
        if (island) out.push(desc(island, { ring: true }));
        if (overlay) out.push(desc(overlay, { ring: true, capsule: true }));
        return out;
      },
      primaryTarget: () => q('[data-tutorial="island-expand"]')
        || q('[data-zone="dynamic-island"] .island-collapsed__chevron-btn'),
      advance: {
        type: 'button',
        require: (s) => Boolean(s.islandExpanded),
      },
    },
    {
      id: 'island-swipe-left',
      platform: 'mobile',
      title: 'Elevation chart',
      body: 'This is your elevation chart. Swipe left to see your ride analysis.',
      placement: 'top',
      targets: () => {
        const out = [];
        const island = islandEl();
        const overlay = overlayEl();
        if (island) out.push(desc(island, { ring: true }));
        if (overlay) out.push(desc(overlay, { ring: true, capsule: true }));
        return out;
      },
      routeBoundsAlongside: true,
      advance: {
        type: 'auto',
        when: (s) => s.islandPage === 2,
      },
    },
    {
      id: 'island-swipe-right',
      platform: 'mobile',
      title: 'Swipe through the pages',
      body: 'Nice. Now swipe right twice to move back through the pages.',
      placement: 'top',
      targets: () => {
        const out = [];
        const island = islandEl();
        const overlay = overlayEl();
        if (island) out.push(desc(island, { ring: true }));
        if (overlay) out.push(desc(overlay, { ring: true, capsule: true }));
        return out;
      },
      routeBoundsAlongside: true,
      advance: {
        type: 'auto',
        when: (s) => s.islandPage === 0 && s.rightSwipesSinceBars >= 2,
      },
    },
    {
      id: 'open-sidebar',
      platform: 'all',
      title: 'Your space',
      body: 'Open your profile to reach your space.',
      placement: isMobile ? 'bottom' : 'left',
      targets: () => el(spaceSel),
      advance: {
        type: 'auto',
        when: (s) => Boolean(s.sidebarOpen),
      },
    },
    {
      id: 'sidebar-overview',
      platform: 'all',
      title: 'Profiles and settings',
      body: 'This is where you manage profiles, adjust account and system settings, and you can always replay this tour from the bottom of the panel.',
      placement: 'left',
      targets: () => el('.profile-sidebar.is-open'),
      advance: { type: 'button', finish: true },
    },
  ];

  return steps.filter((step) => {
    if (!step.platform || step.platform === 'all') return true;
    if (step.platform === 'mobile') return isMobile;
    if (step.platform === 'desktop') return !isMobile;
    return true;
  });
}

export { q, el, els, desc };

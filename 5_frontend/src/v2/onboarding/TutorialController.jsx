import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { X } from 'lucide-react';
import { useIsMobile } from '../hooks/useMediaQuery';
import { useOnboarding } from './OnboardingContext';
import { buildTutorialSteps } from './tutorialSteps';
import './tutorial.css';

/** Flush to element edges — no extra margin (avoids double-ring look). */
const PAD = 0;
const ROUTE_PAD = 14;
const MARKER_PAD = 22;

/**
 * @typedef {{
 *   top: number, left: number, width: number, height: number,
 *   rx: number, ring: boolean,
 * }} Cutout
 */

function parseRadius(el) {
  if (!el || typeof window === 'undefined') return 12;
  try {
    const raw = window.getComputedStyle(el).borderRadius || '12px';
    const first = raw.split(' ')[0];
    const n = parseFloat(first);
    if (!Number.isFinite(n)) return 12;
    if (first.includes('%') || n >= 999) return 999;
    return n;
  } catch {
    return 12;
  }
}

function normalizeTarget(entry) {
  if (!entry) return null;
  if (entry.el) return entry;
  if (entry.nodeType === 1) return { el: entry, ring: true };
  return null;
}

function measureFromElement(el, {
  ring = true,
  pad = PAD,
  capsule = false,
  ringColor = null,
} = {}) {
  const r = el.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) return null;
  const radius = parseRadius(el);
  let rx;
  if (capsule || radius >= 999) {
    rx = Math.min(r.width, r.height) / 2 + pad;
  } else {
    // Prefer computed radius, but never look sharper than a soft 14px control.
    rx = Math.max(radius, Math.min(14, Math.min(r.width, r.height) / 2));
    rx = Math.min(rx + pad, (r.width + pad * 2) / 2, (r.height + pad * 2) / 2);
  }
  return {
    top: Math.max(0, r.top - pad),
    left: Math.max(0, r.left - pad),
    width: r.width + pad * 2,
    height: r.height + pad * 2,
    rx,
    ring: Boolean(ring),
    ringColor: ringColor || null,
  };
}

function pointInCutout(x, y, c) {
  return x >= c.left && x <= c.left + c.width && y >= c.top && y <= c.top + c.height;
}

function rectsOverlap(a, b, margin = 8) {
  return !(
    a.left + a.width + margin < b.left
    || b.left + b.width + margin < a.left
    || a.top + a.height + margin < b.top
    || b.top + b.height + margin < a.top
  );
}

/** Shrink route bbox so it doesn't collide with island / overlay rings. */
function clipRouteAwayFromChrome(route, blockers, gap = 12) {
  if (!route) return null;
  const r = { ...route };
  (blockers || []).forEach((b) => {
    if (!b || !rectsOverlap(r, b, 0)) return;
    const routeCy = r.top + r.height / 2;
    const blockCy = b.top + b.height / 2;
    const routeCx = r.left + r.width / 2;
    const blockCx = b.left + b.width / 2;

    if (blockCy >= routeCy) {
      // Blocker mostly below (island) — raise route bottom
      r.height = Math.max(0, Math.min(r.height, (b.top - gap) - r.top));
    } else if (blockCx >= routeCx) {
      // Blocker to the right (overlay rail)
      r.width = Math.max(0, Math.min(r.width, (b.left - gap) - r.left));
    } else {
      const newLeft = Math.max(r.left, b.left + b.width + gap);
      r.width = Math.max(0, r.left + r.width - newLeft);
      r.left = newLeft;
    }
  });
  if (r.width < 48 || r.height < 48) return null;
  return r;
}

/** Leaflet-style [[lat,lon],...] → screen cutout via mapApi.project. */
function measureRouteCutout(path, start, end, mapApi) {
  if (!mapApi?.project || !mapApi?.getContainer) return null;
  const container = mapApi.getContainer();
  if (!container) return null;
  const crect = container.getBoundingClientRect();

  const pts = [];
  const pushLatLon = (lat, lon) => {
    if (lat == null || lon == null) return;
    const p = mapApi.project([lon, lat]);
    if (!p) return;
    pts.push({
      x: crect.left + p.x,
      y: crect.top + p.y,
    });
  };

  (path || []).forEach((pair) => {
    if (!Array.isArray(pair) || pair.length < 2) return;
    pushLatLon(pair[0], pair[1]);
  });
  if (Array.isArray(start) && start.length >= 2) pushLatLon(start[0], start[1]);
  if (Array.isArray(end) && end.length >= 2) pushLatLon(end[0], end[1]);

  if (pts.length < 2) return null;

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  pts.forEach((p) => {
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x);
    maxY = Math.max(maxY, p.y);
  });

  const pad = ROUTE_PAD + MARKER_PAD;
  const left = Math.max(0, minX - pad);
  const top = Math.max(0, minY - pad);
  const right = Math.min(window.innerWidth, maxX + pad);
  const bottom = Math.min(window.innerHeight, maxY + pad);

  return {
    top,
    left,
    width: Math.max(0, right - left),
    height: Math.max(0, bottom - top),
    rx: 16,
    ring: true,
  };
}

function roundedRectPath(c) {
  const { left: x, top: y, width: w, height: h } = c;
  let rx = Math.min(c.rx || 12, w / 2, h / 2);
  if (rx < 0) rx = 0;
  const ry = rx;
  return [
    `M${x + rx},${y}`,
    `H${x + w - rx}`,
    `Q${x + w},${y} ${x + w},${y + ry}`,
    `V${y + h - ry}`,
    `Q${x + w},${y + h} ${x + w - rx},${y + h}`,
    `H${x + rx}`,
    `Q${x},${y + h} ${x},${y + h - ry}`,
    `V${y + ry}`,
    `Q${x},${y} ${x + rx},${y}`,
    'Z',
  ].join(' ');
}

function buildMaskPath(vw, vh, cutouts) {
  const outer = `M0,0H${vw}V${vh}H0Z`;
  const holes = cutouts.map(roundedRectPath).join('');
  return outer + holes;
}

function placeTooltip(anchor, placement, tipW, tipH, avoidRects = []) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const gap = 18;
  let top;
  let left;

  if (placement === 'avoid-route' && avoidRects[0]) {
    const routeCutout = avoidRects[0];
    const below = routeCutout.top + routeCutout.height + gap;
    if (below + tipH < vh - 56) {
      top = below;
      left = routeCutout.left + routeCutout.width / 2 - tipW / 2;
    } else if (routeCutout.top - tipH - gap > 16) {
      top = routeCutout.top - tipH - gap;
      left = routeCutout.left + routeCutout.width / 2 - tipW / 2;
    } else {
      top = Math.max(16, vh - tipH - 72);
      left = Math.max(16, (vw - tipW) / 2);
    }
  } else if (placement === 'center' || !anchor) {
    top = Math.max(16, (vh - tipH) / 2);
    left = Math.max(16, (vw - tipW) / 2);
  } else if (placement === 'bottom') {
    top = anchor.bottom + gap;
    left = anchor.left + anchor.width / 2 - tipW / 2;
  } else if (placement === 'top') {
    top = anchor.top - tipH - gap;
    left = anchor.left + anchor.width / 2 - tipW / 2;
  } else if (placement === 'left') {
    top = anchor.top + anchor.height / 2 - tipH / 2;
    left = anchor.left - tipW - gap;
  } else {
    top = anchor.top + anchor.height / 2 - tipH / 2;
    left = anchor.right + gap;
  }

  if (left < 16) left = 16;
  if (left + tipW > vw - 16) left = Math.max(16, vw - tipW - 16);

  const tipRect = () => ({ top, left, width: tipW, height: tipH });

  // If tip overlaps any spotlight, push below the lowest overlapping cutout.
  const pushClear = () => {
    let guard = 0;
    while (guard < 6 && avoidRects.some((c) => rectsOverlap(tipRect(), c))) {
      const hit = avoidRects.find((c) => rectsOverlap(tipRect(), c));
      if (!hit) break;
      top = hit.top + hit.height + gap;
      if (top + tipH > vh - 56) {
        top = Math.max(16, hit.top - tipH - gap);
      }
      if (top < 16) top = 16;
      if (top + tipH > vh - 16) {
        top = Math.max(16, vh - tipH - 72);
        left = Math.max(16, (vw - tipW) / 2);
        break;
      }
      guard += 1;
    }
  };

  // Prefer not flipping above the anchor when placement is bottom (avoids covering the control).
  if (placement === 'bottom' && anchor) {
    if (top + tipH > vh - 16) {
      // Side placement instead of flipping over the control
      top = Math.min(vh - tipH - 16, Math.max(16, anchor.top));
      left = Math.min(vw - tipW - 16, anchor.right + gap);
      if (left < 16) left = Math.max(16, anchor.left - tipW - gap);
    }
  } else {
    if (top + tipH > vh - 16) top = Math.max(16, (anchor?.top || tipH) - tipH - gap);
    if (top < 16) top = Math.min(vh - tipH - 16, (anchor?.bottom || 0) + gap);
  }

  pushClear();
  return { top, left };
}

/**
 * Custom spotlight walkthrough — SVG evenodd mask with per-target rounded holes.
 */
export default function TutorialController({ signals }) {
  const { onboardingTheme, finishOnboarding } = useOnboarding();
  const isMobile = useIsMobile();
  const steps = useMemo(() => buildTutorialSteps({ isMobile }), [isMobile]);
  const [stepIndex, setStepIndex] = useState(0);
  const [cutouts, setCutouts] = useState([]);
  const [tipPos, setTipPos] = useState({ top: 80, left: 16 });
  const [bikeMenuOpened, setBikeMenuOpened] = useState(false);
  const [bikeChanged, setBikeChanged] = useState(false);
  const [profileMenuOpened, setProfileMenuOpened] = useState(false);
  const [profileChanged, setProfileChanged] = useState(false);
  const tipRef = useRef(null);
  const catcherRef = useRef(null);
  const cleanupRef = useRef(null);
  const prevOverlayRef = useRef(signals.overlayMode);
  const [overlayChangedWhileExpanded, setOverlayChangedWhileExpanded] = useState(false);
  const [rightSwipesSinceBars, setRightSwipesSinceBars] = useState(0);
  const prevPageRef = useRef(signals.islandPage);
  const sawBarsRef = useRef(false);
  const [cameraSettled, setCameraSettled] = useState(true);
  const [viewport, setViewport] = useState(() => ({
    w: typeof window !== 'undefined' ? window.innerWidth : 0,
    h: typeof window !== 'undefined' ? window.innerHeight : 0,
  }));

  const step = steps[stepIndex] || null;

  const markBikeMenuOpened = useCallback(() => setBikeMenuOpened(true), []);
  const markProfileMenuOpened = useCallback(() => setProfileMenuOpened(true), []);

  // Reliably unlock Next when the dropdown is open (click-through catcher can miss listeners).
  useEffect(() => {
    if (step?.id !== 'profile-selector') return undefined;
    const check = () => {
      if (document.querySelector('[data-zone="routing-core"] .rc-quick__slot:first-child .rc-menu')) {
        setProfileMenuOpened(true);
      }
    };
    check();
    const t = window.setInterval(check, 200);
    return () => window.clearInterval(t);
  }, [step?.id]);

  useEffect(() => {
    if (step?.id !== 'bike-type') return undefined;
    const check = () => {
      if (document.querySelector('[data-zone="routing-core"] .rc-quick__slot:nth-child(2) .rc-menu')) {
        setBikeMenuOpened(true);
      }
    };
    check();
    const t = window.setInterval(check, 200);
    return () => window.clearInterval(t);
  }, [step?.id]);

  const initialBikeRef = useRef(null);
  useEffect(() => {
    if (step?.id !== 'bike-type') return;
    if (initialBikeRef.current == null) {
      initialBikeRef.current = signals.sessionBikeType;
      return;
    }
    if (signals.sessionBikeType !== initialBikeRef.current) {
      setBikeChanged(true);
    }
  }, [step?.id, signals.sessionBikeType]);

  const initialProfileRef = useRef(null);
  useEffect(() => {
    if (step?.id !== 'profile-selector') return;
    if (initialProfileRef.current == null) {
      initialProfileRef.current = signals.activeProfileId;
      return;
    }
    if (signals.activeProfileId !== initialProfileRef.current) {
      setProfileChanged(true);
    }
  }, [step?.id, signals.activeProfileId]);

  useEffect(() => {
    if (signals.islandExpanded && signals.overlayMode !== prevOverlayRef.current) {
      setOverlayChangedWhileExpanded(true);
    }
    prevOverlayRef.current = signals.overlayMode;
  }, [signals.overlayMode, signals.islandExpanded]);

  useEffect(() => {
    const page = signals.islandPage;
    if (page === 2) sawBarsRef.current = true;
    if (
      sawBarsRef.current
      && prevPageRef.current != null
      && page < prevPageRef.current
    ) {
      setRightSwipesSinceBars((n) => n + (prevPageRef.current - page));
    }
    prevPageRef.current = page;
  }, [signals.islandPage]);

  // Wait for fitBounds / flyTo to finish before punching a route bbox hole.
  useEffect(() => {
    const needsCamera = Boolean(step?.routeBounds || step?.routeBoundsAlongside);
    if (!needsCamera) {
      setCameraSettled(true);
      return undefined;
    }
    setCameraSettled(false);
    const api = signals.mapApiRef?.current;
    if (!api?.onceIdle) {
      const t = window.setTimeout(() => setCameraSettled(true), 1100);
      return () => window.clearTimeout(t);
    }
    // Brief delay so an in-flight fitBounds can start moving first.
    let cancelIdle = null;
    const t0 = window.setTimeout(() => {
      cancelIdle = api.onceIdle(() => {
        window.requestAnimationFrame(() => setCameraSettled(true));
      }, 2200);
    }, 80);
    return () => {
      window.clearTimeout(t0);
      if (typeof cancelIdle === 'function') cancelIdle();
    };
  }, [step?.id, step?.routeBounds, step?.routeBoundsAlongside, signals.mapApiRef]);

  const liveSignals = useMemo(() => ({
    ...signals,
    bikeMenuOpened,
    bikeChanged,
    profileMenuOpened,
    profileChanged,
    overlayChangedWhileExpanded,
    rightSwipesSinceBars,
    markBikeMenuOpened,
    markProfileMenuOpened,
  }), [
    signals, bikeMenuOpened, bikeChanged, profileMenuOpened, profileChanged,
    overlayChangedWhileExpanded, rightSwipesSinceBars,
    markBikeMenuOpened, markProfileMenuOpened,
  ]);

  const goNext = useCallback(() => {
    if (!step) return;
    if (cleanupRef.current) {
      cleanupRef.current();
      cleanupRef.current = null;
    }
    if (step.advance?.finish || stepIndex >= steps.length - 1) {
      finishOnboarding({ tutorialComplete: true });
      return;
    }
    setStepIndex((i) => i + 1);
  }, [step, stepIndex, steps.length, finishOnboarding]);

  useEffect(() => {
    if (!step || step.advance?.type !== 'auto') return undefined;
    const when = step.advance.when;
    if (typeof when !== 'function') return undefined;
    if (when(liveSignals)) {
      const t = window.setTimeout(goNext, 280);
      return () => window.clearTimeout(t);
    }
    return undefined;
  }, [step, liveSignals, goNext]);

  const enteredStepRef = useRef(null);
  useEffect(() => {
    if (!step?.onEnter) return undefined;
    if (enteredStepRef.current === step.id) return undefined;
    enteredStepRef.current = step.id;
    const bag = {
      markBikeMenuOpened,
      markProfileMenuOpened,
      _bikeListenAttached: false,
      _bikeCleanup: null,
      _profileListenAttached: false,
      _profileCleanup: null,
    };
    step.onEnter(bag);
    cleanupRef.current = () => {
      if (typeof bag._bikeCleanup === 'function') bag._bikeCleanup();
      if (typeof bag._profileCleanup === 'function') bag._profileCleanup();
    };
    return () => {
      if (cleanupRef.current) {
        cleanupRef.current();
        cleanupRef.current = null;
      }
    };
  }, [step, markBikeMenuOpened, markProfileMenuOpened]);

  const measure = useCallback(() => {
    if (!step) return;
    setViewport({ w: window.innerWidth, h: window.innerHeight });

    const wantRoute = Boolean(step.routeBounds || step.routeBoundsAlongside);
    // Hold ALL holes until the camera settles — avoids island-first then route pop-in.
    if (wantRoute && !cameraSettled) {
      setCutouts([]);
      return;
    }

    const raw = (step.targets?.() || []).map(normalizeTarget).filter(Boolean);
    const measured = raw
      .map((t) => measureFromElement(t.el, {
        ring: t.ring !== false,
        pad: t.pad ?? PAD,
        capsule: Boolean(t.capsule),
        ringColor: t.ringColor || step.ringColor || null,
      }))
      .filter(Boolean);

    let routeCutout = null;
    if (wantRoute) {
      routeCutout = measureRouteCutout(
        signals.safestPath,
        signals.start,
        signals.end,
        signals.mapApiRef?.current,
      );
      if (routeCutout && step.routeBoundsAlongside) {
        routeCutout = clipRouteAwayFromChrome(routeCutout, measured);
      }
      if (routeCutout) {
        if (step.routeBounds) {
          measured.length = 0;
          measured.push(routeCutout);
        } else {
          measured.push(routeCutout);
        }
      }
    }

    // primaryTarget is tip/emphasis only — do NOT add a second ring.
    const primary = step.primaryTarget?.();

    setCutouts(measured);

    const tipEl = tipRef.current;
    const tipW = tipEl?.offsetWidth || 320;
    const tipH = tipEl?.offsetHeight || 140;

    let anchor = null;
    if (primary) {
      const pr = primary.getBoundingClientRect();
      if (pr.width > 0) {
        anchor = {
          top: pr.top,
          left: pr.left,
          width: pr.width,
          height: pr.height,
          bottom: pr.bottom,
          right: pr.right,
        };
      }
    }
    if (!anchor && measured[0]) {
      const c = measured.find((m) => m.ring) || measured[0];
      anchor = {
        top: c.top,
        left: c.left,
        width: c.width,
        height: c.height,
        bottom: c.top + c.height,
        right: c.left + c.width,
      };
    }

    const avoid = step.placement === 'avoid-route' && routeCutout
      ? [routeCutout, ...measured.filter((m) => m !== routeCutout)]
      : measured;

    setTipPos(placeTooltip(anchor, step.placement, tipW, tipH, avoid));
  }, [
    step, cameraSettled,
    signals.safestPath, signals.start, signals.end, signals.mapApiRef,
  ]);

  useLayoutEffect(() => {
    measure();
    const onResize = () => measure();
    window.addEventListener('resize', onResize);
    window.addEventListener('scroll', onResize, true);

    const nodes = (step?.targets?.() || [])
      .map(normalizeTarget)
      .filter(Boolean)
      .map((t) => t.el);
    const ro = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(measure)
      : null;
    nodes.forEach((n) => ro?.observe(n));

    const t = window.setInterval(measure, 350);

    return () => {
      window.removeEventListener('resize', onResize);
      window.removeEventListener('scroll', onResize, true);
      ro?.disconnect();
      window.clearInterval(t);
    };
  }, [measure, step]);

  const buttonEnabled = useMemo(() => {
    if (!step || step.advance?.type !== 'button') return false;
    if (typeof step.advance.require === 'function') {
      return step.advance.require(liveSignals);
    }
    return true;
  }, [step, liveSignals]);

  const handleSkip = () => {
    finishOnboarding({ tutorialComplete: false });
  };

  /** Pass clicks through spotlight holes (SVG fill hit-testing is unreliable). */
  const handleCatcherPointerDown = (e) => {
    if (step?.mapInteract) return;
    const { clientX: x, clientY: y } = e;
    if (!cutouts.some((c) => pointInCutout(x, y, c))) return;
    const catcher = catcherRef.current;
    if (!catcher) return;
    catcher.style.pointerEvents = 'none';
    const under = document.elementFromPoint(x, y);
    catcher.style.pointerEvents = 'auto';
    if (under && under !== catcher) {
      // Prefer a native click so React onClick handlers fire.
      if (typeof under.click === 'function') under.click();
      else {
        under.dispatchEvent(new MouseEvent('click', {
          bubbles: true,
          cancelable: true,
          clientX: x,
          clientY: y,
          view: window,
        }));
      }
    }
    e.preventDefault();
    e.stopPropagation();
  };

  if (!step) return null;

  const vw = viewport.w;
  const vh = viewport.h;
  const maskPath = buildMaskPath(vw, vh, cutouts);
  const ringCutouts = cutouts.filter((c) => c.ring);
  const catcherPassthrough = Boolean(step.mapInteract);

  return (
    <div className="tut-root" data-theme={onboardingTheme} role="dialog" aria-modal="true" aria-label="Tutorial">
      <svg
        className="tut-mask"
        width={vw}
        height={vh}
        viewBox={`0 0 ${vw} ${vh}`}
        aria-hidden
      >
        <path
          className="tut-mask__dim"
          d={maskPath}
          fillRule="evenodd"
        />
      </svg>

      {!catcherPassthrough && (
        <div
          ref={catcherRef}
          className="tut-catcher"
          onPointerDown={handleCatcherPointerDown}
          aria-hidden
        />
      )}

      {ringCutouts.map((c, i) => (
        // eslint-disable-next-line react/no-array-index-key
        <div
          key={i}
          className={`tut-ring${c.ringColor === '#ffffff' || c.ringColor === '#fff' ? ' tut-ring--light' : ''}`}
          style={{
            top: c.top,
            left: c.left,
            width: c.width,
            height: c.height,
            borderRadius: c.rx >= 999 ? '999px' : `${c.rx}px`,
            ...(c.ringColor ? { boxShadow: `0 0 0 2px ${c.ringColor}` } : null),
          }}
          aria-hidden
        />
      ))}

      <div
        ref={tipRef}
        className="tut-tooltip"
        style={{ top: tipPos.top, left: tipPos.left }}
      >
        <h2 className="tut-tooltip__title">{step.title}</h2>
        <p className="tut-tooltip__body">{step.body}</p>
        {step.advance?.type === 'button' && (
          <div className="tut-tooltip__actions">
            <button
              type="button"
              className="tut-tooltip__next"
              disabled={!buttonEnabled}
              onClick={goNext}
            >
              {step.advance?.finish ? 'Done' : 'Next'}
            </button>
          </div>
        )}
      </div>

      <button type="button" className="tut-skip" onClick={handleSkip} aria-label="Skip tour">
        <X size={14} strokeWidth={2.4} aria-hidden />
        Skip tour
      </button>
    </div>
  );
}

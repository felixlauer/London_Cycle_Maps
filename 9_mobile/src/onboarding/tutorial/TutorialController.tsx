import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Dimensions,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { X } from 'lucide-react-native';
import { useSafeAreaEdges } from '../../lib/safeArea';
import { useOnboarding } from '../OnboardingContext';
import {
  blockerRectsForHoles,
  buildMaskPath,
  clipRouteAwayFromChrome,
  isolateCutouts,
  MARKER_PAD,
  placeTooltip,
  ROUTE_PAD,
} from './tutorialGeometry';
import {
  measureTutorialAnchors,
  subscribeTutorialAnchors,
  type MeasuredCutout,
} from './tutorialRegistry';
import {
  buildMobileTutorialSteps,
  type TutorialSignals,
} from './tutorialSteps';

type Props = {
  signals: TutorialSignals;
};

async function measureRouteCutout(
  path: number[][] | null | undefined,
  start: [number, number] | null | undefined,
  end: [number, number] | null | undefined,
  projectToWindow: TutorialSignals['projectToWindow'],
  vw: number,
  vh: number,
): Promise<MeasuredCutout | null> {
  if (!projectToWindow) return null;
  const pts: { x: number; y: number }[] = [];

  const pushLatLon = async (lat: number, lon: number) => {
    if (lat == null || lon == null || !Number.isFinite(lat) || !Number.isFinite(lon)) return;
    try {
      const p = await projectToWindow([lon, lat]);
      if (p && Number.isFinite(p.x) && Number.isFinite(p.y)) pts.push(p);
    } catch {
      /* skip */
    }
  };

  const raw = path || [];
  const stride = Math.max(1, Math.ceil(raw.length / 64));
  for (let i = 0; i < raw.length; i += stride) {
    const pair = raw[i];
    if (!Array.isArray(pair) || pair.length < 2) continue;
    await pushLatLon(pair[0], pair[1]);
  }
  if (raw.length > 1) {
    const last = raw[raw.length - 1];
    if (Array.isArray(last) && last.length >= 2) await pushLatLon(last[0], last[1]);
  }
  if (Array.isArray(start) && start.length >= 2) await pushLatLon(start[0], start[1]);
  if (Array.isArray(end) && end.length >= 2) await pushLatLon(end[0], end[1]);

  if (pts.length < 2) return null;

  // Only use points near the viewport — off-screen Mapbox projections can be
  // extreme and stretch the hole to full screen height/width.
  const EDGE = 64;
  const near = pts.filter((p) => (
    p.x >= -EDGE && p.x <= vw + EDGE
    && p.y >= -EDGE && p.y <= vh + EDGE
  ));
  const usePts = near.length >= 2
    ? near
    : pts.map((p) => ({
      x: Math.max(0, Math.min(vw, p.x)),
      y: Math.max(0, Math.min(vh, p.y)),
    }));

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  usePts.forEach((p) => {
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x);
    maxY = Math.max(maxY, p.y);
  });

  const pad = ROUTE_PAD + MARKER_PAD;
  const left = Math.max(0, minX - pad);
  const top = Math.max(0, minY - pad);
  const right = Math.min(vw, maxX + pad);
  const bottom = Math.min(vh, maxY + pad);
  const width = Math.max(0, right - left);
  const height = Math.max(0, bottom - top);
  if (width < 24 || height < 24) return null;

  // Guard against a near-fullscreen hole from bad projections.
  if (width > vw * 0.92 && height > vh * 0.92) return null;

  return {
    top,
    left,
    width,
    height,
    rx: 16,
    ring: true,
    ringColor: null,
  };
}

/**
 * Custom spotlight walkthrough — SVG evenodd mask (web TutorialController).
 */
export function TutorialController({ signals }: Props) {
  const { onboardingTheme, finishOnboarding, setTutorialMapPass } = useOnboarding();
  const steps = useMemo(() => buildMobileTutorialSteps(), []);
  const insets = useSafeAreaEdges();
  const safeBottom = insets.bottom;
  const skipBottom = safeBottom + 20;
  const [stepIndex, setStepIndex] = useState(0);
  const [cutouts, setCutouts] = useState<MeasuredCutout[]>([]);
  const [tipPos, setTipPos] = useState({ top: 80, left: 16 });
  const [tipSize, setTipSize] = useState({ w: 280, h: 140 });
  const [bikeMenuOpened, setBikeMenuOpened] = useState(false);
  const [bikeChanged, setBikeChanged] = useState(false);
  const [profileMenuOpened, setProfileMenuOpened] = useState(false);
  const [profileChanged, setProfileChanged] = useState(false);
  const [overlayChangedWhileExpanded, setOverlayChangedWhileExpanded] = useState(false);
  const [rightSwipesSinceBars, setRightSwipesSinceBars] = useState(0);
  const [cameraSettled, setCameraSettled] = useState(true);
  const [viewport, setViewport] = useState(() => {
    const { width, height } = Dimensions.get('window');
    return { w: width, h: height };
  });

  const prevOverlayRef = useRef(signals.overlayMode);
  const prevPageRef = useRef(signals.islandPage);
  const sawBarsRef = useRef(false);
  const measureGen = useRef(0);

  const step = steps[stepIndex] || null;
  const isDark = onboardingTheme === 'dark';

  useEffect(() => {
    setTutorialMapPass(Boolean(step?.mapInteract));
    return () => setTutorialMapPass(false);
  }, [step?.id, step?.mapInteract, setTutorialMapPass]);

  const markBikeMenuOpened = useCallback(() => setBikeMenuOpened(true), []);
  const markProfileMenuOpened = useCallback(() => setProfileMenuOpened(true), []);

  useEffect(() => {
    const sub = Dimensions.addEventListener('change', ({ window }) => {
      setViewport({ w: window.width, h: window.height });
    });
    return () => sub.remove();
  }, []);

  // Detect open menus via registered anchors (Modal menus).
  useEffect(() => {
    if (step?.id !== 'profile-selector') return undefined;
    const check = () => {
      void measureTutorialAnchors([{ id: 'tut-profile-menu' }]).then((m) => {
        if (m.length) setProfileMenuOpened(true);
      });
    };
    check();
    const t = setInterval(check, 250);
    return () => clearInterval(t);
  }, [step?.id]);

  useEffect(() => {
    if (step?.id !== 'bike-type') return undefined;
    const check = () => {
      void measureTutorialAnchors([{ id: 'tut-bike-menu' }]).then((m) => {
        if (m.length) setBikeMenuOpened(true);
      });
    };
    check();
    const t = setInterval(check, 250);
    return () => clearInterval(t);
  }, [step?.id]);

  const initialBikeRef = useRef<string | null | undefined>(null);
  useEffect(() => {
    if (step?.id !== 'bike-type') return;
    if (initialBikeRef.current == null) {
      initialBikeRef.current = signals.sessionBikeType;
      return;
    }
    if (signals.sessionBikeType !== initialBikeRef.current) setBikeChanged(true);
  }, [step?.id, signals.sessionBikeType]);

  const initialProfileRef = useRef<string | null | undefined>(null);
  useEffect(() => {
    if (step?.id !== 'profile-selector') return;
    if (initialProfileRef.current == null) {
      initialProfileRef.current = signals.activeProfileId;
      return;
    }
    if (signals.activeProfileId !== initialProfileRef.current) setProfileChanged(true);
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
      && page != null
      && page < prevPageRef.current
    ) {
      setRightSwipesSinceBars((n) => n + (prevPageRef.current! - page));
    }
    prevPageRef.current = page;
  }, [signals.islandPage]);

  // Wait for fitBounds before punching route holes.
  useEffect(() => {
    const needsCamera = Boolean(step?.routeBounds || step?.routeBoundsAlongside);
    if (!needsCamera) {
      setCameraSettled(true);
      return undefined;
    }
    setCameraSettled(false);
    const t = setTimeout(() => setCameraSettled(true), 1100);
    return () => clearTimeout(t);
  }, [step?.id, step?.routeBounds, step?.routeBoundsAlongside]);

  const liveSignals = useMemo((): TutorialSignals => ({
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
      const t = setTimeout(goNext, 280);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [step, liveSignals, goNext]);

  // Reset per-step unlock flags when entering a new step.
  useEffect(() => {
    if (!step) return;
    if (step.id === 'profile-selector') {
      setProfileMenuOpened(false);
      setProfileChanged(false);
      initialProfileRef.current = null;
    }
    if (step.id === 'bike-type') {
      setBikeMenuOpened(false);
      setBikeChanged(false);
      initialBikeRef.current = null;
    }
    if (step.id === 'island-swipe-right') {
      setRightSwipesSinceBars(0);
      sawBarsRef.current = signals.islandPage === 2;
    }
  }, [step?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const measure = useCallback(async () => {
    if (!step) return;
    const gen = ++measureGen.current;
    const { w: vw, h: vh } = viewport;

    const wantRoute = Boolean(step.routeBounds || step.routeBoundsAlongside);
    if (wantRoute && !cameraSettled) {
      setCutouts([]);
      return;
    }

    const measured = await measureTutorialAnchors(
      (step.targets || []).map((t) => ({
        id: t.id,
        opts: {
          ...t.opts,
          ...(step.ringColor ? { ringColor: step.ringColor } : null),
        },
      })),
    );
    if (gen !== measureGen.current) return;

    // Island radius: capsule when collapsed, 20 when expanded.
    if (signals.islandExpanded) {
      measured.forEach((m, i) => {
        const spec = step.targets[i];
        if (spec?.id === 'tut-island') {
          m.rx = 20;
        }
      });
    }

    let routeCutout: MeasuredCutout | null = null;
    if (wantRoute) {
      routeCutout = await measureRouteCutout(
        signals.safestPath,
        signals.start,
        signals.end,
        signals.projectToWindow,
        vw,
        vh,
      );
      if (gen !== measureGen.current) return;
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

    setCutouts([...measured]);

    let anchor: {
      top: number; left: number; width: number; height: number;
      bottom: number; right: number;
    } | null = null;

    if (step.primaryTargetId) {
      const primary = await measureTutorialAnchors([{ id: step.primaryTargetId }]);
      if (gen !== measureGen.current) return;
      if (primary[0]) {
        const c = primary[0];
        anchor = {
          top: c.top,
          left: c.left,
          width: c.width,
          height: c.height,
          bottom: c.top + c.height,
          right: c.left + c.width,
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

    setTipPos(
      placeTooltip(anchor, step.placement, tipSize.w, tipSize.h, vw, vh, avoid, insets),
    );
  }, [
    step, cameraSettled, viewport, tipSize.w, tipSize.h,
    signals.safestPath, signals.start, signals.end, signals.projectToWindow,
    signals.islandExpanded, signals.islandPage,
    // Insets land a frame after mount on iOS; re-measure so holes and the tip
    // move with the Dynamic Island / home indicator instead of staying stale.
    insets,
  ]);

  useEffect(() => {
    void measure();
    const unsub = subscribeTutorialAnchors(() => { void measure(); });
    const t = setInterval(() => { void measure(); }, 350);
    return () => {
      unsub();
      clearInterval(t);
    };
  }, [measure]);

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

  if (!step) return null;

  const vw = viewport.w;
  const vh = viewport.h;
  // Isolate once so mask holes and rings stay aligned (padding matched the ring).
  const displayCutouts = isolateCutouts(cutouts);
  const maskPath = buildMaskPath(vw, vh, displayCutouts);
  const ringCutouts = displayCutouts.filter((c) => c.ring);

  // Pass through map only on start/end. Always block non-spotlighted chrome.
  const mapInteract = Boolean(step.mapInteract);

  const tipW = Math.min(280, vw - 48);

  // Start/end: punch a map pass below the waypoint chrome so pins work,
  // while chrome outside the spotlight (incl. right controls) stays blocked.
  const blockHoles = (() => {
    if (!mapInteract) return displayCutouts;
    let chromeBottom = 0;
    displayCutouts.forEach((c) => {
      chromeBottom = Math.max(chromeBottom, c.top + c.height);
    });
    if (chromeBottom < 120) chromeBottom = Math.min(vh * 0.42, 320);
    const RIGHT_CONTROLS = 72;
    const BOTTOM_SAFE = safeBottom + 28;
    const mapHole = {
      top: chromeBottom + 6,
      left: 0,
      width: Math.max(0, vw - RIGHT_CONTROLS),
      height: Math.max(0, vh - chromeBottom - 6 - BOTTOM_SAFE),
      rx: 0,
      ring: false,
      ringColor: null,
    };
    return mapHole.height > 40 ? [...displayCutouts, mapHole] : displayCutouts;
  })();

  const blockers = blockerRectsForHoles(vw, vh, blockHoles);

  return (
    <View style={styles.root} pointerEvents="box-none" accessibilityLabel="Tutorial">
      <Svg
        width={vw}
        height={vh}
        style={StyleSheet.absoluteFill}
        pointerEvents="none"
      >
        <Path
          d={maskPath}
          fill={isDark ? 'rgba(0,0,0,0.8)' : 'rgba(0,0,0,0.72)'}
          fillRule="evenodd"
        />
      </Svg>

      {/* Opaque-to-hit-test catchers — Android ignores fully transparent views. */}
      <View style={styles.catcherLayer} pointerEvents="box-none">
        {blockers.map((b, i) => (
          <View
            // eslint-disable-next-line react/no-array-index-key
            key={`block-${i}-${b.left}-${b.top}`}
            collapsable={false}
            pointerEvents="auto"
            style={{
              position: 'absolute',
              top: b.top,
              left: b.left,
              width: b.width,
              height: b.height,
              backgroundColor: 'rgba(0,0,0,0.002)',
            }}
          />
        ))}
      </View>

      {ringCutouts.map((c, i) => {
        const color = c.ringColor || '#ff0061';
        const radius = c.rx >= Math.min(c.width, c.height) / 2 - 0.5
          ? 999
          : c.rx;
        return (
          <View
            key={`ring-${i}-${c.left}-${c.top}`}
            pointerEvents="none"
            style={[
              styles.ring,
              {
                top: c.top,
                left: c.left,
                width: c.width,
                height: c.height,
                borderRadius: radius,
                borderColor: color,
              },
            ]}
          />
        );
      })}

      <View
        style={[
          styles.tooltip,
          {
            top: tipPos.top,
            left: tipPos.left,
            width: tipW,
            backgroundColor: isDark ? '#1c1c1e' : '#ffffff',
            borderColor: isDark ? '#3a3a3c' : '#e5e7eb',
          },
        ]}
        onLayout={(e) => {
          const { width, height } = e.nativeEvent.layout;
          if (width > 0 && height > 0) {
            setTipSize((prev) => (
              prev.w === width && prev.h === height ? prev : { w: width, h: height }
            ));
          }
        }}
        pointerEvents="auto"
      >
        <Text style={[styles.title, { color: isDark ? '#fafafa' : '#18181b' }]}>
          {step.title}
        </Text>
        <Text style={[styles.body, { color: isDark ? '#a1a1aa' : '#71717a' }]}>
          {step.body}
        </Text>
        {step.advance?.type === 'button' ? (
          <View style={styles.actions}>
            <Pressable
              accessibilityRole="button"
              disabled={!buttonEnabled}
              onPress={goNext}
              // The pill is ~29 pt tall; slop brings the target to 45 pt.
              hitSlop={8}
              style={({ pressed }) => [
                styles.next,
                !buttonEnabled && styles.nextDisabled,
                pressed && buttonEnabled && styles.nextPressed,
              ]}
            >
              <Text style={styles.nextText}>
                {step.advance?.finishLabel
                  || (step.advance?.finish ? 'Finish tutorial' : 'Next')}
              </Text>
            </Pressable>
          </View>
        ) : null}
      </View>

      <View style={[styles.skipRow, { bottom: skipBottom }]} pointerEvents="box-none">
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Skip tour"
          onPress={handleSkip}
          style={[
            styles.skip,
            {
              backgroundColor: isDark ? 'rgba(28,28,30,0.94)' : 'rgba(255,255,255,0.92)',
              borderColor: isDark ? '#3a3a3c' : '#e5e7eb',
            },
          ]}
          hitSlop={6}
        >
          <X size={14} strokeWidth={2.4} color={isDark ? '#fafafa' : '#18181b'} />
          <Text style={[styles.skipText, { color: isDark ? '#fafafa' : '#18181b' }]}>
            Skip tour
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    ...StyleSheet.absoluteFill,
    zIndex: 2000,
    elevation: 2000,
  },
  catcherLayer: {
    ...StyleSheet.absoluteFill,
    zIndex: 1,
    elevation: 2001,
  },
  ring: {
    position: 'absolute',
    borderWidth: 2,
    backgroundColor: 'transparent',
    zIndex: 2,
  },
  tooltip: {
    position: 'absolute',
    zIndex: 2001,
    paddingVertical: 11,
    paddingHorizontal: 13,
    borderRadius: 12,
    borderWidth: 1,
    elevation: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.12,
    shadowRadius: 12,
  },
  title: {
    marginBottom: 4,
    fontSize: 13.5,
    fontWeight: '700',
    letterSpacing: -0.1,
  },
  body: {
    fontSize: 12,
    fontWeight: '500',
    lineHeight: 17,
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    marginTop: 10,
  },
  next: {
    borderRadius: 999,
    paddingVertical: 7,
    paddingHorizontal: 14,
    backgroundColor: '#ff0061',
  },
  nextDisabled: { opacity: 0.45 },
  nextPressed: { transform: [{ scale: 0.97 }] },
  nextText: {
    color: '#fff',
    fontSize: 12.5,
    fontWeight: '600',
  },
  skipRow: {
    position: 'absolute',
    left: 0,
    right: 0,
    zIndex: 2001,
    alignItems: 'center',
  },
  skip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 999,
    borderWidth: 1,
    elevation: 6,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
  },
  skipText: {
    fontSize: 12.5,
    fontWeight: '600',
  },
});

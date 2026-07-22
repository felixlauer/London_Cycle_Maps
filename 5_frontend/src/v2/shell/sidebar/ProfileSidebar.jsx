import React, { useEffect, useRef, useState } from 'react';
import {
  animate,
  motion,
  useMotionValue,
  useReducedMotion,
  useTransform,
} from 'motion/react';
import { ArrowLeft, PanelRightClose } from 'lucide-react';
import AuthPanel from '../../../auth/AuthPanel';
import PresetWizardShell from '../../wizard/PresetWizardShell';
import { useSidebar, SIDEBAR_WIDTH_PX } from '../SidebarContext';
import { useIsMobile } from '../../hooks/useMediaQuery';
import { useOnboarding } from '../../onboarding/OnboardingContext';
import ProfilesSection from './ProfilesSection';
import AccountManageSection from './AccountManageSection';
import SystemFooter from './SystemFooter';
import './sidebar.css';

const TWEEN = { type: 'tween', duration: 0.48, ease: [0.23, 1, 0.32, 1] };
const SWIPE_CLOSE_PX = 72;

function useViewport() {
  const [dims, setDims] = useState(() => ({
    w: typeof window !== 'undefined' ? window.innerWidth : 1280,
    h: typeof window !== 'undefined' ? window.innerHeight : 800,
  }));

  useEffect(() => {
    const onResize = () => setDims({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  return dims;
}

/**
 * Overlay drawer — morphs to fullscreen wizard via transform (not width).
 * Mobile: full-width overlay; no chrome push. Swipe right to dismiss.
 */
export default function ProfileSidebar({
  profiles,
  activeProfileId,
  onSelectProfile,
  onDeleteProfile,
  onProfileCreated,
  onProfileUpdated,
}) {
  const {
    open,
    view,
    authTab,
    themeMode,
    editingProfileId,
    closeSidebar,
    closeAuthPanel,
    closeWizard,
    shellRef,
    profilesSectionRef,
    sidebarWidth,
  } = useSidebar();
  const { replayTutorial } = useOnboarding();
  const isMobile = useIsMobile();
  const reduceMotion = useReducedMotion();
  const widthMv = useMotionValue(0);
  const morphMv = useMotionValue(0);
  const wasOpen = useRef(false);
  const swipeStart = useRef(null);
  const [wizardMounted, setWizardMounted] = useState(false);
  const [accountPanel, setAccountPanel] = useState(null);
  const [dragOffset, setDragOffset] = useState(0);
  const { w: vw } = useViewport();

  const isWizard = view === 'wizard';
  const isAuth = view === 'auth';
  const showWizard = isWizard || wizardMounted;
  const mobileDrawerW = vw;
  const drawerTarget = isMobile ? mobileDrawerW : (sidebarWidth || SIDEBAR_WIDTH_PX);
  const profilesStacked = Boolean(accountPanel);

  useEffect(() => {
    if (!open) {
      setAccountPanel(null);
      setDragOffset(0);
    }
  }, [open]);

  useEffect(() => {
    const target = open ? drawerTarget : 0;
    const tween = reduceMotion ? { duration: 0.01 } : TWEEN;
    const ctrl = animate(widthMv, target, {
      ...tween,
      onUpdate: (v) => {
        const el = shellRef.current;
        if (!el) return;
        // Mobile: overlay only — never push island/controls via --shell-sidebar-w
        if (isMobile) {
          el.style.setProperty('--shell-sidebar-w', '0px');
        } else {
          el.style.setProperty('--shell-sidebar-w', `${Math.round(v)}px`);
        }
      },
      onComplete: () => {
        const el = shellRef.current;
        if (!el) return;
        if (isMobile) {
          el.style.setProperty('--shell-sidebar-w', '0px');
        } else {
          el.style.setProperty('--shell-sidebar-w', `${target}px`);
        }
        wasOpen.current = open;
      },
    });
    return () => ctrl.stop();
  }, [open, reduceMotion, drawerTarget, widthMv, shellRef, isMobile]);

  useEffect(() => {
    if (isWizard) setWizardMounted(true);
  }, [isWizard]);

  useEffect(() => {
    const target = isWizard ? 1 : 0;
    const tween = reduceMotion ? { duration: 0.01 } : TWEEN;
    const ctrl = animate(morphMv, target, {
      ...tween,
      onComplete: () => {
        if (!isWizard) setWizardMounted(false);
      },
    });
    return () => ctrl.stop();
  }, [isWizard, reduceMotion, morphMv]);

  const morphScaleX = useTransform(morphMv, (p) => {
    if (p <= 0) return 1;
    const fromW = isMobile ? mobileDrawerW : SIDEBAR_WIDTH_PX;
    const from = fromW / Math.max(vw, 1);
    return from + (1 - from) * p;
  });

  const morphOpacity = useTransform(morphMv, (p) => (p > 0 && p < 1 ? 0.98 + p * 0.02 : 1));

  const handleCollapse = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (isWizard) {
      closeWizard();
      return;
    }
    if (isAuth) {
      closeAuthPanel();
      return;
    }
    closeSidebar();
  };

  const handleReturnToMap = () => {
    closeWizard();
  };

  const handleWizardCreated = (profile) => {
    onProfileCreated?.(profile);
    closeWizard();
  };

  const handleWizardUpdated = (profile) => {
    onProfileUpdated?.(profile);
    closeWizard();
  };

  const onSwipeStart = (e) => {
    if (!isMobile || !open || showWizard) return;
    if (e.target?.closest?.('input, textarea, select, button, a')) return;
    const t = e.touches?.[0];
    if (!t) return;
    swipeStart.current = { x: t.clientX, y: t.clientY };
  };

  const onSwipeMove = (e) => {
    if (!swipeStart.current) return;
    const t = e.touches?.[0];
    if (!t) return;
    const dx = t.clientX - swipeStart.current.x;
    const dy = t.clientY - swipeStart.current.y;
    if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > 18) {
      swipeStart.current = null;
      setDragOffset(0);
      return;
    }
    // Right-edge drawer: swipe right to dismiss.
    setDragOffset(Math.max(0, dx));
  };

  const onSwipeEnd = (e) => {
    if (!swipeStart.current) {
      setDragOffset(0);
      return;
    }
    const t = e.changedTouches?.[0];
    const dx = t ? t.clientX - swipeStart.current.x : dragOffset;
    swipeStart.current = null;
    setDragOffset(0);
    if (dx > SWIPE_CLOSE_PX) {
      if (isAuth) closeAuthPanel();
      else closeSidebar();
    }
  };

  return (
    <aside
      className={[
        'profile-sidebar',
        open ? 'is-open' : '',
        showWizard ? 'is-wizard' : '',
        isAuth ? 'is-auth' : '',
        isMobile ? 'is-mobile' : '',
      ].filter(Boolean).join(' ')}
      style={isMobile && open ? {
        width: `${drawerTarget}px`,
        transform: dragOffset ? `translateX(${dragOffset}px)` : undefined,
        transition: dragOffset ? 'none' : undefined,
      } : undefined}
      aria-hidden={!open}
      aria-label="Profile and settings"
      onTouchStart={onSwipeStart}
      onTouchMove={onSwipeMove}
      onTouchEnd={onSwipeEnd}
    >
      {!showWizard && !isMobile && (
        <button
          type="button"
          className="profile-sidebar__collapse"
          aria-label="Collapse sidebar"
          tabIndex={open ? 0 : -1}
          onClick={handleCollapse}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <PanelRightClose size={16} strokeWidth={2.2} aria-hidden />
        </button>
      )}

      <div className="profile-sidebar__clip">
        <motion.div
          className="profile-sidebar__frame"
          style={{
            ...(isMobile && !showWizard ? { width: drawerTarget } : {}),
            ...(showWizard ? {
              transformOrigin: 'top right',
              scaleX: morphScaleX,
              opacity: morphOpacity,
            } : {}),
          }}
        >
          {showWizard ? (
            <>
              {!isMobile && (
                <div className="profile-sidebar__wizard-chrome">
                  <button
                    type="button"
                    className="profile-sidebar__return"
                    onClick={handleReturnToMap}
                    aria-label="Return to map"
                  >
                    <ArrowLeft size={15} strokeWidth={2.2} aria-hidden />
                    <span>Return to map</span>
                  </button>
                </div>
              )}
              <div className="profile-sidebar__wizard-body">
                <PresetWizardShell
                  key={editingProfileId || 'create'}
                  themeMode={themeMode}
                  editingProfileId={editingProfileId}
                  onCreated={handleWizardCreated}
                  onUpdated={handleWizardUpdated}
                />
              </div>
            </>
          ) : (
            <>
              <div className="profile-sidebar__top" aria-hidden />

              {isAuth && (
                <div className="profile-sidebar__auth">
                  <AuthPanel
                    variant="inline"
                    themeMode={themeMode}
                    initialTab={authTab}
                    visible={isAuth}
                    onClose={closeAuthPanel}
                  />
                </div>
              )}

              <div className="profile-sidebar__scroll">
                <ProfilesSection
                  profiles={profiles}
                  activeProfileId={activeProfileId}
                  sectionRef={profilesSectionRef}
                  onDeleteProfile={onDeleteProfile}
                  onSelectProfile={onSelectProfile}
                  stacked={profilesStacked}
                  onStackedActivate={() => setAccountPanel(null)}
                />
              </div>

              <div className="profile-sidebar__bottom">
                <AccountManageSection
                  expandedPanel={accountPanel}
                  onExpandedPanelChange={setAccountPanel}
                />
                <SystemFooter />
                <button
                  type="button"
                  className="sb-revisit-tutorial"
                  onClick={() => {
                    closeSidebar();
                    window.setTimeout(() => replayTutorial(), 320);
                  }}
                >
                  Revisit tutorial?
                </button>
              </div>
            </>
          )}
        </motion.div>
      </div>
    </aside>
  );
}

/**
 * Full-bleed profile drawer — web ProfileSidebar (mobile overlay).
 */
import { useEffect, useRef, useState } from 'react';
import {
  Animated,
  BackHandler,
  Dimensions,
  KeyboardAvoidingView,
  PanResponder,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  AccountManageSection,
  type AccountPanelId,
} from './AccountManageSection';
import { AuthPanel } from './AuthPanel';
import { ProfilePillBar } from './ProfilePillBar';
import { ProfilesSection } from './ProfilesSection';
import { SystemFooter } from './SystemFooter';
import { useSidebar } from './SidebarContext';
import { BugReportModal } from '../feedback/BugReportModal';
import { TutorialAnchor } from '../../onboarding/tutorial/TutorialAnchor';
import { useOnboardingOptional } from '../../onboarding/OnboardingContext';
import { useSafeAreaBottom, useSafeAreaTop } from '../../lib/safeArea';
import type { ProfileRow } from '../../routing/constants';
import { useChrome } from '../../theme/useChrome';
import { PresetWizardShell } from '../../wizard/PresetWizardShell';

const SWIPE_CLOSE_PX = 72;
const OPEN_MS = 280;
const CLOSE_MS = 220;

type Props = {
  profiles?: ProfileRow[];
  activeProfileId?: string | null;
  onSelectProfile?: (id: string) => void;
  onDeleteProfile?: (id: string) => Promise<void> | void;
  onProfileCreated?: (profile: Record<string, unknown>) => void;
  onProfileUpdated?: (profile: Record<string, unknown>) => void;
};

export function ProfileSidebar({
  profiles = [],
  activeProfileId = null,
  onSelectProfile,
  onDeleteProfile,
  onProfileCreated,
  onProfileUpdated,
}: Props) {
  const {
    open,
    view,
    authTab,
    editingProfileId,
    closeSidebar,
    closeAuthPanel,
    closeWizard,
  } = useSidebar();
  const onboarding = useOnboardingOptional();
  const { themeMode, c } = useChrome();
  const topInset = useSafeAreaTop();
  const [accountPanel, setAccountPanel] = useState<AccountPanelId>(null);
  const [bugReportOpen, setBugReportOpen] = useState(false);
  const [wizardMounted, setWizardMounted] = useState(false);
  const screenW = Dimensions.get('window').width;
  const screenH = Dimensions.get('window').height;
  // Account rows and help links sit above the home indicator / gesture bar.
  const bottomPad = useSafeAreaBottom() + 16;

  const progress = useRef(new Animated.Value(0)).current;
  const dragX = useRef(new Animated.Value(0)).current;
  const openRef = useRef(open);
  openRef.current = open;
  const viewRef = useRef(view);
  viewRef.current = view;

  const isAuth = view === 'auth';
  const isWizard = view === 'wizard';
  const profilesStacked = Boolean(accountPanel);

  useEffect(() => {
    if (!open) {
      setAccountPanel(null);
      setBugReportOpen(false);
    }
  }, [open]);

  useEffect(() => {
    if (isWizard) setWizardMounted(true);
    else {
      const t = setTimeout(() => setWizardMounted(false), 280);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [isWizard]);

  const skipCloseAnimRef = useRef(false);
  const screenWRef = useRef(screenW);
  screenWRef.current = screenW;

  useEffect(() => {
    if (open) {
      skipCloseAnimRef.current = false;
      dragX.setValue(0);
      Animated.timing(progress, {
        toValue: 1,
        duration: OPEN_MS,
        useNativeDriver: true,
      }).start();
      return;
    }
    if (skipCloseAnimRef.current) {
      skipCloseAnimRef.current = false;
      dragX.setValue(0);
      progress.setValue(0);
      return;
    }
    dragX.setValue(0);
    Animated.timing(progress, {
      toValue: 0,
      duration: CLOSE_MS,
      useNativeDriver: true,
    }).start();
  }, [open, progress, dragX]);

  useEffect(() => {
    if (!open) return undefined;
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (bugReportOpen) {
        setBugReportOpen(false);
        return true;
      }
      if (viewRef.current === 'wizard') {
        closeWizard();
        return true;
      }
      if (viewRef.current === 'auth') {
        closeAuthPanel();
        return true;
      }
      closeSidebar();
      return true;
    });
    return () => sub.remove();
  }, [open, closeSidebar, closeAuthPanel, closeWizard, bugReportOpen]);

  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, g) => (
        openRef.current
        && viewRef.current !== 'wizard'
        && Math.abs(g.dx) > 10
        && Math.abs(g.dx) > Math.abs(g.dy) * 1.2
        && g.dx > 0
      ),
      onPanResponderMove: (_, g) => {
        dragX.setValue(Math.max(0, g.dx));
      },
      onPanResponderRelease: (_, g) => {
        const dx = Math.max(0, g.dx);
        const shouldClose = dx > SWIPE_CLOSE_PX || g.vx > 0.85;
        if (shouldClose) {
          const w = screenWRef.current;
          const remaining = Math.max(0, w - dx);
          const ms = Math.min(CLOSE_MS, Math.max(100, remaining / Math.max(Math.abs(g.vx), 1.2)));
          Animated.timing(dragX, {
            toValue: w,
            duration: ms,
            useNativeDriver: true,
          }).start(({ finished }) => {
            if (!finished) return;
            skipCloseAnimRef.current = true;
            dragX.setValue(0);
            progress.setValue(0);
            if (viewRef.current === 'auth') closeAuthPanel();
            else closeSidebar();
          });
          return;
        }
        Animated.spring(dragX, {
          toValue: 0,
          useNativeDriver: true,
          bounciness: 0,
          speed: 20,
        }).start();
      },
      onPanResponderTerminate: () => {
        Animated.spring(dragX, {
          toValue: 0,
          useNativeDriver: true,
          bounciness: 0,
          speed: 20,
        }).start();
      },
    }),
  ).current;

  const slideX = Animated.add(
    progress.interpolate({
      inputRange: [0, 1],
      outputRange: [screenW, 0],
    }),
    dragX,
  );

  const backdropOpacity = progress.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 0.55],
  });

  const handleClose = () => {
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

  const handleWizardCreated = (profile: Record<string, unknown>) => {
    onProfileCreated?.(profile);
    closeWizard();
  };

  const handleWizardUpdated = (profile: Record<string, unknown>) => {
    onProfileUpdated?.(profile);
    closeWizard();
  };

  const [mounted, setMounted] = useState(open);
  useEffect(() => {
    if (open) {
      setMounted(true);
      return undefined;
    }
    const t = setTimeout(() => setMounted(false), CLOSE_MS + 40);
    return () => clearTimeout(t);
  }, [open]);

  if (!mounted) return null;

  return (
    <View
      style={[styles.overlay, { width: screenW, height: screenH }]}
      pointerEvents={open ? 'auto' : 'none'}
    >
      <Pressable
        accessibilityLabel="Dismiss sidebar"
        onPress={handleClose}
        style={StyleSheet.absoluteFill}
      >
        <Animated.View
          pointerEvents="none"
          style={[styles.backdrop, { opacity: backdropOpacity }]}
        />
      </Pressable>

      <Animated.View
        style={[
          styles.sheet,
          {
            width: screenW,
            height: screenH,
            backgroundColor: c.shellBg,
            transform: [{ translateX: slideX }],
          },
        ]}
        {...(isWizard ? {} : pan.panHandlers)}
      >
        <TutorialAnchor
          id="tut-sidebar-panel"
          opts={{ radius: 0 }}
          style={[StyleSheet.absoluteFill, { pointerEvents: 'none' }]}
        >
          <View style={StyleSheet.absoluteFill} pointerEvents="none" />
        </TutorialAnchor>
        <KeyboardAvoidingView
          style={[styles.sheetInner, { backgroundColor: c.shellBg }]}
          // Auth fields and the account rows in the pinned bottom block sit
          // behind the iOS keyboard otherwise.
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          {wizardMounted ? (
            <>
              <ProfilePillBar topInset={Math.max(0, topInset - 4)} />
              <View style={styles.wizardWrap}>
                <PresetWizardShell
                  key={editingProfileId || 'create'}
                  themeMode={themeMode}
                  onCreated={handleWizardCreated}
                  onUpdated={handleWizardUpdated}
                />
              </View>
            </>
          ) : (
            <>
              <ProfilePillBar topInset={Math.max(0, topInset - 4)} />

              {isAuth ? (
                <ScrollView
                  style={styles.scroll}
                  contentContainerStyle={styles.scrollContent}
                  keyboardShouldPersistTaps="handled"
                  bounces
                >
                  <AuthPanel
                    initialTab={authTab}
                    visible={isAuth}
                    onClose={closeAuthPanel}
                  />
                </ScrollView>
              ) : (
                <>
                  <ScrollView
                    style={styles.scroll}
                    contentContainerStyle={styles.scrollContent}
                    keyboardShouldPersistTaps="handled"
                    bounces
                  >
                    <ProfilesSection
                      profiles={profiles}
                      activeProfileId={activeProfileId}
                      onSelectProfile={onSelectProfile}
                      onDeleteProfile={onDeleteProfile}
                      stacked={profilesStacked}
                      onStackedActivate={() => setAccountPanel(null)}
                    />
                  </ScrollView>

                  <View style={[
                    styles.bottom,
                    {
                      paddingBottom: bottomPad,
                      borderTopColor: c.line,
                      backgroundColor: c.shellBg,
                    },
                  ]}
                  >
                    <AccountManageSection
                      expandedPanel={accountPanel}
                      onExpandedPanelChange={setAccountPanel}
                    />
                    <SystemFooter />
                    <TutorialAnchor id="tut-sidebar-help" opts={{ radius: 8 }}>
                      <View style={styles.helpLinks}>
                        <Pressable
                          accessibilityRole="button"
                          onPress={() => {
                            closeSidebar();
                            setTimeout(() => onboarding?.replayTutorial?.(), 320);
                          }}
                          style={({ pressed }) => pressed && { opacity: 0.7 }}
                          hitSlop={6}
                        >
                          <Text style={[styles.helpLink, { color: c.textSub }]}>
                            Revisit tutorial?
                          </Text>
                        </Pressable>
                        <Pressable
                          accessibilityRole="button"
                          onPress={() => setBugReportOpen(true)}
                          style={({ pressed }) => pressed && { opacity: 0.7 }}
                          hitSlop={6}
                        >
                          <Text style={[styles.helpLink, { color: c.textSub }]}>
                            Report a bug
                          </Text>
                        </Pressable>
                      </View>
                    </TutorialAnchor>
                  </View>
                </>
              )}
            </>
          )}
        </KeyboardAvoidingView>
      </Animated.View>

      <BugReportModal
        open={bugReportOpen}
        onClose={() => setBugReportOpen(false)}
        themeMode={themeMode}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFill,
    zIndex: 100,
  },
  backdrop: {
    ...StyleSheet.absoluteFill,
    backgroundColor: '#000',
  },
  sheet: {
    position: 'absolute',
    top: 0,
    left: 0,
  },
  sheetInner: {
    flex: 1,
  },
  wizardWrap: {
    flex: 1,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 14,
    paddingTop: 8,
    paddingBottom: 24,
    gap: 18,
    flexGrow: 1,
  },
  bottom: {
    flexShrink: 0,
    gap: 18,
    paddingHorizontal: 14,
    paddingTop: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  helpLinks: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingBottom: 2,
  },
  helpLink: {
    fontSize: 12,
    fontWeight: '600',
    textDecorationLine: 'underline',
  },
});

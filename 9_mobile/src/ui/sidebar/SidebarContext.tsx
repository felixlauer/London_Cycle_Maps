/**
 * Sidebar open/view state — web SidebarContext (drawer + auth + system prefs).
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { Appearance } from 'react-native';
import {
  loadFavouriteOrder,
  writeFavouriteOrder,
} from '../../lib/prefs';
import {
  type AppearancePref,
  type ThemeMode,
  loadStoredAppearance,
  resolveEffectiveTheme,
  systemPrefersDark,
  writeStoredAppearance,
} from '../../theme/resolveAppearance';
import {
  type UnitsPref,
  loadStoredUnits,
  writeStoredUnits,
} from '../../units';

export type SidebarView = 'sidebar' | 'auth' | 'wizard';
export type AuthTab = 'login' | 'signup' | 'reset';

type SidebarContextValue = {
  open: boolean;
  view: SidebarView;
  authTab: AuthTab;
  editingProfileId: string | null;
  appearance: AppearancePref;
  setAppearance: (pref: AppearancePref) => void;
  units: UnitsPref;
  setUnits: (units: UnitsPref) => void;
  themeMode: ThemeMode;
  /** London outdoor darkness from /night_status — overlay + island CAE (not chrome). */
  isDarkOutside: boolean;
  favouriteOrder: string[];
  setFavouriteOrder: (idsOrUpdater: string[] | ((prev: string[]) => string[])) => void;
  prefsReady: boolean;
  openSidebar: (opts?: { focus?: 'profiles' | null }) => void;
  closeSidebar: () => void;
  toggleSidebar: () => void;
  openAuthPanel: (tab?: AuthTab) => void;
  closeAuthPanel: () => void;
  openWizard: (opts?: { profileId?: string | null }) => void;
  closeWizard: () => void;
};

const SidebarContext = createContext<SidebarContextValue | null>(null);

type ProviderProps = {
  children: React.ReactNode;
  isDarkOutside?: boolean;
};

export function SidebarProvider({
  children,
  isDarkOutside = false,
}: ProviderProps) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<SidebarView>('sidebar');
  const [authTab, setAuthTab] = useState<AuthTab>('login');
  const [editingProfileId, setEditingProfileId] = useState<string | null>(null);
  const [appearance, setAppearanceState] = useState<AppearancePref>('auto');
  const [units, setUnitsState] = useState<UnitsPref>('metric');
  const [systemDark, setSystemDark] = useState(systemPrefersDark);
  const [favouriteOrder, setFavouriteOrderState] = useState<string[]>([]);
  const [prefsReady, setPrefsReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [a, u, fav] = await Promise.all([
        loadStoredAppearance(),
        loadStoredUnits(),
        loadFavouriteOrder(),
      ]);
      if (cancelled) return;
      setAppearanceState(a);
      setUnitsState(u);
      setFavouriteOrderState(fav);
      setPrefsReady(true);
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (appearance !== 'system') return undefined;
    const sub = Appearance.addChangeListener(({ colorScheme }) => {
      setSystemDark(colorScheme === 'dark');
    });
    setSystemDark(systemPrefersDark());
    return () => sub.remove();
  }, [appearance]);

  const themeMode = useMemo((): ThemeMode => {
    if (appearance === 'system') return systemDark ? 'dark' : 'light';
    return resolveEffectiveTheme(appearance, { isDarkOutside });
  }, [appearance, isDarkOutside, systemDark]);

  const setAppearance = useCallback((pref: AppearancePref) => {
    setAppearanceState(pref);
    void writeStoredAppearance(pref);
  }, []);

  const setUnits = useCallback((next: UnitsPref) => {
    setUnitsState(next);
    void writeStoredUnits(next);
  }, []);

  const setFavouriteOrder = useCallback((
    idsOrUpdater: string[] | ((prev: string[]) => string[]),
  ) => {
    setFavouriteOrderState((prev) => {
      const next = typeof idsOrUpdater === 'function' ? idsOrUpdater(prev) : idsOrUpdater;
      void writeFavouriteOrder(next);
      return next;
    });
  }, []);

  const openSidebar = useCallback((_opts: { focus?: 'profiles' | null } = {}) => {
    setOpen(true);
  }, []);

  const closeSidebar = useCallback(() => {
    setOpen(false);
    setView('sidebar');
    setEditingProfileId(null);
  }, []);

  const toggleSidebar = useCallback(() => {
    setOpen((v) => {
      if (v) {
        setView('sidebar');
        setEditingProfileId(null);
      }
      return !v;
    });
  }, []);

  const openAuthPanel = useCallback((tab: AuthTab = 'login') => {
    setAuthTab(tab);
    setOpen(true);
    setView('auth');
  }, []);

  const closeAuthPanel = useCallback(() => {
    setView('sidebar');
  }, []);

  const openWizard = useCallback((opts: { profileId?: string | null } = {}) => {
    setEditingProfileId(opts.profileId || null);
    setOpen(true);
    setView('wizard');
  }, []);

  const closeWizard = useCallback(() => {
    setView('sidebar');
    setEditingProfileId(null);
  }, []);

  const value = useMemo(() => ({
    open,
    view,
    authTab,
    editingProfileId,
    appearance,
    setAppearance,
    units,
    setUnits,
    themeMode,
    isDarkOutside,
    favouriteOrder,
    setFavouriteOrder,
    prefsReady,
    openSidebar,
    closeSidebar,
    toggleSidebar,
    openAuthPanel,
    closeAuthPanel,
    openWizard,
    closeWizard,
  }), [
    open, view, authTab, editingProfileId,
    appearance, setAppearance, units, setUnits, themeMode, isDarkOutside,
    favouriteOrder, setFavouriteOrder, prefsReady,
    openSidebar, closeSidebar, toggleSidebar,
    openAuthPanel, closeAuthPanel, openWizard, closeWizard,
  ]);

  return (
    <SidebarContext.Provider value={value}>
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebar(): SidebarContextValue {
  const ctx = useContext(SidebarContext);
  if (!ctx) throw new Error('useSidebar must be used within SidebarProvider');
  return ctx;
}

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  readStoredAppearance,
  writeStoredAppearance,
  resolveEffectiveTheme,
  systemPrefersDark,
} from '../theme/resolveAppearance';
import { readStoredUnits, writeStoredUnits } from '../units';

const FAV_ORDER_KEY = 'tuned_favourite_order';
export const SIDEBAR_WIDTH_PX = 320;

/** @typedef {'sidebar' | 'auth' | 'wizard'} SidebarView */

function readFavOrder() {
  try {
    const raw = localStorage.getItem(FAV_ORDER_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((id) => typeof id === 'string') : [];
  } catch {
    return [];
  }
}

function writeFavOrder(ids) {
  try {
    localStorage.setItem(FAV_ORDER_KEY, JSON.stringify(ids));
  } catch {
    /* ignore */
  }
}

const SidebarContext = createContext(null);

export function SidebarProvider({
  children,
  isDarkOutside = false,
}) {
  const [open, setOpen] = useState(false);
  const [focus, setFocus] = useState(null);
  /** @type {[SidebarView, Function]} */
  const [view, setView] = useState('sidebar');
  const [authTab, setAuthTab] = useState('login');
  /** Profile id when editing; null when creating. */
  const [editingProfileId, setEditingProfileId] = useState(null);
  const [appearance, setAppearanceState] = useState(readStoredAppearance);
  const [units, setUnitsState] = useState(readStoredUnits);
  const [systemDark, setSystemDark] = useState(systemPrefersDark);
  const [favouriteOrder, setFavouriteOrderState] = useState(readFavOrder);
  const shellRef = useRef(null);
  const profilesSectionRef = useRef(null);

  const themeMode = useMemo(() => {
    if (appearance === 'system') {
      return systemDark ? 'dark' : 'light';
    }
    return resolveEffectiveTheme(appearance, { isDarkOutside });
  }, [appearance, isDarkOutside, systemDark]);

  useEffect(() => {
    if (appearance !== 'system') return undefined;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => setSystemDark(mq.matches);
    onChange();
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, [appearance]);

  const setAppearance = useCallback((pref) => {
    setAppearanceState(pref);
    writeStoredAppearance(pref);
  }, []);

  const setUnits = useCallback((next) => {
    setUnitsState(next);
    writeStoredUnits(next);
  }, []);

  const setFavouriteOrder = useCallback((idsOrUpdater) => {
    setFavouriteOrderState((prev) => {
      const next = typeof idsOrUpdater === 'function' ? idsOrUpdater(prev) : idsOrUpdater;
      writeFavOrder(next);
      return next;
    });
  }, []);

  const openSidebar = useCallback((opts = {}) => {
    setOpen(true);
    if (opts.focus) setFocus(opts.focus);
  }, []);

  const closeSidebar = useCallback(() => {
    setOpen(false);
    setFocus(null);
    setView('sidebar');
    setEditingProfileId(null);
  }, []);

  const toggleSidebar = useCallback(() => {
    setOpen((v) => {
      if (v) {
        setFocus(null);
        setView('sidebar');
        setEditingProfileId(null);
      }
      return !v;
    });
  }, []);

  const openAuthPanel = useCallback((tab = 'login') => {
    setAuthTab(tab);
    setOpen(true);
    setView('auth');
  }, []);

  const closeAuthPanel = useCallback(() => {
    setView('sidebar');
  }, []);

  const openWizard = useCallback((opts = {}) => {
    setEditingProfileId(opts.profileId || null);
    setOpen(true);
    setView('wizard');
  }, []);

  const closeWizard = useCallback(() => {
    setView('sidebar');
    setEditingProfileId(null);
  }, []);

  useEffect(() => {
    if (!open || focus !== 'profiles') return undefined;
    const t = window.setTimeout(() => {
      profilesSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 280);
    return () => window.clearTimeout(t);
  }, [open, focus]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      if (view === 'wizard') {
        closeWizard();
        return;
      }
      if (view === 'auth') {
        closeAuthPanel();
        return;
      }
      closeSidebar();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, view, closeSidebar, closeWizard, closeAuthPanel]);

  const value = useMemo(() => ({
    open,
    focus,
    view,
    authTab,
    editingProfileId,
    appearance,
    setAppearance,
    units,
    setUnits,
    themeMode,
    favouriteOrder,
    setFavouriteOrder,
    openSidebar,
    closeSidebar,
    toggleSidebar,
    openAuthPanel,
    closeAuthPanel,
    openWizard,
    closeWizard,
    shellRef,
    profilesSectionRef,
    sidebarWidth: SIDEBAR_WIDTH_PX,
  }), [
    open, focus, view, authTab, editingProfileId, appearance, setAppearance, units, setUnits, themeMode,
    favouriteOrder, setFavouriteOrder, openSidebar, closeSidebar, toggleSidebar,
    openAuthPanel, closeAuthPanel, openWizard, closeWizard,
  ]);

  return (
    <SidebarContext.Provider value={value}>
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebar() {
  const ctx = useContext(SidebarContext);
  if (!ctx) throw new Error('useSidebar must be used within SidebarProvider');
  return ctx;
}

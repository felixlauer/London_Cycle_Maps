/**
 * Owns the Flag -> picker -> save flow while turn-by-turn is running.
 *
 * The rider is moving, so every decision here is about not costing them
 * attention: the point is written on the first tap, the picker closes itself,
 * there is no cancel, and nothing waits on the network.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native';
import * as Application from 'expo-application';
import * as Haptics from 'expo-haptics';
import * as Network from 'expo-network';
import * as Crypto from 'expo-crypto';

import { RIDE_REPORT_COPY } from '../routing/constants';
import {
  RIDE_REPORT_PERSONAL_ONLY,
  RIDE_REPORT_SIMULATE,
} from '../routing/rideReportFlags';
import { loadDeviceId, peekDeviceId } from '../lib/deviceId';
import type { RideReportCategory } from './rideReportCategories';
import { buildRideReport, type RideReportInput } from './rideReportPayload';
import {
  appendStub,
  loadQueue,
  patchCategory,
  scheduleFlushAfterTap,
} from './rideReportQueue';

/** Long enough to read the four labels without rushing. */
export const PICKER_MS = 10000;
/** A second Flag this soon after a save is a bounce, not a new report. */
const REPEAT_GUARD_MS = 8000;

/** Everything the payload needs that only the screen knows. */
export type RideReportContext = Pick<
  RideReportInput,
  'progress' | 'nav' | 'route' | 'profile' | 'night'
> & {
  fallbackLocation?: [number, number] | null;
  themeMode?: string | null;
};

type Options = {
  /** Lighting gate from /night_status — decides slot 4. */
  isDark: boolean;
  getContext: () => RideReportContext;
  pushAlert: (alert: { type: string; message: string }) => void;
  /** Route around a reported barrier straight away, without awaiting upload. */
  replanAvoiding?: (point: [number, number]) => void;
};

export function useRideReport({
  isDark,
  getContext,
  pushAlert,
  replanAvoiding,
}: Options) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const openEventIdRef = useRef<string | null>(null);
  const openPointRef = useRef<[number, number] | null>(null);
  const openedAtRef = useRef(0);
  const lastCompletedAtRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const remainingRef = useRef(PICKER_MS);
  const heldAtRef = useRef(0);
  const onlineRef = useRef(true);

  useEffect(() => {
    void loadQueue();
    void loadDeviceId();
    Network.getNetworkStateAsync()
      .then((s) => {
        onlineRef.current = Boolean(s.isConnected);
      })
      .catch(() => undefined);
    const sub = Network.addNetworkStateListener(({ isConnected }) => {
      onlineRef.current = Boolean(isConnected);
    });
    return () => sub.remove();
  }, []);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => clearTimer, [clearTimer]);

  const finish = useCallback((message: string) => {
    clearTimer();
    openEventIdRef.current = null;
    lastCompletedAtRef.current = Date.now();
    setPickerOpen(false);
    pushAlert({
      type: 'ride_report',
      // Offline is worth saying: it explains why nothing changes for a while.
      message: onlineRef.current ? message : RIDE_REPORT_COPY.offline,
    });
    scheduleFlushAfterTap();
  }, [clearTimer, pushAlert]);

  /** Timeout keeps the point as `general` — a place still beats nothing. */
  const timeOut = useCallback(() => {
    if (!openEventIdRef.current) return;
    finish(RIDE_REPORT_COPY.noted);
  }, [finish]);

  const startTimer = useCallback((ms: number) => {
    clearTimer();
    remainingRef.current = ms;
    timerRef.current = setTimeout(timeOut, ms);
  }, [clearTimer, timeOut]);

  const onTrigger = useCallback(() => {
    if (pickerOpen) return;
    if (Date.now() - lastCompletedAtRef.current < REPEAT_GUARD_MS) return;

    const ctx = getContext();
    const envelope = buildRideReport({
      clientEventId: Crypto.randomUUID(),
      category: 'general',
      deviceId: peekDeviceId(),
      personalOnly: RIDE_REPORT_PERSONAL_ONLY,
      simulate: RIDE_REPORT_SIMULATE,
      progress: ctx.progress,
      fallbackLocation: ctx.fallbackLocation,
      nav: ctx.nav,
      route: ctx.route,
      profile: ctx.profile,
      night: ctx.night,
      device: {
        platform: Platform.OS,
        osVersion: Platform.Version,
        appVersion: Application.nativeApplicationVersion,
        themeMode: ctx.themeMode ?? null,
        netState: onlineRef.current ? 'online' : 'offline',
      },
      timing: { tappedAtMs: Date.now(), elapsedMsIntoPicker: 0 },
    });

    if (!envelope) {
      pushAlert({ type: 'warning', message: 'No position yet — try again shortly' });
      return;
    }

    // Disk first: if the app dies inside the picker, the point survives.
    appendStub(envelope);
    openEventIdRef.current = envelope.client_event_id;
    // The place as it was at the Flag press, not wherever the rider has coasted
    // to by the time they pick a category.
    openPointRef.current = [envelope.lat, envelope.lon];
    openedAtRef.current = Date.now();
    heldAtRef.current = 0;
    setPickerOpen(true);
    startTimer(PICKER_MS);
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => undefined);
  }, [pickerOpen, getContext, pushAlert, startTimer]);

  const onPick = useCallback((category: RideReportCategory) => {
    const id = openEventIdRef.current;
    if (!id) return;
    patchCategory(id, category.id, Date.now() - openedAtRef.current);
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
      .catch(() => undefined);

    // A gate is shut now, so the line has to change now — the rider cannot wait
    // for the report to reach the server and come back as a global overlay.
    if (category.id === 'impassable' && replanAvoiding) {
      const at = openPointRef.current;
      if (at) replanAvoiding(at);
    }
    finish(RIDE_REPORT_COPY.saved);
  }, [finish, replanAvoiding]);

  /** A finger on a circle pauses the countdown — never punish hesitation. */
  const onHoldChange = useCallback((held: boolean) => {
    if (!openEventIdRef.current) return;
    if (held) {
      heldAtRef.current = Date.now();
      const elapsed = heldAtRef.current - openedAtRef.current;
      remainingRef.current = Math.max(0, PICKER_MS - elapsed);
      clearTimer();
      return;
    }
    if (!heldAtRef.current) return;
    // Shift the origin forward by the hold so remaining stays truthful.
    openedAtRef.current += Date.now() - heldAtRef.current;
    heldAtRef.current = 0;
    startTimer(remainingRef.current);
  }, [clearTimer, startTimer]);

  /** Nav ending mid-picker: keep the point, drop the UI. */
  const cancelPicker = useCallback(() => {
    if (!openEventIdRef.current) return;
    clearTimer();
    openEventIdRef.current = null;
    setPickerOpen(false);
  }, [clearTimer]);

  return {
    pickerOpen,
    isDark,
    onTrigger,
    onPick,
    onHoldChange,
    cancelPicker,
    /** Debounce on the trigger circle right after a save. */
    reportDisabled: pickerOpen,
  };
}

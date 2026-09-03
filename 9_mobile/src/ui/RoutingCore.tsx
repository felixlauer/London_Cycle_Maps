import { useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import { Plus } from 'lucide-react-native';
import { useSafeAreaTop } from '../lib/safeArea';
import { avatarPaletteForEmail, initialsFromEmail } from '../lib/avatar';
import type { LatLon } from '../lib/coords';
import {
  BLOCKED,
  MAX_VIAS,
  type BikeTypeId,
  type ProfileRow,
  type ViaPoint,
} from '../routing/constants';
import { space } from '../theme/tokens';
import { useChrome } from '../theme/useChrome';
import {
  DepartAtPanel,
  DepartAtTrigger,
  useDepartAtControl,
  type DepartMode,
} from './DepartAtControl';
import { GetRoutePill } from './GetRoutePill';
import { ModeBikeSantanderRow } from './ModeBikeSantanderRow';
import {
  WaypointFields,
  type PickTarget,
  type WaypointChange,
} from './WaypointFields';
import { TutorialAnchor } from '../onboarding/tutorial/TutorialAnchor';

type UserLike = { email?: string | null; display_name?: string | null } | null;

type Props = {
  user: UserLike;
  authLoading?: boolean;
  onAvatarPress?: () => void;
  onSignOut: () => void;
  profiles: ProfileRow[];
  activeProfileId: string | null;
  onSelectProfile: (id: string) => void;
  favouriteOrder?: string[];
  onEditFavourites?: () => void;
  bikeType: BikeTypeId;
  onSelectBike: (id: BikeTypeId) => void;
  santanderMode: boolean;
  onSantanderChange: (on: boolean) => void;
  start: LatLon | null;
  end: LatLon | null;
  startLabel: string;
  endLabel: string;
  vias: ViaPoint[];
  onChangeWaypoints: (next: WaypointChange) => void;
  onAddVia: () => void;
  onRemoveVia: (i: number) => void;
  onFlyTo?: (coord: LatLon) => void;
  onMapPickTargetChange: (t: PickTarget) => void;
  departMode: DepartMode;
  departAtIso: string | null;
  onDepartChange: (next: { mode: DepartMode; departAtIso: string | null }) => void;
  onGetRoute: () => void;
  isCalculating: boolean;
  onBlocked?: (msg: string) => void;
};

/**
 * Full mobile routing core — layout twin of web RoutingCoreZone (≤767px).
 */
export function RoutingCore({
  user,
  authLoading,
  onAvatarPress,
  onSignOut,
  profiles,
  activeProfileId,
  onSelectProfile,
  favouriteOrder,
  onEditFavourites,
  bikeType,
  onSelectBike,
  santanderMode,
  onSantanderChange,
  start,
  end,
  startLabel,
  endLabel,
  vias,
  onChangeWaypoints,
  onAddVia,
  onRemoveVia,
  onFlyTo,
  onMapPickTargetChange,
  departMode,
  departAtIso,
  onDepartChange,
  onGetRoute,
  isCalculating,
  onBlocked,
}: Props) {
  const { c, themeMode } = useChrome();
  const topInset = useSafeAreaTop();
  const shadowOpacity = themeMode === 'light' ? 0.08 : 0.45;
  const [viasCollapsed, setViasCollapsed] = useState(false);

  const hasVias = (vias || []).length > 0;
  const santanderDisabled = hasVias;
  const departDisabled = santanderMode;
  const atMaxVias = (vias || []).length >= MAX_VIAS;
  const addStopBlocked = santanderMode || atMaxVias;
  const canGetRoute = Boolean(start && end) && !(vias || []).some((v) => !v.coord);

  const depart = useDepartAtControl({
    mode: departMode,
    departAtIso,
    onChange: onDepartChange,
    disabled: departDisabled,
    onBlocked,
  });

  const initials = initialsFromEmail(user?.email);
  const palette = avatarPaletteForEmail(user?.email);

  const handleAvatar = () => {
    if (onAvatarPress) {
      onAvatarPress();
      return;
    }
    Alert.alert(user?.email || 'Account', undefined, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Sign out', style: 'destructive', onPress: () => onSignOut() },
    ]);
  };

  const handleSantander = () => {
    if (santanderDisabled) {
      onBlocked?.(BLOCKED.santanderNeedsNoStops);
      return;
    }
    onSantanderChange(!santanderMode);
  };

  const handleAddStop = () => {
    if (santanderMode) {
      onBlocked?.(BLOCKED.addStopNeedsNoSantander);
      return;
    }
    if (atMaxVias) {
      onBlocked?.(BLOCKED.addStopMax);
      return;
    }
    setViasCollapsed(false);
    onAddVia();
  };

  const handleGetRoute = () => {
    if (isCalculating) {
      onBlocked?.(BLOCKED.getRouteBusy);
      return;
    }
    if (!start) {
      onBlocked?.(BLOCKED.getRouteNeedsStart);
      return;
    }
    if (!end) {
      onBlocked?.(BLOCKED.getRouteNeedsEnd);
      return;
    }
    if ((vias || []).some((v) => !v.coord)) {
      onBlocked?.(BLOCKED.getRouteNeedsStops);
      return;
    }
    depart.commitDraft();
    depart.collapse();
    if (hasVias) setViasCollapsed(true);
    onGetRoute();
  };

  return (
    <View style={[styles.wrap, { paddingTop: topInset }]} collapsable={false}>
      <View style={[styles.panel, { backgroundColor: c.shellBg, borderColor: c.shellBorder, shadowOpacity }]}>
        <View style={styles.topRow}>
          <ModeBikeSantanderRow
            profiles={profiles}
            activeProfileId={activeProfileId}
            onSelectProfile={onSelectProfile}
            favouriteOrder={favouriteOrder}
            onEditFavourites={onEditFavourites}
            bikeType={bikeType}
            onSelectBike={onSelectBike}
            santanderMode={santanderMode}
            onSantanderPress={handleSantander}
            santanderDisabled={santanderDisabled}
            onBlocked={onBlocked}
          />
          <TutorialAnchor id="tut-mobile-avatar" opts={{ capsule: true, radius: 999 }}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Open account"
              onPress={handleAvatar}
              style={({ pressed }) => [
                styles.avatar,
                { borderColor: c.line, backgroundColor: c.shellBg },
                pressed && styles.pressed,
              ]}
            >
              <View
                style={[
                  styles.avatarFace,
                  !user && styles.avatarGuest,
                  authLoading && { backgroundColor: c.surface },
                  user ? { backgroundColor: palette.from } : null,
                ]}
              >
                {!authLoading && (
                  <Text
                    style={[
                      styles.avatarText,
                      !user && styles.avatarGuestText,
                      user ? { color: palette.color } : null,
                    ]}
                    numberOfLines={1}
                  >
                    {user ? initials : 'Guest'}
                  </Text>
                )}
              </View>
            </Pressable>
          </TutorialAnchor>
        </View>

        <View style={styles.routeStack}>
          <View style={styles.wpWithPill}>
            <TutorialAnchor id="tut-waypoint-card" opts={{ radius: 14 }} style={styles.wpFields}>
              <WaypointFields
                start={start}
                end={end}
                startLabel={startLabel}
                endLabel={endLabel}
                vias={vias}
                onChangeWaypoints={(next) => {
                  setViasCollapsed(false);
                  onChangeWaypoints(next);
                }}
                onRemoveVia={(i) => {
                  setViasCollapsed(false);
                  onRemoveVia(i);
                }}
                onFlyTo={onFlyTo}
                onMapPickTargetChange={onMapPickTargetChange}
                viasCollapsed={viasCollapsed}
                onExpandVias={() => setViasCollapsed(false)}
              />
            </TutorialAnchor>
            <View style={styles.wpSide}>
              <GetRoutePill
                disabled={!canGetRoute}
                busy={isCalculating}
                onPress={handleGetRoute}
              />
            </View>
          </View>

          <View style={[styles.subrow, depart.disabled && styles.subrowDepartDisabled]}>
            <DepartAtTrigger
              linkLabel={depart.linkLabel}
              open={depart.open}
              disabled={depart.disabled}
              onToggle={depart.toggleOpen}
            />
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: addStopBlocked }}
              onPress={handleAddStop}
              style={({ pressed }) => [
                styles.addStop,
                addStopBlocked && styles.addStopDisabled,
                pressed && !addStopBlocked && { opacity: 0.75 },
              ]}
            >
              <Plus size={14} strokeWidth={2.2} color={c.textSub} />
              <Text style={[styles.addStopText, { color: c.textSub }]}>Add stop</Text>
            </Pressable>
          </View>

          {depart.open && !depart.disabled && <DepartAtPanel {...depart} />}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { width: '100%' },
  panel: {
    width: '100%',
    padding: space.panelPad,
    gap: space.gap,
    borderRadius: 16,
    borderWidth: 1,
    shadowColor: '#000',
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 8,
    overflow: 'visible',
    zIndex: 20,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minWidth: 0,
    zIndex: 30,
  },
  avatar: {
    width: 40,
    height: 40,
    padding: 3,
    borderRadius: 999,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  avatarFace: {
    width: '100%',
    height: '100%',
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FF0061',
  },
  avatarGuest: { backgroundColor: '#7768AE' },
  avatarText: { fontSize: 11.5, fontWeight: '700', color: '#fff' },
  avatarGuestText: { fontSize: 7.5, fontWeight: '700' },
  pressed: { transform: [{ scale: 0.97 }] },
  routeStack: {
    flexDirection: 'column',
    gap: space.gap,
    minWidth: 0,
    zIndex: 10,
  },
  wpWithPill: {
    flexDirection: 'row',
    alignItems: 'stretch',
    gap: 8,
    minWidth: 0,
    zIndex: 15,
  },
  wpFields: { flex: 1, minWidth: 0, zIndex: 15 },
  wpSide: {
    flexShrink: 0,
    alignSelf: 'stretch',
    width: 40,
  },
  subrow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
    minHeight: 24,
  },
  subrowDepartDisabled: {},
  addStop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 4,
    paddingHorizontal: 5,
    borderRadius: 6,
    marginLeft: 'auto',
  },
  addStopDisabled: { opacity: 0.45 },
  addStopText: {
    fontSize: 12.5,
    fontWeight: '600',
  },
});

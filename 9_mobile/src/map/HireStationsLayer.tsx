/**
 * Santander hire stations — Android-safe rebuild.
 *
 * Compact expand: ShapeSource / CircleLayer only (same as traffic chips).
 * MarkerViews are glued to the map. Expanded confirm is drawn inside the
 * MarkerView so it never lags behind pan/zoom; an invisible chrome Pressable
 * mirrors the hit target for Android when MapView steals in-map touches.
 */
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { CircleLayer, MarkerView, ShapeSource } from '@rnmapbox/maps';
import { Bike, Footprints } from 'lucide-react-native';
import type { HireNeed, HireStation } from '../api/santander';
import { brand, type ChromeTokens } from '../theme/tokens';
import { useChrome } from '../theme/useChrome';

const BEAK_ALONG_COMPACT = 32;
const BEAK_ALONG_EXPANDED = 36;
const BADGE = 28;
const CARD_PAD_V = 5;
const CARD_PAD_L = 10;
const CARD_PAD_R = CARD_PAD_V;
const COMPACT_GAP = 6;
const COMPACT_H = BADGE + CARD_PAD_V * 2;
const BEAK_H = 11;
const COMPACT_W_EST = 96;
const EXPANDED_W_EST = 220;
const EXPANDED_H_EST = 132;
/** Approx confirm control size inside the expanded card. */
const CONFIRM_W = 92;
const CONFIRM_H = 40;

type CardPalette = {
  text: string;
  textSub: string;
  muted: string;
  line: string;
  surface: string;
  confirmBg: string;
};

function cardPalette(themeMode: 'light' | 'dark', c: ChromeTokens): CardPalette {
  if (themeMode === 'dark') {
    return {
      text: c.text,
      textSub: c.textSub,
      muted: c.textSub,
      line: c.line,
      surface: c.shellBg,
      confirmBg: c.surface,
    };
  }
  return {
    text: '#3f3f46',
    textSub: '#71717a',
    muted: '#a1a1aa',
    line: '#e4e4e7',
    surface: '#fff',
    confirmBg: '#f4f4f5',
  };
}

type LayerProps = {
  stations: HireStation[];
  hireStep: 'pickup' | 'dropoff' | 'done' | string;
  hireNeed: HireNeed;
  expandedId: string | null;
  confirmLabel?: string;
  pickupStation?: HireStation | null;
  dropoffStation?: HireStation | null;
  onExpand: (station: HireStation) => void;
  onConfirm?: (station: HireStation) => void;
};

type HitChromeProps = {
  mapRef: { current: { getPointInView?: (c: number[]) => Promise<number[] | { x: number; y: number } | null> } | null };
  station: HireStation;
  cameraEpoch: number;
  confirmLabel: string;
  onCollapse: () => void;
  onConfirm: () => void;
};

function DonePin() {
  return (
    <View style={styles.donePin} collapsable={false} pointerEvents="none">
      <Bike size={14} strokeWidth={2.4} color={brand.fuchsia} />
    </View>
  );
}

function CompactCard({
  station,
  hireNeed,
  palette,
}: {
  station: HireStation;
  hireNeed: HireNeed;
  palette: CardPalette;
}) {
  const st = palette;
  const unavailable = hireNeed === 'docks'
    ? !(Number(station.nb_empty) > 0)
    : !(Number(station.nb_bikes) > 0);

  return (
    <View style={styles.pinWrap} collapsable={false} pointerEvents="none">
      <View
        style={[styles.card, styles.cardCompact, { backgroundColor: st.surface }]}
        collapsable={false}
        pointerEvents="none"
      >
        <View style={styles.compactRow} pointerEvents="none">
          <Text
            style={[styles.counts, { color: unavailable ? st.muted : st.text }]}
            numberOfLines={1}
          >
            {`${station.nb_bikes ?? 0}`}
            <Text style={{ color: st.muted, fontWeight: '500' }}>{' | '}</Text>
            {`${station.nb_docks ?? 0}`}
          </Text>
          <View style={[styles.badge, unavailable && { backgroundColor: st.muted }]}>
            <Bike size={14} strokeWidth={2.25} color="#fff" />
          </View>
        </View>
      </View>
      <View style={styles.beakTrack} pointerEvents="none">
        <View
          style={[
            styles.beak,
            { marginLeft: BEAK_ALONG_COMPACT - 12, borderTopColor: st.surface },
          ]}
        />
      </View>
    </View>
  );
}

/** Expanded bubble — confirm is part of the MarkerView so it stays map-locked. */
function ExpandedCard({
  station,
  hireNeed,
  palette,
  confirmLabel,
  onConfirm,
}: {
  station: HireStation;
  hireNeed: HireNeed;
  palette: CardPalette;
  confirmLabel: string;
  onConfirm?: (station: HireStation) => void;
}) {
  const st = palette;
  const unavailable = hireNeed === 'docks'
    ? !(Number(station.nb_empty) > 0)
    : !(Number(station.nb_bikes) > 0);
  const walkMin = Math.max(
    1,
    Math.round(Number(station.walk_duration_min ?? station.walk_estimate_min ?? 1)),
  );
  const walkLabel = station.walk_duration_min != null ? 'walk' : 'estimated';

  return (
    <View style={styles.pinWrap} collapsable={false} pointerEvents="box-none">
      <View
        style={[
          styles.card,
          styles.cardExpanded,
          styles.cardExpandedRaise,
          { backgroundColor: st.surface },
        ]}
        collapsable={false}
        pointerEvents="box-none"
      >
        <View style={styles.top} pointerEvents="none">
          <View style={styles.breakdown}>
            <View style={styles.bd}>
              <Text style={[styles.bdNum, { color: st.text }]} numberOfLines={1}>
                {station.nb_standard ?? 0}
              </Text>
              <Text style={[styles.bdLabel, { color: st.textSub }]} numberOfLines={1}>
                regular
              </Text>
            </View>
            <View style={[styles.bd, styles.bdBorder, { borderLeftColor: st.line }]}>
              <Text style={[styles.bdNum, { color: st.text }]} numberOfLines={1}>
                {station.nb_ebikes ?? 0}
              </Text>
              <Text style={[styles.bdLabel, { color: st.textSub }]} numberOfLines={1}>
                electric
              </Text>
            </View>
            <View style={[styles.bd, styles.bdBorder, { borderLeftColor: st.line }]}>
              <Text style={[styles.bdNum, { color: st.muted }]} numberOfLines={1}>
                {station.nb_empty ?? 0}
              </Text>
              <Text style={[styles.bdLabel, { color: st.textSub }]} numberOfLines={1}>
                empty
              </Text>
            </View>
          </View>
          <View style={[styles.badgeLg, unavailable && { backgroundColor: st.muted }]}>
            <Bike size={18} strokeWidth={2.25} color="#fff" />
          </View>
        </View>

        <View style={styles.walkRow} pointerEvents="box-none">
          <View style={styles.walkHit} pointerEvents="none">
            <View style={styles.walkIcon}>
              <Footprints size={28} strokeWidth={2} color={st.text} />
            </View>
            <View style={styles.walkText}>
              <Text style={[styles.walkStrong, { color: st.text }]} numberOfLines={1}>
                {walkMin} min
              </Text>
              <Text style={[styles.walkSub, { color: st.textSub }]} numberOfLines={1}>
                {walkLabel}
              </Text>
            </View>
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={confirmLabel}
            onPress={() => onConfirm?.(station)}
            hitSlop={{ top: 10, bottom: 10, left: 8, right: 8 }}
            style={({ pressed }) => [
              styles.confirm,
              {
                backgroundColor: st.confirmBg,
                borderColor: st.line,
                opacity: pressed ? 0.88 : 1,
              },
            ]}
          >
            <Text style={[styles.confirmText, { color: st.text }]} numberOfLines={1}>
              {confirmLabel}
            </Text>
          </Pressable>
        </View>
      </View>
      <View style={styles.beakTrack} pointerEvents="none">
        <View
          style={[
            styles.beak,
            { marginLeft: BEAK_ALONG_EXPANDED - 12, borderTopColor: st.surface },
          ]}
        />
      </View>
    </View>
  );
}

function StationHitSource({
  stations,
  skipIds,
  onPress,
}: {
  stations: HireStation[];
  skipIds: Set<string>;
  onPress: (station: HireStation) => void;
}) {
  const byId = useMemo(() => {
    const map = new Map<string, HireStation>();
    (stations || []).forEach((s) => {
      if (s?.id != null) map.set(String(s.id), s);
    });
    return map;
  }, [stations]);

  const fc = useMemo(() => {
    const features: GeoJSON.Feature[] = [];
    (stations || []).forEach((s) => {
      if (!Number.isFinite(s.lat) || !Number.isFinite(s.lon)) return;
      const id = String(s.id);
      if (skipIds.has(id)) return;
      features.push({
        type: 'Feature',
        properties: { id },
        geometry: { type: 'Point', coordinates: [s.lon, s.lat] },
      });
    });
    return { type: 'FeatureCollection' as const, features };
  }, [stations, skipIds]);

  if (!fc.features.length) return null;

  return (
    <ShapeSource
      id="hire-station-hits"
      shape={fc}
      hitbox={{ width: 88, height: 88 }}
      onPress={(event) => {
        const id = String(
          (event.features?.[0]?.properties as { id?: string } | null)?.id || '',
        );
        const station = byId.get(id);
        if (station) onPress(station);
      }}
    >
      <CircleLayer
        id="hire-station-hits-circle"
        style={{
          circleRadius: 44,
          circleColor: '#000000',
          circleOpacity: 0,
          circlePitchAlignment: 'viewport',
          circlePitchScale: 'viewport',
        }}
      />
    </ShapeSource>
  );
}

/**
 * Invisible chrome hit fallback above MapView (Android MapView steals in-map
 * Pressables). Confirm *visual* lives in the MarkerView — this only catches taps.
 */
export function HireExpandedHitChrome({
  mapRef,
  station,
  cameraEpoch,
  confirmLabel,
  onCollapse,
  onConfirm,
}: HitChromeProps) {
  const wrapRef = useRef<View>(null);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      const map = mapRef.current;
      if (!map?.getPointInView) return;
      try {
        const point = await map.getPointInView([station.lon, station.lat]);
        if (cancelled || !point) return;
        let x = 0;
        let y = 0;
        if (Array.isArray(point) && point.length >= 2) {
          x = Number(point[0]);
          y = Number(point[1]);
        } else {
          const obj = point as { x?: number; y?: number };
          x = Number(obj.x);
          y = Number(obj.y);
        }
        if (!Number.isFinite(x) || !Number.isFinite(y)) return;
        wrapRef.current?.setNativeProps({
          style: {
            left: x - BEAK_ALONG_EXPANDED,
            top: y - EXPANDED_H_EST,
            width: EXPANDED_W_EST,
            height: EXPANDED_H_EST,
          },
        });
      } catch {
        /* ignore */
      }
    };
    void run();
    return () => { cancelled = true; };
  }, [mapRef, station, cameraEpoch]);

  return (
    <View
      ref={wrapRef}
      collapsable={false}
      pointerEvents="box-none"
      style={[styles.hitChrome, { left: -9999, top: -9999 }]}
    >
      <Pressable
        accessibilityLabel="Collapse station"
        onPress={onCollapse}
        style={styles.hitCollapse}
        hitSlop={4}
      />
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={confirmLabel}
        onPress={onConfirm}
        hitSlop={{ top: 12, bottom: 12, left: 10, right: 10 }}
        style={styles.hitConfirmInvisible}
      />
    </View>
  );
}

export function HireStationsLayer({
  stations,
  hireStep,
  hireNeed,
  expandedId,
  confirmLabel = 'Confirm',
  pickupStation,
  dropoffStation,
  onExpand,
  onConfirm,
}: LayerProps) {
  const { themeMode, c } = useChrome();
  const palette = useMemo(() => cardPalette(themeMode, c), [themeMode, c]);
  const lastHitAt = useRef(0);

  const lockedPickup = hireStep === 'dropoff' && pickupStation ? pickupStation : null;

  const skipIds = useMemo(() => {
    const set = new Set<string>();
    if (expandedId != null) set.add(String(expandedId));
    if (lockedPickup?.id != null) set.add(String(lockedPickup.id));
    return set;
  }, [expandedId, lockedPickup?.id]);

  const hitStations = useMemo(
    () => (stations || []).filter((s) => Number.isFinite(s.lat) && Number.isFinite(s.lon)),
    [stations],
  );

  const handleHit = useCallback((s: HireStation) => {
    const now = Date.now();
    if (now - lastHitAt.current < 280) return;
    lastHitAt.current = now;
    onExpand(s);
  }, [onExpand]);

  if (hireStep === 'done') {
    const pins = [pickupStation, dropoffStation].filter(Boolean) as HireStation[];
    return (
      <>
        {pins.map((s) => (
          <MarkerView
            key={`done-${s.id}`}
            coordinate={[s.lon, s.lat]}
            anchor={{ x: 0.5, y: 0.5 }}
            allowOverlap
            allowOverlapWithPuck
            pointerEvents="none"
          >
            <DonePin />
          </MarkerView>
        ))}
      </>
    );
  }

  if (hireStep !== 'pickup' && hireStep !== 'dropoff') return null;

  const list = (stations || []).filter(
    (s) => Number.isFinite(s.lat) && Number.isFinite(s.lon),
  );
  const expanded = expandedId != null
    ? list.find((s) => String(s.id) === String(expandedId)) || null
    : null;
  const compactOnly = list.filter((s) => String(s.id) !== String(expandedId));

  return (
    <>
      <StationHitSource
        stations={hitStations}
        skipIds={skipIds}
        onPress={handleHit}
      />

      {lockedPickup
        && Number.isFinite(lockedPickup.lat)
        && Number.isFinite(lockedPickup.lon)
        && String(lockedPickup.id) !== String(expandedId) ? (
          <MarkerView
            key={`locked-${lockedPickup.id}`}
            coordinate={[lockedPickup.lon, lockedPickup.lat]}
            anchor={{
              x: Math.min(1, Math.max(0, BEAK_ALONG_COMPACT / COMPACT_W_EST)),
              y: 1,
            }}
            allowOverlap
            allowOverlapWithPuck
            pointerEvents="none"
          >
            <CompactCard station={lockedPickup} hireNeed="bikes" palette={palette} />
          </MarkerView>
        ) : null}

      {/* Compact first so the expanded MarkerView paints / selects on top. */}
      {compactOnly.map((s) => {
        if (lockedPickup && String(s.id) === String(lockedPickup.id)) return null;
        return (
          <MarkerView
            key={`hire-${s.id}`}
            coordinate={[s.lon, s.lat]}
            anchor={{
              x: Math.min(1, Math.max(0, BEAK_ALONG_COMPACT / COMPACT_W_EST)),
              y: 1,
            }}
            allowOverlap
            allowOverlapWithPuck
            pointerEvents="none"
          >
            <CompactCard station={s} hireNeed={hireNeed} palette={palette} />
          </MarkerView>
        );
      })}

      {expanded ? (
        <MarkerView
          key={`hire-expanded-${expanded.id}`}
          coordinate={[expanded.lon, expanded.lat]}
          anchor={{
            x: Math.min(1, Math.max(0, BEAK_ALONG_EXPANDED / EXPANDED_W_EST)),
            y: 1,
          }}
          allowOverlap
          allowOverlapWithPuck
          isSelected
          pointerEvents="box-none"
        >
          <ExpandedCard
            station={expanded}
            hireNeed={hireNeed}
            palette={palette}
            confirmLabel={confirmLabel}
            onConfirm={onConfirm}
          />
        </MarkerView>
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  hitChrome: {
    position: 'absolute',
    zIndex: 35,
    elevation: 35,
  },
  hitCollapse: {
    position: 'absolute',
    left: 0,
    top: 0,
    right: CONFIRM_W + 10,
    bottom: BEAK_H,
  },
  hitConfirmInvisible: {
    position: 'absolute',
    right: 8,
    bottom: BEAK_H + 10,
    width: CONFIRM_W,
    minHeight: CONFIRM_H,
    // Invisible — visual button is map-locked in MarkerView.
    opacity: 0,
    zIndex: 2,
  },
  donePin: {
    width: 28,
    height: 28,
    borderRadius: 999,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#101828',
    shadowOpacity: 0.22,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
  },
  pinWrap: {
    alignItems: 'flex-start',
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    borderRadius: 999,
    paddingTop: CARD_PAD_V,
    paddingBottom: CARD_PAD_V,
    paddingLeft: CARD_PAD_L,
    paddingRight: CARD_PAD_R,
    shadowColor: '#101828',
    shadowOpacity: 0.18,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 5,
  },
  cardCompact: {
    height: COMPACT_H,
    paddingTop: 0,
    paddingBottom: 0,
  },
  cardExpanded: {
    flexDirection: 'column',
    alignItems: 'stretch',
    gap: 12,
    paddingTop: 12,
    paddingBottom: 12,
    paddingLeft: 14,
    paddingRight: 12,
    borderRadius: 16,
    minWidth: 210,
  },
  cardExpandedRaise: {
    elevation: 12,
    zIndex: 20,
    shadowOpacity: 0.28,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
  },
  beakTrack: {
    height: BEAK_H,
    alignSelf: 'stretch',
  },
  beak: {
    width: 0,
    height: 0,
    borderStyle: 'solid',
    borderLeftWidth: 12,
    borderRightWidth: 12,
    borderTopWidth: 11,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
  },
  compactRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: COMPACT_GAP,
    height: COMPACT_H,
  },
  counts: {
    fontSize: 13.5,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
    letterSpacing: 0.1,
  },
  top: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  breakdown: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    flexGrow: 1,
    flexShrink: 1,
  },
  bd: {
    alignItems: 'center',
    width: 48,
  },
  bdBorder: {
    borderLeftWidth: StyleSheet.hairlineWidth,
  },
  bdNum: {
    fontSize: 18,
    fontWeight: '700',
    lineHeight: 20,
    fontVariant: ['tabular-nums'],
  },
  bdLabel: {
    fontSize: 10,
    fontWeight: '500',
    marginTop: 3,
  },
  badge: {
    width: BADGE,
    height: BADGE,
    borderRadius: 999,
    backgroundColor: brand.fuchsia,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  badgeLg: {
    width: 36,
    height: 36,
    borderRadius: 999,
    backgroundColor: brand.fuchsia,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  walkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingTop: 2,
  },
  walkHit: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minWidth: 0,
  },
  walkIcon: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  walkText: {
    flexShrink: 1,
    minWidth: 0,
    justifyContent: 'center',
  },
  walkStrong: {
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 16,
  },
  walkSub: {
    fontSize: 11,
    fontWeight: '500',
    lineHeight: 13,
    marginTop: 1,
  },
  confirm: {
    flexShrink: 0,
    maxWidth: 102,
    minWidth: 84,
    minHeight: CONFIRM_H,
    paddingVertical: 10,
    paddingHorizontal: 10,
    borderRadius: 9,
    borderWidth: StyleSheet.hairlineWidth,
    justifyContent: 'center',
    alignItems: 'center',
  },
  confirmText: {
    fontSize: 12,
    fontWeight: '600',
  },
});

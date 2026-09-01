import { useMemo, useRef, useState, type RefObject } from 'react';
import {
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
  type LayoutRectangle,
} from 'react-native';
import {
  Bike,
  ChevronDown,
  Package,
  Road,
  Shield,
  Trees,
  Zap,
} from 'lucide-react-native';
import {
  BIKE_OPTIONS,
  PRESET_META,
  PRESET_ORDER,
  SANTANDER_BIKE_OPTIONS,
  buildFavouriteSlots,
  type BikeTypeId,
  type ProfileRow,
} from '../routing/constants';
import { TutorialAnchor } from '../onboarding/tutorial/TutorialAnchor';
import { brand, space } from '../theme/tokens';
import { useChrome } from '../theme/useChrome';

const ICONS: Record<string, typeof Bike> = {
  Shield,
  Zap,
  Trees,
  Bike,
  Package,
  Road,
};

type MenuKind = 'mode' | 'bike' | null;

type Anchor = LayoutRectangle & { pageX: number; pageY: number };

type Props = {
  profiles: ProfileRow[];
  activeProfileId: string | null;
  onSelectProfile: (id: string) => void;
  favouriteOrder?: string[];
  onEditFavourites?: () => void;
  bikeType: BikeTypeId;
  onSelectBike: (id: BikeTypeId) => void;
  santanderMode: boolean;
  onSantanderPress: () => void;
  santanderDisabled?: boolean;
  onBlocked?: (msg: string) => void;
};

function OptIcon({ name, size = 15 }: { name?: string; size?: number }) {
  const { c } = useChrome();
  const Comp = (name && ICONS[name]) || Bike;
  return <Comp size={size} strokeWidth={2} color={c.icon} />;
}

/**
 * Mode | Bike | Santander — web ModeBikeSantanderRow.
 * Menus: absolute under trigger, maxWidth 220, compact (web .rc-menu).
 */
export function ModeBikeSantanderRow({
  profiles,
  activeProfileId,
  onSelectProfile,
  favouriteOrder,
  onEditFavourites,
  bikeType,
  onSelectBike,
  santanderMode,
  onSantanderPress,
  santanderDisabled,
  onBlocked,
}: Props) {
  const { c, themeMode } = useChrome();
  const menuShadowOpacity = themeMode === 'light' ? 0.08 : 0.28;
  const [menu, setMenu] = useState<MenuKind>(null);
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const modeRef = useRef<View>(null);
  const bikeRef = useRef<View>(null);

  const favourites = useMemo(
    () => buildFavouriteSlots(profiles, favouriteOrder || null),
    [profiles, favouriteOrder],
  );
  const activeProfile = profiles.find((p) => p.id === activeProfileId);
  const presetMeta = activeProfileId ? PRESET_META[activeProfileId] : undefined;
  const favSlot = favourites.find((f) => f.id === activeProfileId);
  const modeLabel = presetMeta?.label || activeProfile?.name || 'Mode';

  const bikeOpts = santanderMode ? SANTANDER_BIKE_OPTIONS : BIKE_OPTIONS;
  const activeBike =
    bikeOpts.find((o) => o.id === bikeType) || bikeOpts[0];

  const openMenu = (kind: MenuKind, ref: RefObject<View | null>) => {
    const next = menu === kind ? null : kind;
    if (!next) {
      setMenu(null);
      setAnchor(null);
      return;
    }
    ref.current?.measureInWindow((x, y, width, height) => {
      setAnchor({ x: 0, y: 0, width, height, pageX: x, pageY: y });
      setMenu(next);
    });
  };

  const close = () => {
    setMenu(null);
    setAnchor(null);
  };

  const menuWidth = Math.min(220, Math.max(anchor?.width || 140, 140));

  return (
    <View style={styles.quick}>
      <View style={styles.slot} ref={modeRef} collapsable={false}>
        <TutorialAnchor id="tut-profile-pill" opts={{ capsule: true }}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Riding mode"
            onPress={() => openMenu('mode', modeRef)}
            style={({ pressed }) => [
              styles.pill,
              { borderColor: c.line, backgroundColor: c.surface },
              pressed && styles.pressed,
              menu === 'mode' && { backgroundColor: c.surfaceHover },
            ]}
          >
            <View style={styles.lead}>
              {presetMeta ? (
                <OptIcon name={presetMeta.Icon} />
              ) : favSlot ? (
                <View style={[styles.badge, { backgroundColor: c.icon }]}>
                  <Text style={[styles.badgeText, { color: c.badgeFg }]}>{favSlot.slot}</Text>
                </View>
              ) : (
                <Shield size={15} strokeWidth={2} color={c.icon} />
              )}
            </View>
            <Text style={[styles.label, { color: c.text }]} numberOfLines={1}>
              {modeLabel}
            </Text>
            <ChevronDown
              size={13}
              strokeWidth={2}
              color={c.textSub}
              style={menu === 'mode' ? styles.chevOpen : undefined}
            />
          </Pressable>
        </TutorialAnchor>
      </View>

      <View style={styles.slot} ref={bikeRef} collapsable={false}>
        <TutorialAnchor id="tut-bike-pill" opts={{ capsule: true }}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Bike type"
            onPress={() => openMenu('bike', bikeRef)}
            style={({ pressed }) => [
              styles.pill,
              { borderColor: c.line, backgroundColor: c.surface },
              pressed && styles.pressed,
              menu === 'bike' && { backgroundColor: c.surfaceHover },
            ]}
          >
            <View style={styles.lead}>
              <OptIcon name={activeBike.Icon} />
            </View>
            <Text style={[styles.label, { color: c.text }]} numberOfLines={1}>
              {activeBike.label}
            </Text>
            <ChevronDown
              size={13}
              strokeWidth={2}
              color={c.textSub}
              style={menu === 'bike' ? styles.chevOpen : undefined}
            />
          </Pressable>
        </TutorialAnchor>
      </View>

      <View style={styles.slot} collapsable={false}>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ selected: santanderMode, disabled: !!santanderDisabled }}
          accessibilityLabel="Santander Cycles hire"
          onPress={onSantanderPress}
          style={({ pressed }) => [
            styles.pill,
            { borderColor: c.line, backgroundColor: c.surface },
            santanderMode && styles.santanderOn,
            santanderDisabled && styles.santanderDisabled,
            pressed && !santanderDisabled && styles.pressed,
          ]}
        >
          <View style={[styles.dot, santanderMode && styles.dotOn]} />
          <Text style={[styles.label, { color: c.text }]} numberOfLines={1}>
            Santander
          </Text>
        </Pressable>
      </View>

      <Modal visible={menu != null && !!anchor} transparent animationType="none" onRequestClose={close}>
        <View style={styles.modalRoot} pointerEvents="box-none">
          <Pressable style={StyleSheet.absoluteFill} onPress={close} />
          {anchor && (
            <TutorialAnchor
              id={menu === 'mode' ? 'tut-profile-menu' : 'tut-bike-menu'}
              opts={{ radius: 12 }}
              style={[
                styles.menu,
                {
                  top: anchor.pageY + anchor.height + 5,
                  left: Math.min(
                    anchor.pageX,
                    // keep on screen roughly
                    Math.max(8, anchor.pageX),
                  ),
                  width: menuWidth,
                  maxWidth: 220,
                  backgroundColor: c.shellBg,
                  borderColor: c.line,
                  shadowOpacity: menuShadowOpacity,
                },
              ]}
            >
              {menu === 'mode' && (
                <>
                  {favourites.length > 0 && (
                    <View style={styles.section}>
                      <Text style={[styles.heading, { color: c.textSub }]}>Favourites</Text>
                      {favourites.map((f) => (
                        <Pressable
                          key={f.id}
                          style={({ pressed }) => [
                            styles.item,
                            f.id === activeProfileId && styles.itemActive,
                            pressed && { backgroundColor: c.surface },
                          ]}
                          onPress={() => {
                            onSelectProfile(f.id);
                            close();
                          }}
                        >
                          <View style={[styles.badge, { backgroundColor: c.icon }]}>
                            <Text style={[styles.badgeText, { color: c.badgeFg }]}>{f.slot}</Text>
                          </View>
                          <Text
                            style={[
                              styles.itemText,
                              { color: c.text },
                              f.id === activeProfileId && styles.itemTextActive,
                            ]}
                            numberOfLines={1}
                          >
                            {f.name}
                          </Text>
                          {f.id === activeProfileId ? <View style={styles.activeDot} /> : null}
                        </Pressable>
                      ))}
                    </View>
                  )}
                  <View style={[styles.section, favourites.length > 0 && styles.sectionBorder, favourites.length > 0 && { borderTopColor: c.line }]}>
                    <Text style={[styles.heading, { color: c.textSub }]}>Presets</Text>
                    {PRESET_ORDER.map((id) => {
                      const meta = PRESET_META[id];
                      return (
                        <Pressable
                          key={id}
                          style={({ pressed }) => [
                            styles.item,
                            id === activeProfileId && styles.itemActive,
                            pressed && { backgroundColor: c.surface },
                          ]}
                          onPress={() => {
                            onSelectProfile(id);
                            close();
                          }}
                        >
                          <OptIcon name={meta.Icon} />
                          <Text
                            style={[
                              styles.itemText,
                              { color: c.text },
                              id === activeProfileId && styles.itemTextActive,
                            ]}
                          >
                            {meta.label}
                          </Text>
                          {id === activeProfileId ? <View style={styles.activeDot} /> : null}
                        </Pressable>
                      );
                    })}
                  </View>
                  <Pressable
                    style={[styles.footer, { borderTopColor: c.line }]}
                    onPress={() => {
                      close();
                      onEditFavourites?.();
                    }}
                  >
                    <Text style={[styles.footerText, { color: c.textSub }]}>Edit favourites…</Text>
                  </Pressable>
                </>
              )}
              {menu === 'bike' &&
                bikeOpts.map((opt) => (
                  <Pressable
                    key={opt.id}
                    style={({ pressed }) => [
                      styles.item,
                      opt.id === bikeType && styles.itemActive,
                      pressed && { backgroundColor: c.surface },
                    ]}
                    onPress={() => {
                      onSelectBike(opt.id as BikeTypeId);
                      close();
                    }}
                  >
                    <OptIcon name={opt.Icon} />
                    <Text
                      style={[
                        styles.itemText,
                        { color: c.text },
                        opt.id === bikeType && styles.itemTextActive,
                      ]}
                    >
                      {opt.label}
                    </Text>
                    {opt.id === bikeType ? <View style={styles.activeDot} /> : null}
                  </Pressable>
                ))}
            </TutorialAnchor>
          )}
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  quick: {
    flex: 1,
    flexDirection: 'row',
    gap: 7,
    minWidth: 0,
  },
  slot: { flex: 1, minWidth: 0 },
  pill: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    height: 34,
    paddingHorizontal: 9,
    borderRadius: space.radiusSm,
    borderWidth: 1,
  },
  pressed: { transform: [{ scale: 0.97 }] },
  lead: { flexShrink: 0 },
  label: {
    flex: 1,
    minWidth: 0,
    fontSize: 12.5,
    fontWeight: '600',
  },
  chevOpen: { transform: [{ rotate: '180deg' }] },
  badge: {
    width: 18,
    height: 16,
    borderRadius: 5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: {
    fontSize: 9.5,
    fontWeight: '700',
  },
  santanderOn: {},
  santanderDisabled: { opacity: 0.45 },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 999,
    backgroundColor: '#b3b3b8',
    flexShrink: 0,
  },
  dotOn: {
    backgroundColor: brand.fuchsia,
  },
  modalRoot: {
    flex: 1,
  },
  menu: {
    position: 'absolute',
    padding: 5,
    borderRadius: 11,
    borderWidth: 1,
    shadowColor: '#000',
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 8 },
    elevation: 16,
  },
  section: {
    paddingBottom: 2,
  },
  sectionBorder: {
    marginTop: 4,
    paddingTop: 4,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  heading: {
    paddingHorizontal: 8,
    paddingTop: 4,
    paddingBottom: 3,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.7,
    textTransform: 'uppercase',
  },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    width: '100%',
    paddingVertical: 7,
    paddingHorizontal: 9,
    borderRadius: 8,
  },
  itemActive: {
    // bold text only — web keeps transparent bg until hover
  },
  itemText: {
    flex: 1,
    minWidth: 0,
    fontSize: 12.5,
    fontWeight: '600',
  },
  itemTextActive: {
    fontWeight: '700',
  },
  activeDot: {
    width: 5,
    height: 5,
    borderRadius: 999,
    backgroundColor: brand.fuchsia,
    flexShrink: 0,
  },
  footer: {
    marginTop: 4,
    paddingVertical: 6,
    paddingHorizontal: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  footerText: {
    fontSize: 11.5,
    fontWeight: '600',
  },
});

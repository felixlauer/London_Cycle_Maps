/**
 * Profiles — web ProfilesSection (mobile touch expand for edit/delete).
 */
import { useMemo, useState } from 'react';
import {
  Alert,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  ChevronDown,
  ChevronUp,
  Equal,
  Pencil,
  Plus,
  X,
} from 'lucide-react-native';
import { useAuth } from '../../auth/AuthProvider';
import {
  BIKE_OPTIONS,
  PRESET_META,
  type ProfileRow,
} from '../../routing/constants';
import { brand } from '../../theme/tokens';
import { useChrome } from '../../theme/useChrome';
import { useSidebar } from './SidebarContext';

function isCustomProfile(p: ProfileRow | null | undefined) {
  if (!p?.id) return false;
  if (p.is_system) return false;
  if (PRESET_META[p.id]) return false;
  if (String(p.id).startsWith('preset_')) return false;
  return true;
}

function bikeLabel(bikeType?: string | null) {
  return BIKE_OPTIONS.find((b) => b.id === bikeType)?.label || 'Regular';
}

function sortCustoms(customs: ProfileRow[], order: string[]) {
  if (!order?.length) return customs;
  const rank = new Map(order.map((id, i) => [id, i]));
  return [...customs].sort((a, b) => {
    const ra = rank.has(a.id!) ? rank.get(a.id!)! : 9999;
    const rb = rank.has(b.id!) ? rank.get(b.id!)! : 9999;
    if (ra !== rb) return ra - rb;
    return String(a.name || '').localeCompare(String(b.name || ''));
  });
}

type Props = {
  profiles?: ProfileRow[];
  activeProfileId?: string | null;
  onDeleteProfile?: (id: string) => Promise<void> | void;
  onSelectProfile?: (id: string) => void;
  stacked?: boolean;
  onStackedActivate?: () => void;
};

export function ProfilesSection({
  profiles = [],
  activeProfileId,
  onDeleteProfile,
  onSelectProfile,
  stacked = false,
  onStackedActivate,
}: Props) {
  const { user, isLoading } = useAuth();
  const {
    favouriteOrder,
    setFavouriteOrder,
    openWizard,
    openAuthPanel,
  } = useSidebar();
  const { c } = useChrome();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const customs = useMemo(() => {
    const list = (profiles || []).filter(isCustomProfile);
    return sortCustoms(list, favouriteOrder);
  }, [profiles, favouriteOrder]);

  const reorder = (fromId: string, direction: 'up' | 'down') => {
    const ids = customs.map((p) => p.id!);
    const from = ids.indexOf(fromId);
    if (from < 0) return;
    const to = direction === 'up' ? from - 1 : from + 1;
    if (to < 0 || to >= ids.length) return;
    const next = [...ids];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    setFavouriteOrder(next);
  };

  const handleDelete = (profile: ProfileRow) => {
    if (!onDeleteProfile || busyId || !profile.id) return;
    Alert.alert(
      'Delete profile',
      `Delete profile “${profile.name}”? This cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: () => {
            void (async () => {
              setBusyId(profile.id!);
              try {
                await onDeleteProfile(profile.id!);
              } finally {
                setBusyId(null);
              }
            })();
          },
        },
      ],
    );
  };

  const toggleExpanded = (id: string) => {
    setExpandedId((cur) => (cur === id ? null : id));
  };

  return (
    <View style={styles.section}>
      <View style={styles.head}>
        <Text style={[styles.title, { color: c.text }]}>Riding profiles</Text>
        <Text style={[styles.hint, { color: c.textSub }]}>
          Top 3 appear as favourites in quick settings
        </Text>
      </View>

      {isLoading ? (
        <View style={[styles.skeleton, { backgroundColor: c.inset }]} />
      ) : !user ? (
        <Text style={[styles.empty, { color: c.textSub }]}>
          <Text
            style={styles.textLink}
            onPress={() => openAuthPanel('login')}
          >
            Sign in
          </Text>
          {' '}
          to create a profile.
        </Text>
      ) : (
        <>
          {customs.length === 0 ? (
            <Text style={[styles.empty, { color: c.textSub }]}>
              No custom profiles yet.
            </Text>
          ) : stacked ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Expand riding profiles"
              onPress={() => onStackedActivate?.()}
              style={styles.stack}
            >
              {customs.slice(0, Math.min(3, customs.length)).map((p, i) => {
                const active = p.id === activeProfileId;
                return (
                  <View
                    key={p.id}
                    pointerEvents="none"
                    style={[
                      styles.stackCard,
                      {
                        zIndex: 3 - i,
                        backgroundColor: c.shellBg,
                        borderColor: c.line,
                        transform: [
                          { translateY: i * 7 },
                          { scale: 1 - i * 0.04 },
                        ],
                      },
                      i === 0 && styles.stackFront,
                    ]}
                  >
                    {i === 0 ? (
                      <>
                        <View style={styles.lead}>
                          <View style={[
                            styles.dot,
                            active && styles.dotOn,
                          ]}
                          />
                          <View style={[styles.badge, { backgroundColor: c.icon }]}>
                            <Text style={[styles.badgeText, { color: c.badgeFg }]}>C1</Text>
                          </View>
                        </View>
                        <Text
                          style={[
                            styles.name,
                            { color: c.text },
                            active && styles.nameActive,
                          ]}
                          numberOfLines={1}
                        >
                          {p.name}
                        </Text>
                        <Text style={[styles.bike, { color: c.textSub }]}>
                          {bikeLabel(p.bike_type)}
                        </Text>
                      </>
                    ) : null}
                  </View>
                );
              })}
            </Pressable>
          ) : (
            <>
              {customs.length > 3 ? (
                <Text style={[styles.band, { color: c.textSub }]}>Quick picks</Text>
              ) : null}
              <View style={[styles.card, { borderColor: c.line, backgroundColor: c.shellBg }]}>
                {customs.map((p, index) => {
                  const quick = index < 3;
                  const showMoreBand = index === 3;
                  const active = p.id === activeProfileId;
                  const expanded = expandedId === p.id;
                  return (
                    <View key={p.id}>
                      {showMoreBand ? (
                        <>
                          <View style={[styles.divider, { backgroundColor: c.line }]} />
                          <Text style={[styles.cardBand, { color: c.textSub }]}>
                            More profiles
                          </Text>
                        </>
                      ) : null}
                      {index > 0 && index !== 3 ? (
                        <View style={[styles.divider, { backgroundColor: c.line }]} />
                      ) : null}
                      <Pressable
                        onPress={() => toggleExpanded(p.id!)}
                        style={[
                          styles.row,
                          expanded && { backgroundColor: c.surface },
                        ]}
                      >
                        <View style={styles.lead}>
                          <Pressable
                            accessibilityRole="button"
                            accessibilityLabel={
                              active ? `${p.name} is active` : `Select ${p.name}`
                            }
                            onPress={(e) => {
                              e.stopPropagation?.();
                              onSelectProfile?.(p.id!);
                            }}
                            hitSlop={8}
                            style={[styles.dot, active && styles.dotOn]}
                          />
                          {quick ? (
                            <View style={[styles.badge, { backgroundColor: c.icon }]}>
                              <Text style={[styles.badgeText, { color: c.badgeFg }]}>
                                {`C${index + 1}`}
                              </Text>
                            </View>
                          ) : (
                            <View style={styles.badgeSpacer} />
                          )}
                        </View>

                        <Text
                          style={[
                            styles.name,
                            { color: c.text },
                            active && styles.nameActive,
                          ]}
                          numberOfLines={1}
                        >
                          {p.name}
                        </Text>

                        {!expanded ? (
                          <Text style={[styles.bike, { color: c.textSub }]}>
                            {bikeLabel(p.bike_type)}
                          </Text>
                        ) : (
                          <View style={styles.actions}>
                            <Pressable
                              accessibilityLabel={`Move ${p.name} up`}
                              disabled={index === 0}
                              onPress={() => reorder(p.id!, 'up')}
                              style={({ pressed }) => [
                                styles.action,
                                pressed && { backgroundColor: c.surfaceHover },
                                index === 0 && { opacity: 0.35 },
                              ]}
                              hitSlop={4}
                            >
                              <ChevronUp size={14} strokeWidth={2.2} color={c.textSub} />
                            </Pressable>
                            <Pressable
                              accessibilityLabel={`Move ${p.name} down`}
                              disabled={index === customs.length - 1}
                              onPress={() => reorder(p.id!, 'down')}
                              style={({ pressed }) => [
                                styles.action,
                                pressed && { backgroundColor: c.surfaceHover },
                                index === customs.length - 1 && { opacity: 0.35 },
                              ]}
                              hitSlop={4}
                            >
                              <ChevronDown size={14} strokeWidth={2.2} color={c.textSub} />
                            </Pressable>
                            <Pressable
                              accessibilityLabel={`Edit ${p.name}`}
                              onPress={() => openWizard({ profileId: p.id })}
                              style={({ pressed }) => [
                                styles.action,
                                pressed && { backgroundColor: c.surfaceHover },
                              ]}
                              hitSlop={4}
                            >
                              <Pencil size={14} strokeWidth={2.2} color={c.textSub} />
                            </Pressable>
                            <Pressable
                              accessibilityLabel={`Delete ${p.name}`}
                              disabled={busyId === p.id}
                              onPress={() => handleDelete(p)}
                              style={({ pressed }) => [
                                styles.action,
                                pressed && { backgroundColor: c.surfaceHover },
                                busyId === p.id && { opacity: 0.4 },
                              ]}
                              hitSlop={4}
                            >
                              <X size={15} strokeWidth={2.25} color={c.danger} />
                            </Pressable>
                          </View>
                        )}

                        <View style={styles.grip} pointerEvents="none">
                          <Equal size={15} strokeWidth={2.2} color={c.textSub} />
                        </View>
                      </Pressable>
                    </View>
                  );
                })}
              </View>
            </>
          )}

          {!stacked ? (
            <View style={[styles.card, styles.createCard, { borderColor: c.line }]}>
              <Pressable
                onPress={() => openWizard()}
                style={({ pressed }) => [
                  styles.createRow,
                  pressed && { backgroundColor: c.surface },
                ]}
              >
                <View style={styles.createIcon}>
                  <Plus size={15} strokeWidth={2.4} color={c.icon} />
                </View>
                <Text style={[styles.createLabel, { color: c.text }]}>
                  Create profile
                </Text>
              </Pressable>
            </View>
          ) : null}
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    gap: 10,
  },
  head: {
    gap: 4,
  },
  title: {
    fontSize: 14,
    fontWeight: '700',
    letterSpacing: -0.15,
  },
  hint: {
    fontSize: 12,
    fontWeight: '500',
    lineHeight: 16,
  },
  band: {
    fontSize: 11,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.3,
  },
  empty: {
    fontSize: 13.5,
    lineHeight: 18,
  },
  textLink: {
    fontWeight: '600',
    textDecorationLine: 'underline',
  },
  skeleton: {
    height: 52,
    borderRadius: 11,
  },
  card: {
    borderRadius: 11,
    borderWidth: 1,
    overflow: 'hidden',
  },
  createCard: {
    marginTop: 12,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    marginLeft: 14,
  },
  cardBand: {
    fontSize: 11,
    fontWeight: '600',
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 48,
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 8,
  },
  lead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    width: 33,
    flexShrink: 0,
  },
  dot: {
    width: 11,
    height: 11,
    borderRadius: 999,
    backgroundColor: '#B3B3B8',
  },
  dotOn: {
    backgroundColor: brand.fuchsia,
    shadowColor: brand.fuchsia,
    shadowOpacity: 0.35,
    shadowRadius: 3,
    shadowOffset: { width: 0, height: 0 },
  },
  badge: {
    width: 18,
    height: 18,
    borderRadius: 5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeSpacer: {
    width: 18,
    height: 18,
  },
  badgeText: {
    fontSize: 9.5,
    fontWeight: '700',
  },
  name: {
    flex: 1,
    minWidth: 0,
    fontSize: 13.5,
    fontWeight: '600',
  },
  nameActive: {
    fontWeight: '700',
  },
  bike: {
    flexShrink: 0,
    fontSize: 12,
    fontWeight: '500',
  },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 1,
    flexShrink: 0,
  },
  action: {
    width: 26,
    height: 26,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  grip: {
    width: 24,
    height: 26,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  createRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    minHeight: 48,
    paddingHorizontal: 14,
  },
  createIcon: {
    width: 18,
    height: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  createLabel: {
    fontSize: 13.5,
    fontWeight: '600',
  },
  stack: {
    height: 52,
    marginBottom: 10,
    position: 'relative',
  },
  stackCard: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    height: 48,
    borderRadius: 11,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    gap: 8,
  },
  stackFront: {},
});

import { StyleSheet, Text, View } from 'react-native';
import { Bike, Footprints } from 'lucide-react-native';
import type { HireStation } from '../../api/santander';
import { useChrome } from '../../theme/useChrome';

function IslandHireCard({
  station,
  role,
}: {
  station: HireStation | null | undefined;
  role: string;
}) {
  const { c, themeMode } = useChrome();
  const cardBg = themeMode === 'light' ? '#FFFFFF' : '#1c1c1e';
  if (!station) return null;
  const walkMin = station.walk_duration_min != null
    ? Math.max(1, Math.round(Number(station.walk_duration_min)))
    : null;
  const name = station.name || 'Station';
  const regular = station.nb_standard ?? null;
  const ebikes = station.nb_ebikes ?? null;
  const empty = station.nb_empty ?? station.nb_docks ?? 0;
  const hasBreakdown = regular != null && ebikes != null;

  return (
    <View style={styles.item}>
      <Text style={[styles.role, { color: c.textSub }]}>{role}</Text>
      <View style={[styles.card, { backgroundColor: cardBg, borderColor: c.shellBorder }]}>
        <View style={[styles.badge, { backgroundColor: c.surface }]}>
          <Bike size={12} strokeWidth={2.25} color={c.text} />
        </View>
        <View style={styles.info}>
          <Text style={[styles.name, { color: c.text }]} numberOfLines={1}>{name}</Text>
          {hasBreakdown ? (
            <View style={styles.breakdown}>
              <View style={styles.bd}>
                <Text style={[styles.bdNum, { color: c.text }]}>{regular}</Text>
                <Text style={[styles.bdLabel, { color: c.textSub }]}>regular</Text>
              </View>
              <View style={styles.bd}>
                <Text style={[styles.bdNum, { color: c.text }]}>{ebikes}</Text>
                <Text style={[styles.bdLabel, { color: c.textSub }]}>electric</Text>
              </View>
              <View style={styles.bd}>
                <Text style={[styles.bdNum, { color: c.textSub }]}>{empty}</Text>
                <Text style={[styles.bdLabel, { color: c.textSub }]}>empty</Text>
              </View>
            </View>
          ) : (
            <Text style={[styles.counts, { color: c.text }]}>
              {station.nb_bikes ?? 0}
              {' | '}
              {empty}
              <Text style={[styles.hint, { color: c.textSub }]}> bikes · docks</Text>
            </Text>
          )}
        </View>
        {walkMin != null ? (
          <View style={styles.walk}>
            <Footprints size={11} strokeWidth={2.2} color={c.textSub} />
            <Text style={[styles.walkNum, { color: c.text }]}>{walkMin} min</Text>
            <Text style={[styles.walkHint, { color: c.textSub }]}>walk</Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

/** Compact hire strip for expanded island metrics page (web IslandHireStations). */
export function IslandHireStations({
  pickup,
  dropoff,
}: {
  pickup?: HireStation | null;
  dropoff?: HireStation | null;
}) {
  return (
    <View style={styles.root}>
      <IslandHireCard station={pickup} role="Pick up" />
      <IslandHireCard station={dropoff} role="Drop off" />
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    minWidth: 0,
    justifyContent: 'space-evenly',
    gap: 6,
  },
  item: {
    gap: 2,
    minWidth: 0,
  },
  role: {
    fontSize: 9.5,
    fontWeight: '700',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 5,
    paddingHorizontal: 6,
    borderRadius: 10,
    borderWidth: 1,
    minWidth: 0,
  },
  badge: {
    width: 22,
    height: 22,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  info: {
    flex: 1,
    minWidth: 0,
    gap: 1,
  },
  name: {
    fontSize: 10.5,
    fontWeight: '700',
  },
  breakdown: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  bd: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 2,
  },
  bdNum: {
    fontSize: 10,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
  },
  bdLabel: {
    fontSize: 8,
    fontWeight: '600',
  },
  counts: {
    fontSize: 10,
    fontWeight: '600',
  },
  hint: {
    fontWeight: '500',
  },
  walk: {
    alignItems: 'center',
    gap: 1,
    flexShrink: 0,
  },
  walkNum: {
    fontSize: 9.5,
    fontWeight: '700',
  },
  walkHint: {
    fontSize: 8,
    fontWeight: '600',
  },
});

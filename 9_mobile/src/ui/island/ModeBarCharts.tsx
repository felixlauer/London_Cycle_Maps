import { StyleSheet, Text, Pressable, View } from 'react-native';
import type { RouteHover } from '../../map/routeHover';
import { useChrome } from '../../theme/useChrome';
import { modeKindAggregates } from './modeData';

function barMatchesHover(modeId: string, kind: string, hover: RouteHover | null | undefined) {
  if (!hover) return false;
  if (hover.kind !== kind) return false;
  return hover.modeId == null || hover.modeId === modeId;
}

type Props = {
  safest: Record<string, unknown> | null | undefined;
  modes: string[];
  maxKindsPerChart?: number;
  showOverlayHint?: boolean;
  onOverlayHintClick?: () => void;
  externalHover?: RouteHover | null;
  onHoverChange?: (seg: { modeId: string; kind: string } | null) => void;
};

/**
 * Mode bar charts — press a bar to highlight matching overlay segments (web).
 */
export function ModeBarCharts({
  safest,
  modes,
  maxKindsPerChart = 3,
  showOverlayHint = false,
  onOverlayHintClick,
  externalHover = null,
  onHoverChange,
}: Props) {
  const { c } = useChrome();
  const list = Array.isArray(modes) ? modes : [];
  if (list.length === 0) {
    return (
      <View style={styles.wrap}>
        <Text style={[styles.empty, { color: c.textSub }]}>No mode charts for this route</Text>
      </View>
    );
  }

  return (
    <View style={styles.root}>
      {showOverlayHint ? (
        <View style={styles.noteWrap}>
          <Text style={[styles.note, { color: c.textSub }]} numberOfLines={1}>
            {'Detailed analysis. '}
            <Text style={[styles.noteLink, { color: c.text }]} onPress={onOverlayHintClick}>
              Switch map overlay
            </Text>
            {' to change charts.'}
          </Text>
        </View>
      ) : null}

      <View style={styles.wrap}>
        {list.map((modeId) => {
          const agg = modeKindAggregates(safest, modeId);
          if (!agg) return null;
          const kinds = [...agg.kinds]
            .sort((a, b) => b.pct - a.pct)
            .slice(0, Math.max(1, maxKindsPerChart));
          const maxPct = Math.max(1, ...kinds.map((k) => k.pct));
          return (
            <View key={modeId} style={styles.chart}>
              <Text style={[styles.heading, { color: c.text }]}>{agg.meta.label}</Text>
              {kinds.length === 0 ? (
                <Text style={[styles.empty, { color: c.textSub }]}>
                  {modeId === 'surface' ? 'No rough surfaces on this route' : 'None on this route'}
                </Text>
              ) : (
                kinds.map((k) => {
                  const active = barMatchesHover(modeId, k.kind, externalHover);
                  return (
                    <Pressable
                      key={`${modeId}-${k.kind}`}
                      onPress={() => {
                        if (active) {
                          onHoverChange?.(null);
                          return;
                        }
                        onHoverChange?.({ modeId, kind: k.kind });
                      }}
                      style={[styles.bar, active && { backgroundColor: c.surfaceHover }]}
                    >
                      <View style={styles.barMeta}>
                        <Text style={[styles.barLabel, { color: c.textSub }, active && { color: c.text }]} numberOfLines={1}>
                          {k.label}
                        </Text>
                        <Text style={[styles.pct, { color: c.text }]}>{`${Math.round(k.pct)}%`}</Text>
                      </View>
                      <View style={[styles.track, { backgroundColor: c.inset }]}>
                        <View
                          style={[
                            styles.fill,
                            {
                              width: `${Math.max(3, (k.pct / maxPct) * 100)}%`,
                              backgroundColor: k.color,
                              opacity: active ? 1 : 0.85,
                            },
                          ]}
                        />
                      </View>
                    </Pressable>
                  );
                })
              )}
            </View>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    width: '100%',
    minWidth: 0,
    paddingTop: 16,
  },
  noteWrap: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  note: {
    width: '100%',
    fontSize: 9.5,
    fontWeight: '400',
    lineHeight: 12,
    textAlign: 'center',
  },
  noteLink: {
    textDecorationLine: 'underline',
  },
  wrap: {
    flex: 1,
    gap: 8,
    width: '100%',
    minWidth: 0,
    justifyContent: 'space-evenly',
  },
  chart: { gap: 4, minWidth: 0, width: '100%' },
  heading: {
    fontSize: 11,
    fontWeight: '700',
    marginBottom: 1,
  },
  empty: {
    fontSize: 11,
  },
  bar: {
    width: '100%',
    minWidth: 0,
    gap: 3,
    paddingVertical: 2,
    borderRadius: 6,
  },
  barMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  barLabel: {
    flex: 1,
    minWidth: 0,
    fontSize: 11,
    fontWeight: '600',
  },
  pct: {
    flexShrink: 0,
    fontSize: 11,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
  },
  track: {
    width: '100%',
    height: 6,
    borderRadius: 999,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: 999,
  },
});

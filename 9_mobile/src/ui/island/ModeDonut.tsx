import { useMemo, useState } from 'react';
import { Text, View } from 'react-native';
import Svg, { Circle, G, Path } from 'react-native-svg';
import type { RouteHover } from '../../map/routeHover';
import { useChrome } from '../../theme/useChrome';
import { modeKindAggregates } from './modeData';

function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
  const sweep = endAngle - startAngle;
  if (sweep < 1e-4) return '';
  if (sweep >= 2 * Math.PI - 1e-4) {
    return (
      `M ${cx} ${cy - r} ` +
      `A ${r} ${r} 0 1 1 ${cx} ${cy + r} ` +
      `A ${r} ${r} 0 1 1 ${cx} ${cy - r}`
    );
  }
  const x1 = cx + r * Math.cos(startAngle);
  const y1 = cy + r * Math.sin(startAngle);
  const x2 = cx + r * Math.cos(endAngle);
  const y2 = cy + r * Math.sin(endAngle);
  const large = sweep > Math.PI ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
}

type Props = {
  safest: Record<string, unknown> | null | undefined;
  modeId: string;
  size?: number;
  strokeWidth?: number;
  externalHover?: RouteHover | null;
  onHoverChange?: (seg: { modeId: string; kind: string } | null) => void;
};

/** Mode donut — grey track + bright arcs; press arc → map highlight (web ModeDonut). */
export function ModeDonut({
  safest,
  modeId,
  size = 56,
  strokeWidth = 5.5,
  externalHover = null,
  onHoverChange,
}: Props) {
  const { c: chrome } = useChrome();
  const [localHover, setLocalHover] = useState<{ kind: string } | null>(null);
  const agg = useMemo(() => modeKindAggregates(safest, modeId), [safest, modeId]);
  if (!agg) return null;

  const r = (size - strokeWidth) / 2 - 1;
  const cx = size / 2;

  const activeKind = localHover?.kind
    || (externalHover
      && (externalHover.modeId == null || externalHover.modeId === modeId)
      ? externalHover.kind
      : null);

  let cursor = -Math.PI / 2;
  const arcs = agg.kinds.map((k) => {
    const sweep = Math.max(0, (k.pct / 100) * 2 * Math.PI);
    const start = cursor;
    const end = cursor + sweep;
    cursor = end;
    const d = describeArc(cx, cx, r, start, end);
    if (!d) return null;
    const dimmed = Boolean(activeKind && activeKind !== k.kind);
    const active = activeKind === k.kind;
    return (
      <G key={`${modeId}-${k.kind}`}>
        <Path
          d={d}
          fill="none"
          stroke="transparent"
          strokeWidth={strokeWidth + 14}
          strokeLinecap="butt"
          onPress={() => {
            if (localHover?.kind === k.kind) {
              setLocalHover(null);
              onHoverChange?.(null);
              return;
            }
            setLocalHover(k);
            onHoverChange?.({ modeId, kind: k.kind });
          }}
        />
        <Path
          d={d}
          fill="none"
          stroke={k.color}
          strokeWidth={active ? strokeWidth + 1.5 : strokeWidth}
          strokeLinecap={sweep > 0.08 ? 'round' : 'butt'}
          opacity={dimmed ? 0.35 : 1}
          pointerEvents="none"
        />
      </G>
    );
  }).filter(Boolean);

  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size}>
        <Circle cx={cx} cy={cx} r={r} stroke={chrome.line} strokeWidth={strokeWidth} fill="none" />
        {arcs}
      </Svg>
      <Text
        style={{
          position: 'absolute',
          fontSize: 13,
          fontWeight: '700',
          color: chrome.text,
          letterSpacing: -0.2,
        }}
      >
        {agg.centerPct}%
      </Text>
    </View>
  );
}

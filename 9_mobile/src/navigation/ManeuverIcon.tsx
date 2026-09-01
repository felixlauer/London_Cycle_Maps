import { StyleSheet, View } from 'react-native';
import Svg, { Circle, G, Path } from 'react-native-svg';
import {
  ArrowUp,
  CircleDot,
  CornerUpLeft,
  CornerUpRight,
  Flag,
  GitFork,
  Redo2,
  Undo2,
} from 'lucide-react-native';

/**
 * Turn glyphs for the nav banner, step list and preview sheet.
 *
 * Angle bands (|degrees| between bearing_before and bearing_after):
 *   < 25    straight
 *   25–65   straight arrow rotated by the real angle
 *   65–135  regular turn
 *   >= 135  sharp turn (arrow curls back)
 *   > 160 / uturn modifier — U-turn glyph
 */
const STRAIGHT_MAX = 25;
const SLIGHT_MAX = 65;
const SHARP_MIN = 135;
const UTURN_MIN = 160;

type Props = {
  type?: string | null;
  modifier?: string | null;
  bearingBefore?: number | null;
  bearingAfter?: number | null;
  size?: number;
  color?: string;
  strokeWidth?: number;
};

/** Signed turn: positive is a right (clockwise) turn. */
export function maneuverTurnAngle(
  bearingBefore?: number | null,
  bearingAfter?: number | null,
): number | null {
  if (bearingBefore == null || bearingAfter == null) return null;
  if (!Number.isFinite(bearingBefore) || !Number.isFinite(bearingAfter)) return null;
  let delta = (bearingAfter - bearingBefore) % 360;
  if (delta > 180) delta -= 360;
  if (delta < -180) delta += 360;
  return delta;
}

function sideFromModifier(modifier: string): 'left' | 'right' | null {
  if (modifier.includes('left')) return 'left';
  if (modifier.includes('right')) return 'right';
  return null;
}

export function maneuverLabel(type?: string | null, modifier?: string | null): string {
  const parts = [type, modifier].filter(Boolean);
  return parts.join(' ') || 'continue';
}

export function ManeuverIcon({
  type,
  modifier,
  bearingBefore,
  bearingAfter,
  size = 26,
  color = '#FFFFFF',
  strokeWidth = 2.25,
}: Props) {
  const t = (type || '').toLowerCase().trim();
  const m = (modifier || '').toLowerCase().trim();
  const angle = maneuverTurnAngle(bearingBefore, bearingAfter);
  const magnitude = angle == null ? null : Math.abs(angle);
  const side = sideFromModifier(m) || (angle == null ? null : angle > 0 ? 'right' : 'left');

  if (t === 'depart') return <CircleDot size={size} color={color} strokeWidth={strokeWidth} />;
  if (t === 'arrive') return <Flag size={size} color={color} strokeWidth={strokeWidth} />;

  if (t.includes('roundabout') || t === 'rotary') {
    return <RoundaboutGlyph size={size} color={color} strokeWidth={strokeWidth} exitAngle={angle ?? 0} />;
  }

  const isUturn = m === 'uturn' || m === 'u-turn' || (magnitude != null && magnitude >= UTURN_MIN);
  if (isUturn) {
    return (
      <UturnGlyph
        size={size}
        color={color}
        strokeWidth={strokeWidth}
        side={side === 'left' ? 'left' : 'right'}
      />
    );
  }

  if (t === 'fork' && !side) {
    return <GitFork size={size} color={color} strokeWidth={strokeWidth} />;
  }

  // No bearings (or genuinely straight) — fall back to the modifier wording.
  if (magnitude == null) {
    if (m === 'sharp left') return <Undo2 size={size} color={color} strokeWidth={strokeWidth} />;
    if (m === 'sharp right') return <Redo2 size={size} color={color} strokeWidth={strokeWidth} />;
    if (m === 'slight left' || m === 'slight right') {
      return (
        <RotatedArrow
          size={size}
          color={color}
          strokeWidth={strokeWidth}
          degrees={m === 'slight right' ? 35 : -35}
        />
      );
    }
    if (side === 'left') return <CornerUpLeft size={size} color={color} strokeWidth={strokeWidth} />;
    if (side === 'right') return <CornerUpRight size={size} color={color} strokeWidth={strokeWidth} />;
    return <ArrowUp size={size} color={color} strokeWidth={strokeWidth} />;
  }

  if (magnitude < STRAIGHT_MAX) {
    return <ArrowUp size={size} color={color} strokeWidth={strokeWidth} />;
  }
  if (magnitude < SLIGHT_MAX) {
    return (
      <RotatedArrow size={size} color={color} strokeWidth={strokeWidth} degrees={angle as number} />
    );
  }
  if (magnitude >= SHARP_MIN) {
    return side === 'left'
      ? <Undo2 size={size} color={color} strokeWidth={strokeWidth} />
      : <Redo2 size={size} color={color} strokeWidth={strokeWidth} />;
  }
  return side === 'left'
    ? <CornerUpLeft size={size} color={color} strokeWidth={strokeWidth} />
    : <CornerUpRight size={size} color={color} strokeWidth={strokeWidth} />;
}

/** Slight turns read best as the straight arrow tipped by the real angle. */
function RotatedArrow({
  size,
  color,
  strokeWidth,
  degrees,
}: {
  size: number;
  color: string;
  strokeWidth: number;
  degrees: number;
}) {
  return (
    <View style={[styles.rotate, { transform: [{ rotate: `${Math.round(degrees)}deg` }] }]}>
      <ArrowUp size={size} color={color} strokeWidth={strokeWidth} />
    </View>
  );
}

/** Open ring with an entry stem; the exit arrow swings to the exit bearing. */
function RoundaboutGlyph({
  size,
  color,
  strokeWidth,
  exitAngle,
}: {
  size: number;
  color: string;
  strokeWidth: number;
  exitAngle: number;
}) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Circle
        cx={12}
        cy={10}
        r={5}
        stroke={color}
        strokeWidth={strokeWidth}
        fill="none"
      />
      <Path
        d="M12 22 L12 15"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        fill="none"
      />
      <G rotation={Math.round(exitAngle)} origin="12, 10">
        <Path
          d="M12 5 L12 1.5 M9.4 4 L12 1.5 L14.6 4"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </G>
    </Svg>
  );
}

/** Doubling back — stem up, half loop, arrow down the other side. */
function UturnGlyph({
  size,
  color,
  strokeWidth,
  side,
}: {
  size: number;
  color: string;
  strokeWidth: number;
  side: 'left' | 'right';
}) {
  const path = side === 'right'
    ? 'M7.5 21 L7.5 11 A4.5 4.5 0 0 1 16.5 11 L16.5 17'
    : 'M16.5 21 L16.5 11 A4.5 4.5 0 0 0 7.5 11 L7.5 17';
  const head = side === 'right'
    ? 'M13.5 14.5 L16.5 18 L19.5 14.5'
    : 'M4.5 14.5 L7.5 18 L10.5 14.5';
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Path
        d={path}
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        fill="none"
      />
      <Path
        d={head}
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </Svg>
  );
}

const styles = StyleSheet.create({
  rotate: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});

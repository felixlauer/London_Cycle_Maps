import { StyleSheet, Text, View } from 'react-native';
import { MarkerView } from '@rnmapbox/maps';
import { latLonToLngLat, type LatLon } from '../lib/coords';

type Point = {
  key: string;
  coord: LatLon;
  label: string;
};

type Props = {
  start: LatLon | null;
  end: LatLon | null;
  vias?: { id?: string; coord: LatLon | null }[];
  /** When start is GPS ("Current location"), omit the A badge — LocationPuck is enough. */
  hideStart?: boolean;
};

function letterAt(index: number) {
  return String.fromCharCode(65 + index);
}

/**
 * Greyscale teardrop — web PointMarkers.
 * MarkerView sits above GL route lines; wrap sized so rotated tip is not clipped.
 */
function Pin({ label }: { label: string }) {
  return (
    <View style={styles.pinWrap} collapsable={false}>
      <View style={styles.pin}>
        <Text style={styles.letter}>{label}</Text>
      </View>
    </View>
  );
}

export function PointMarkers({ start, end, vias, hideStart }: Props) {
  const points: Point[] = [];
  if (start && !hideStart) {
    points.push({ key: 'start', coord: start, label: letterAt(0) });
  }
  // Keep letter indices stable: start always reserved as A even when hidden.
  const letterBase = start ? 1 : 0;
  let viaOrdinal = 0;
  (vias || []).forEach((v) => {
    if (!v?.coord) return;
    points.push({
      key: v.id || `via-${viaOrdinal}`,
      coord: v.coord,
      label: letterAt(letterBase + viaOrdinal),
    });
    viaOrdinal += 1;
  });
  if (end) {
    points.push({
      key: 'end',
      coord: end,
      label: letterAt(letterBase + viaOrdinal),
    });
  }

  return (
    <>
      {points.map((p) => {
        const ll = latLonToLngLat(p.coord);
        if (!ll) return null;
        return (
          <MarkerView
            key={p.key}
            coordinate={ll}
            anchor={{ x: 0.5, y: 1 }}
            allowOverlap
            allowOverlapWithPuck
          >
            <Pin label={p.label} />
          </MarkerView>
        );
      })}
    </>
  );
}

const styles = StyleSheet.create({
  // Rotated 24px square needs ~34px bbox — pad so the tip is never clipped.
  pinWrap: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pin: {
    width: 24,
    height: 24,
    backgroundColor: '#3f3f46',
    borderWidth: 2,
    borderColor: '#fff',
    borderTopLeftRadius: 12,
    borderTopRightRadius: 12,
    borderBottomRightRadius: 12,
    borderBottomLeftRadius: 0,
    transform: [{ rotate: '-45deg' }],
    alignItems: 'center',
    justifyContent: 'center',
  },
  letter: {
    transform: [{ rotate: '45deg' }],
    color: '#fff',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 12,
    textAlign: 'center',
    includeFontPadding: false,
  },
});

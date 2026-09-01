import { useMemo } from 'react';
import { Text, View } from 'react-native';
import Svg, { Defs, LinearGradient, Path, Stop } from 'react-native-svg';
import { useChrome } from '../../theme/useChrome';
import { areaPathFromLine, scaleProfile, smoothLinePath } from './elevationPath';

export const ELEVATION_ACCENT = '#8717BF';

type Props = {
  profile?: { d_m?: number; elev_m?: number }[] | null;
  width?: number;
  height?: number;
  accent?: string;
};

export function ElevationSparkline({
  profile,
  width = 72,
  height = 30,
  accent = ELEVATION_ACCENT,
}: Props) {
  const { c } = useChrome();
  const geo = useMemo(
    () => scaleProfile(profile, { width, height, padX: 2, padTop: 5, padBottom: 3 }),
    [profile, width, height],
  );

  if (!geo) {
    return (
      <View style={{ width, height, alignItems: 'center', justifyContent: 'center' }}>
        <Text style={{ color: c.textSub, fontSize: 12 }}>—</Text>
      </View>
    );
  }

  const line = smoothLinePath(geo.points);
  const area = areaPathFromLine(line, geo.points, height);

  return (
    <Svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <Defs>
        <LinearGradient id="island-spark-grad" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0%" stopColor={accent} stopOpacity={0.28} />
          <Stop offset="100%" stopColor={accent} stopOpacity={0} />
        </LinearGradient>
      </Defs>
      <Path d={area} fill="url(#island-spark-grad)" stroke="none" />
      <Path
        d={line}
        fill="none"
        stroke={accent}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}


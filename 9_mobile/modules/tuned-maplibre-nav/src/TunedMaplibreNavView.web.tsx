import { View } from 'react-native';
import type { TunedMaplibreNavViewProps } from './TunedMaplibreNav.types';

/** Web has no navigation engine — render an inert surface. */
export function TunedMaplibreNavView({ style }: TunedMaplibreNavViewProps) {
  return <View style={style} />;
}

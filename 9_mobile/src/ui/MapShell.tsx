import { ReactNode, useState } from 'react';
import {
  LayoutChangeEvent,
  StyleSheet,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { chromeForTheme, space } from '../theme/tokens';
import type { ThemeMode } from '../theme/resolveAppearance';

type Props = {
  map: ReactNode;
  top?: ReactNode;
  alert?: ReactNode;
  mapControls?: ReactNode;
  /** Freeform chrome above the map (e.g. hire expanded hit targets). */
  mapOverlay?: ReactNode;
  island?: ReactNode;
  sidebar?: ReactNode;
  islandExpanded?: boolean;
  themeMode?: ThemeMode;
  style?: StyleProp<ViewStyle>;
};

/**
 * Full-bleed map + floating chrome (web MapShell mobile).
 * Alert is centred on the full screen; AlertPill caps its own maxWidth
 * so it never reaches the right control stack.
 */
export function MapShell({
  map,
  top,
  alert,
  mapControls,
  mapOverlay,
  island,
  sidebar,
  islandExpanded = false,
  themeMode = 'dark',
  style,
}: Props) {
  const c = chromeForTheme(themeMode);
  const [topH, setTopH] = useState(0);

  const onTopLayout = (e: LayoutChangeEvent) => {
    setTopH(e.nativeEvent.layout.height);
  };

  const belowTop = Math.max(0, space.inset - 4) + topH + 8;
  const islandBottom = islandExpanded ? space.inset * 1.4 : space.inset * 3.5;

  return (
    <View style={[styles.root, { backgroundColor: c.mapFallback }, style]}>
      <View style={styles.map} pointerEvents="box-none">
        {map}
      </View>
      <View style={styles.chrome} pointerEvents="box-none">
        {mapOverlay ? (
          <View style={styles.mapOverlay} pointerEvents="box-none">
            {mapOverlay}
          </View>
        ) : null}

        {top ? (
          <View
            style={[styles.top, { top: Math.max(0, space.inset - 4) }]}
            pointerEvents="box-none"
            onLayout={onTopLayout}
          >
            {top}
          </View>
        ) : null}

        {alert ? (
          <View
            style={[styles.alert, { top: belowTop }]}
            pointerEvents="box-none"
          >
            {alert}
          </View>
        ) : null}

        {mapControls ? (
          <View
            style={[styles.mapControls, { top: belowTop }]}
            pointerEvents="box-none"
          >
            {mapControls}
          </View>
        ) : null}

        {island ? (
          <View style={[styles.island, { bottom: islandBottom }]} pointerEvents="box-none">
            {island}
          </View>
        ) : null}
      </View>

      {sidebar ? (
        <View style={styles.sidebar} pointerEvents="box-none">
          {sidebar}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  map: {
    ...StyleSheet.absoluteFill,
    zIndex: 0,
  },
  chrome: {
    ...StyleSheet.absoluteFill,
    zIndex: 10,
  },
  mapOverlay: {
    ...StyleSheet.absoluteFill,
    zIndex: 28,
    elevation: 28,
  },
  top: {
    position: 'absolute',
    left: space.inset,
    right: space.inset,
    zIndex: 20,
  },
  alert: {
    position: 'absolute',
    left: 0,
    right: 0,
    alignItems: 'center',
    zIndex: 18,
    paddingHorizontal: space.inset,
  },
  mapControls: {
    position: 'absolute',
    right: space.inset,
    zIndex: 19,
  },
  island: {
    position: 'absolute',
    left: space.inset,
    right: space.inset,
    alignItems: 'center',
    zIndex: 15,
    overflow: 'visible',
  },
  sidebar: {
    ...StyleSheet.absoluteFill,
    zIndex: 50,
    elevation: 50,
  },
});

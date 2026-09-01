import { requireNativeViewManager } from 'expo-modules-core';
import type { ComponentType } from 'react';
import type { TunedMaplibreNavViewProps } from './TunedMaplibreNav.types';

/**
 * In-process MapLibre navigation map (Android). Renders the map, puck, camera,
 * route line and voice; every piece of chrome is React Native on top.
 */
export const TunedMaplibreNavView: ComponentType<TunedMaplibreNavViewProps> =
  requireNativeViewManager('TunedMaplibreNav');

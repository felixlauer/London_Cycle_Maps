/**
 * Expo config — reads EXPO_PUBLIC_* from .env (loaded by Expo CLI).
 * Do not put secret sk. tokens here.
 */
export default {
  expo: {
    name: 'Tuned',
    slug: 'tuned-cycling',
    version: '1.0.0',
    orientation: 'portrait',
    icon: './assets/icon.png',
    userInterfaceStyle: 'light',
    scheme: 'tuned',
    ios: {
      supportsTablet: true,
      bundleIdentifier: 'online.tunedcycling.app',
      infoPlist: {
        MBXAccessToken: process.env.EXPO_PUBLIC_MAPBOX_TOKEN || '',
      },
    },
    android: {
      package: 'online.tunedcycling.app',
      adaptiveIcon: {
        backgroundColor: '#E6F4FE',
        foregroundImage: './assets/android-icon-foreground.png',
        backgroundImage: './assets/android-icon-background.png',
        monochromeImage: './assets/android-icon-monochrome.png',
      },
      predictiveBackGestureEnabled: false,
    },
    web: {
      favicon: './assets/favicon.png',
    },
    plugins: [
      'expo-secure-store',
      'expo-dev-client',
      [
        'expo-location',
        {
          locationWhenInUsePermission: 'Show your location on the Tuned map.',
        },
      ],
      [
        '@rnmapbox/maps',
        {
          // Must match @rnmapbox/maps package.json mapbox.android (10.3.5 → 11.23.1).
          // Too-old SDK (e.g. 11.16.2) fails Kotlin compile: DistanceUnits, lineElevationGroundScale, …
          RNMapboxMapsVersion: '11.23.1',
        },
      ],
      './plugins/withMapLibreNavigation',
    ],
  },
};

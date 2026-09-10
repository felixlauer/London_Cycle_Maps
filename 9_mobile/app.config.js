/**
 * Expo config — reads EXPO_PUBLIC_* from .env (loaded by Expo CLI).
 * Do not put secret sk. tokens here.
 */

/**
 * Shown by iOS when the app first asks for location. Written to stay true once
 * turn-by-turn lands, so beta 2 does not have to change the permission copy.
 * When In Use only — no Always key, no location background mode.
 */
const LOCATION_WHEN_IN_USE = 'TUNE uses your location only while the app is on screen, '
  + 'to show where you are on the map, start routes from your current position, and '
  + '(when you use Navigate) follow your ride. Location is not used in the background.';

const BRAND_FUCHSIA = '#FF0061';

export default {
  expo: {
    name: 'TUNE',
    slug: 'tuned-cycling',
    version: '1.0.0',
    orientation: 'portrait',
    icon: './assets/icon.png',
    // Follow the device. In-app appearance still resolves light|dark for the
    // map and shell tokens (src/theme/resolveAppearance.ts).
    userInterfaceStyle: 'automatic',
    scheme: 'tuned',
    extra: {
      eas: {
        // Written by eas init — Expo cannot patch a JS app.config.js itself.
        projectId: '587a9315-c657-43c2-8cba-fe810fa6af48',
      },
    },
    ios: {
      // iPhone only for beta 1 — no iPad layouts exist.
      supportsTablet: false,
      bundleIdentifier: 'online.tunedcycling.app',
      config: {
        // HTTPS + Keychain only, so the app qualifies for the export exemption.
        usesNonExemptEncryption: false,
      },
      infoPlist: {
        MBXAccessToken: process.env.EXPO_PUBLIC_MAPBOX_TOKEN || '',
        LSRequiresIPhoneOS: true,
      },
      // Required-reason API declarations. No tracking domains: the app has no
      // ad SDK and no ATT prompt, so NSPrivacyTracking stays false.
      privacyManifests: {
        NSPrivacyTracking: false,
        NSPrivacyTrackingDomains: [],
        NSPrivacyCollectedDataTypes: [],
        NSPrivacyAccessedAPITypes: [
          {
            // React Native and expo-secure-store read/write app preferences.
            NSPrivacyAccessedAPIType: 'NSPrivacyAccessedAPICategoryUserDefaults',
            NSPrivacyAccessedAPITypeReasons: ['CA92.1'],
          },
          {
            // expo-file-system and the Mapbox tile cache stat their own files.
            NSPrivacyAccessedAPIType: 'NSPrivacyAccessedAPICategoryFileTimestamp',
            NSPrivacyAccessedAPITypeReasons: ['C617.1'],
          },
          {
            // Mapbox checks free space before writing offline tiles.
            NSPrivacyAccessedAPIType: 'NSPrivacyAccessedAPICategoryDiskSpace',
            NSPrivacyAccessedAPITypeReasons: ['E174.1'],
          },
          {
            // Hermes / RN use uptime for frame timing, not identification.
            NSPrivacyAccessedAPIType: 'NSPrivacyAccessedAPICategorySystemBootTime',
            NSPrivacyAccessedAPITypeReasons: ['35F9.1'],
          },
        ],
      },
    },
    android: {
      package: 'online.tunedcycling.app',
      adaptiveIcon: {
        backgroundColor: BRAND_FUCHSIA,
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
      // Registered before expo-location on purpose: Info.plist mods run in
      // reverse registration order, so this one executes last and gets the
      // final say on the location keys.
      './plugins/withIosWhenInUseLocation',
      './plugins/withDisableAppleSiliconMac',
      'expo-secure-store',
      'expo-dev-client',
      // Applies userInterfaceStyle on Android and the root view colour on iOS.
      'expo-system-ui',
      [
        'expo-splash-screen',
        {
          backgroundColor: BRAND_FUCHSIA,
          image: './assets/splash-icon.png',
          imageWidth: 200,
          resizeMode: 'contain',
          // Brand fuchsia in both appearances — the JS boot screen
          // (OnboardingLoading) picks up the theme once React mounts.
          dark: {
            backgroundColor: BRAND_FUCHSIA,
            image: './assets/splash-icon.png',
          },
        },
      ],
      [
        'expo-location',
        {
          locationWhenInUsePermission: LOCATION_WHEN_IN_USE,
          isIosBackgroundLocationEnabled: false,
          isAndroidBackgroundLocationEnabled: false,
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

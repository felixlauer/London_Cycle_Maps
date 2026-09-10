/**
 * Keep the iOS Info.plist honest: When In Use location only.
 *
 * The expo-location plugin writes NSLocationAlwaysUsageDescription and
 * NSLocationAlwaysAndWhenInUseUsageDescription with default copy even when only
 * `locationWhenInUsePermission` is configured. The app never calls
 * requestBackgroundPermissionsAsync, so those keys would advertise a capability
 * that does not exist and invite questions during Beta App Review.
 *
 * Also drops `location` from UIBackgroundModes if anything adds it later.
 * Turn-by-turn (beta 2) stays foreground-only, so this plugin does not need an
 * escape hatch.
 */
const { withInfoPlist } = require('@expo/config-plugins');

const ALWAYS_KEYS = [
  'NSLocationAlwaysUsageDescription',
  'NSLocationAlwaysAndWhenInUseUsageDescription',
];

function withIosWhenInUseLocation(config) {
  // expo-location writes the usage strings straight onto the static config
  // (createPermissionsPlugin mutates ios.infoPlist), so clear that first —
  // this plugin is listed after it. The mod below covers anything written later.
  if (config.ios && config.ios.infoPlist) {
    for (const key of ALWAYS_KEYS) {
      delete config.ios.infoPlist[key];
    }
  }

  return withInfoPlist(config, (cfg) => {
    for (const key of ALWAYS_KEYS) {
      delete cfg.modResults[key];
    }

    const modes = cfg.modResults.UIBackgroundModes;
    if (Array.isArray(modes)) {
      const kept = modes.filter((mode) => mode !== 'location');
      if (kept.length) cfg.modResults.UIBackgroundModes = kept;
      else delete cfg.modResults.UIBackgroundModes;
    }

    return cfg;
  });
}

module.exports = withIosWhenInUseLocation;

/**
 * Opt the iOS target out of "iPhone app on Apple silicon Mac".
 *
 * Apple still analyzes iOS binaries for Mac availability. ExpoModulesCore
 * only exports iOS symbols, which produced ITMS-90863 on build 1 and is the
 * same ABI path that crashed on launch. These Xcode flags stop Apple treating
 * the IPA as a Mac-capable iPhone app. The App Store Connect checkbox
 * (Preise und Verfügbarkeit → Apple Silicon Mac) is still required once;
 * that setting is not in the binary.
 */
const { withXcodeProject } = require('@expo/config-plugins');

const FLAGS = {
  SUPPORTS_MACCATALYST: 'NO',
  SUPPORTS_MAC_DESIGNED_FOR_IPHONE_IPAD: 'NO',
  SUPPORTS_XR_DESIGNED_FOR_IPHONE_IPAD: 'NO',
};

function withDisableAppleSiliconMac(config) {
  return withXcodeProject(config, (cfg) => {
    const configs = cfg.modResults.pbxXCBuildConfigurationSection();
    for (const key of Object.keys(configs)) {
      const buildSettings = configs[key].buildSettings;
      if (!buildSettings || typeof buildSettings !== 'object') continue;
      Object.assign(buildSettings, FLAGS);
    }
    return cfg;
  });
}

module.exports = withDisableAppleSiliconMac;

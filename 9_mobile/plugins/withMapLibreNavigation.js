/**
 * Soften dual Mapbox Maps + MapLibre Navigation native .so conflicts
 * after Expo prebuild. The navigation module itself also declares pickFirst.
 * Also adds JDK 24+ native-access flag so AGP prefab does not treat
 * "restricted method in java.lang.System" stderr as a configureCMake failure.
 */
const { withAppBuildGradle, withGradleProperties } = require('@expo/config-plugins');

function withMapLibreNavigation(config) {
  config = withGradleProperties(config, (cfg) => {
    const key = 'org.gradle.jvmargs';
    const flag = '--enable-native-access=ALL-UNNAMED';
    const existing = cfg.modResults.find((item) => item.type === 'property' && item.key === key);
    if (existing) {
      if (!String(existing.value || '').includes(flag)) {
        existing.value = `${existing.value || ''} ${flag}`.trim();
      }
    } else {
      cfg.modResults.push({
        type: 'property',
        key,
        value: `-Xmx2048m -XX:MaxMetaspaceSize=512m ${flag}`,
      });
    }
    return cfg;
  });

  return withAppBuildGradle(config, (cfg) => {
    if (cfg.modResults.language !== 'groovy') {
      return cfg;
    }
    if (cfg.modResults.contents.includes('packagingOptions')) {
      if (!cfg.modResults.contents.includes("pickFirst '**/libmaplibre.so'")) {
        cfg.modResults.contents = cfg.modResults.contents.replace(
          /packagingOptions\s*\{/,
          `packagingOptions {\n        pickFirst '**/libmaplibre.so'\n        pickFirst '**/libmapbox-common.so'`,
        );
      }
      return cfg;
    }
    const snippet = `
    packagingOptions {
        pickFirst '**/libc++_shared.so'
        pickFirst '**/libjsc.so'
        pickFirst '**/libmapbox-common.so'
        pickFirst '**/libmapbox-maps.so'
        pickFirst '**/libmaplibre.so'
    }
`;
    cfg.modResults.contents = cfg.modResults.contents.replace(
      /android\s*\{/,
      `android {\n${snippet}`,
    );
    return cfg;
  });
}

module.exports = withMapLibreNavigation;

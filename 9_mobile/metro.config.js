const path = require('path');
const { getDefaultConfig } = require('expo/metro-config');

/** @type {import('expo/metro-config').MetroConfig} */
const config = getDefaultConfig(__dirname);

/**
 * @rnmapbox/maps 10.3.x ships Fabric codegen specs as `.ts` beside compiled `.js`.
 * With Metro package-exports on (Expo default), relative imports like
 * `Snow.js → ../specs/RNMBXSnowNativeComponent` fail with UnableToResolveError.
 *
 * Disable package exports and resolve the package entry to the TypeScript source
 * so specs + components load consistently.
 */
config.resolver.unstable_enablePackageExports = false;

const rnmapboxEntry = path.resolve(
  __dirname,
  'node_modules/@rnmapbox/maps/src/index.ts',
);

const defaultResolveRequest = config.resolver.resolveRequest;
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (moduleName === '@rnmapbox/maps') {
    return { type: 'sourceFile', filePath: rnmapboxEntry };
  }
  if (defaultResolveRequest) {
    return defaultResolveRequest(context, moduleName, platform);
  }
  return context.resolveRequest(context, moduleName, platform);
};

module.exports = config;

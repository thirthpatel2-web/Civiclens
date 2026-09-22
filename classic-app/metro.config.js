// Metro config. The only customisation is a WEB-ONLY alias for react-native-maps, which is a
// native module (it wraps the Google/Apple Maps SDKs) and has no web build - without this the
// web bundle fails to resolve it. Native platforms are untouched and resolve normally.
const { getDefaultConfig } = require('expo/metro-config');
const path = require('node:path');

const config = getDefaultConfig(__dirname);

const WEB_ALIASES = {
  'react-native-maps': path.resolve(__dirname, 'src/shims/react-native-maps.web.tsx'),
};

const defaultResolveRequest = config.resolver.resolveRequest;

config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (platform === 'web' && WEB_ALIASES[moduleName]) {
    return { type: 'sourceFile', filePath: WEB_ALIASES[moduleName] };
  }
  return defaultResolveRequest ? defaultResolveRequest(context, moduleName, platform) : context.resolveRequest(context, moduleName, platform);
};

module.exports = config;

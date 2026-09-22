import Constants from 'expo-constants';

const extra = (Constants.expoConfig?.extra ?? {}) as { apiBaseUrl?: string };
export const API_BASE_URL: string = (process.env.EXPO_PUBLIC_API_URL || extra.apiBaseUrl || '').replace(/\/+$/, '');
export const IS_CONFIGURED = API_BASE_URL.length > 0;
export const WS_URL = API_BASE_URL.replace(/^http/, 'ws') + '/ws';
// Production builds must talk HTTPS: the session token travels in the Authorization header.
export const IS_INSECURE = API_BASE_URL.startsWith('http://') && !/(localhost|127\.0\.0\.1|10\.0\.2\.2|192\.168\.|10\.)/.test(API_BASE_URL);

// The session token lives ONLY in the OS secure store (Keychain / Android Keystore-backed), never in
// AsyncStorage, on the native platforms this app ships on. expo-secure-store has no web implementation
// at all (it throws), so the one exception is the browser preview used for development: there the
// token falls back to sessionStorage (cleared when the tab closes) purely so the web build is usable
// for testing - this app is not shipped to citizens as a website, only Expo Go / native builds are.
import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

const KEY = 'civiclens.session.token';

export const getToken = async (): Promise<string | null> =>
  Platform.OS === 'web' ? window.sessionStorage.getItem(KEY) : SecureStore.getItemAsync(KEY);

export const setToken = async (t: string): Promise<void> => {
  if (Platform.OS === 'web') { window.sessionStorage.setItem(KEY, t); return; }
  await SecureStore.setItemAsync(KEY, t, { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
};

export const clearToken = async (): Promise<void> => {
  if (Platform.OS === 'web') { window.sessionStorage.removeItem(KEY); return; }
  await SecureStore.deleteItemAsync(KEY);
};

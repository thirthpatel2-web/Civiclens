// The session token lives ONLY in the OS secure store (Keychain / Android Keystore-backed), never in AsyncStorage.
import * as SecureStore from 'expo-secure-store';

const KEY = 'civiclens.session.token';
export const getToken = () => SecureStore.getItemAsync(KEY);
export const setToken = (t: string) => SecureStore.setItemAsync(KEY, t, { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
export const clearToken = () => SecureStore.deleteItemAsync(KEY);

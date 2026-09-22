import AsyncStorage from '@react-native-async-storage/async-storage';
import * as FileSystem from 'expo-file-system/legacy';
import { DraftStore } from './queue.ts';
import type { KeyValueStorage } from './queue.ts';
import type { LocalFile } from '../api/types.ts';

// Draft metadata is app-private (sandboxed). The session token is NOT stored here (see auth/session.ts).
export const kv: KeyValueStorage = { getItem: (k) => AsyncStorage.getItem(k), setItem: (k, v) => AsyncStorage.setItem(k, v), removeItem: (k) => AsyncStorage.removeItem(k) };
export const draftStore = new DraftStore(kv);

const DIR = `${FileSystem.documentDirectory}civiclens-outbox/`;

/** Copy a camera/recorder temp file into the app's persistent outbox so it survives cache clearing until it is synced. */
export async function persistLocalFile(file: LocalFile): Promise<LocalFile> {
  await FileSystem.makeDirectoryAsync(DIR, { intermediates: true }).catch(() => undefined);
  const dest = `${DIR}${Date.now()}-${file.name.replace(/[^A-Za-z0-9._-]/g, '_')}`;
  await FileSystem.copyAsync({ from: file.uri, to: dest });
  return { ...file, uri: dest };
}
export async function deleteLocalFile(uri: string) { await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => undefined); }

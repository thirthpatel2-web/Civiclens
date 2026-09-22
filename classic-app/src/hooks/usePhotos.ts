import * as ImagePicker from 'expo-image-picker';
import type { LocalFile } from '../api/types.ts';

const toFile = (a: ImagePicker.ImagePickerAsset): LocalFile => ({ uri: a.uri, name: a.fileName ?? `photo-${Date.now()}.jpg`, type: a.mimeType ?? 'image/jpeg' });

export async function takePhoto(): Promise<LocalFile | null> {
  const perm = await ImagePicker.requestCameraPermissionsAsync();
  if (!perm.granted) return null;
  const r = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.7 });
  return r.canceled ? null : toFile(r.assets[0]);
}
export async function pickPhotos(): Promise<LocalFile[]> {
  const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.7, allowsMultipleSelection: true, selectionLimit: 4 });
  return r.canceled ? [] : r.assets.map(toFile);
}

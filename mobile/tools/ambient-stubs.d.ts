declare namespace JSX { interface Element { type: any; props: any; key: any; children: any; [k: string]: any } interface IntrinsicElements { [k: string]: any } interface ElementChildrenAttribute { children: {} } interface IntrinsicAttributes { key?: any } }
declare module 'react' {
  export type ReactNode = any;
  export type FC<P = {}> = (p: P) => any;
  export function useState<T>(i: T | (() => T)): [T, (v: T | ((p: T) => T)) => void];
  export function useEffect(f: () => void | (() => void) | Promise<void>, d?: any[]): void;
  export function useCallback<T extends (...a: any[]) => any>(f: T, d: any[]): T;
  export function useMemo<T>(f: () => T, d: any[]): T;
  export function useRef<T>(i: T): { current: T };
  export function useReducer<S, A>(r: (s: S, a: A) => S, i: S): [S, (a: A) => void];
  export function createContext<T>(d: T): { Provider: any; __t?: T };
  export function useContext<T>(c: { Provider: any; __t?: T }): T;
  const React: any; export default React;
}
declare module 'react-native' { export const View: any, Text: any, TextInput: any, ScrollView: any, Pressable: any, Image: any, Switch: any, ActivityIndicator: any, StyleSheet: { create<T>(x: T): T }, Linking: any, AppState: any, Platform: any, Appearance: any; export type TextInputProps = any; export type ViewStyle = any; }
declare module 'react-native-maps' { const M: any; export default M; export const Circle: any, Marker: any; }
declare module 'expo-router' { export const Slot: any, Link: any, Redirect: any, Tabs: any; export function useRouter(): any; export function useSegments(): string[]; export function useLocalSearchParams<T>(): T; }
declare module 'expo-status-bar' { export const StatusBar: any; }
declare module '@expo/vector-icons' { export const Ionicons: any; }
declare module 'expo-audio' { export function useAudioRecorder(o: any): any; export const RecordingPresets: any; export function requestRecordingPermissionsAsync(): Promise<any>; export function setAudioModeAsync(o: any): Promise<void>; }
declare module 'expo-secure-store' { export const WHEN_UNLOCKED_THIS_DEVICE_ONLY: any; export function getItemAsync(k: string): Promise<string | null>; export function setItemAsync(k: string, v: string, o?: any): Promise<void>; export function deleteItemAsync(k: string): Promise<void>; }
declare module 'expo-location' { const L: any; export = L; }
declare module 'expo-image-picker' { export const launchCameraAsync: any, launchImageLibraryAsync: any, requestCameraPermissionsAsync: any; export type ImagePickerAsset = { uri: string; fileName?: string | null; mimeType?: string | null }; }
declare module 'expo-notifications' { const N: any; export = N; }
declare module 'expo-constants' { const C: any; export default C; }
declare module 'expo-crypto' { export function randomUUID(): string; }
declare module 'expo-file-system/legacy' { const F: any; export = F; }
declare module 'expo-background-task' { const B: any; export = B; }
declare module 'expo-task-manager' { const T: any; export = T; }
declare module '@react-native-community/netinfo' { const N: any; export default N; }
declare module '@react-native-async-storage/async-storage' { const A: any; export default A; }
declare const process: { env: Record<string, string | undefined> };
declare module '*.json' { const v: any; export default v; }
declare module 'node:test' { export const test: any; }
declare module 'node:assert/strict' { const a: any; export default a; }
declare module 'node:fs' { export const readFileSync: any; }
declare const FormData: any; declare class AbortController { signal: any; abort(): void }
declare interface ImportMeta { url: string }
declare const globalThis: any;
declare module 'react/jsx-runtime' { export const jsx: any, jsxs: any, Fragment: any; }

import { useCallback, useState } from 'react';
import * as Location from 'expo-location';

export type LocationState = { kind: 'none' } | { kind: 'locating' } | { kind: 'ok'; lat: number; lng: number; accuracy: number | null } | { kind: 'denied' } | { kind: 'error'; message: string };

/** Location is requested only when the citizen taps "Use my location"; coordinates are attached, never invented. */
export function useDeviceLocation() {
  const [state, setState] = useState<LocationState>({ kind: 'none' });
  const request = useCallback(async () => {
    setState({ kind: 'locating' });
    const perm = await Location.requestForegroundPermissionsAsync();
    if (perm.status !== 'granted') { setState({ kind: 'denied' }); return null; }
    try {
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const ok = { kind: 'ok' as const, lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy ?? null };
      setState(ok);
      return ok;
    } catch (e: any) { setState({ kind: 'error', message: e?.message ?? 'Could not get your location.' }); return null; }
  }, []);
  return { state, request, clear: () => setState({ kind: 'none' }) };
}

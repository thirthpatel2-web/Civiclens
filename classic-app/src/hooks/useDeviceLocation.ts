import { useCallback, useState } from 'react';
import * as Location from 'expo-location';
import { endpoints } from '../api/instance.ts';
import type { ReverseGeocodeResult } from '../api/types.ts';

export type LocationState =
  | { kind: 'none' }
  | { kind: 'locating' }
  | { kind: 'ok'; lat: number; lng: number; accuracy: number | null; address: ReverseGeocodeResult | null; addressLoading: boolean }
  | { kind: 'denied' }
  | { kind: 'error'; message: string };

/** Location is requested only when the citizen taps "Use my location"; coordinates are attached, never
 * invented. The reverse-geocoded address (city/state/pincode/area) is best-effort and additive - if it
 * fails or the lookup is unavailable, the coordinates alone are still a complete, valid location. */
export function useDeviceLocation() {
  const [state, setState] = useState<LocationState>({ kind: 'none' });
  const request = useCallback(async () => {
    setState({ kind: 'locating' });
    const perm = await Location.requestForegroundPermissionsAsync();
    if (perm.status !== 'granted') { setState({ kind: 'denied' }); return null; }
    try {
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const { latitude: lat, longitude: lng } = pos.coords;
      const ok = { kind: 'ok' as const, lat, lng, accuracy: pos.coords.accuracy ?? null, address: null, addressLoading: true };
      setState(ok);
      endpoints.reverseGeocode(lat, lng).then((r) => {
        setState((s) => (s.kind === 'ok' && s.lat === lat && s.lng === lng ? { ...s, address: r.result, addressLoading: false } : s));
      }).catch(() => setState((s) => (s.kind === 'ok' && s.lat === lat && s.lng === lng ? { ...s, addressLoading: false } : s)));
      return ok;
    } catch (e: any) { setState({ kind: 'error', message: e?.message ?? 'Could not get your location.' }); return null; }
  }, []);
  return { state, request, clear: () => setState({ kind: 'none' }) };
}

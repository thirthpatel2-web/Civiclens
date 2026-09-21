// Notifications: permission with explanation, push-token registration, and local alerts for new server notifications.
import { useCallback, useEffect, useRef } from 'react';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { endpoints } from '../api/instance.ts';

Notifications.setNotificationHandler({ handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: false, shouldSetBadge: false }) });

export async function enableNotifications(): Promise<'granted' | 'denied' | 'unavailable'> {
  const cur = await Notifications.getPermissionsAsync();
  const perm = cur.granted ? cur : await Notifications.requestPermissionsAsync(); // shown after the screen explains why
  if (!perm.granted) return 'denied';
  if (Platform.OS === 'android') await Notifications.setNotificationChannelAsync('default', { name: 'Complaint updates', importance: Notifications.AndroidImportance.DEFAULT });
  try {
    const projectId = (Constants.expoConfig?.extra as any)?.eas?.projectId ?? (Constants as any).easConfig?.projectId;
    const token = await Notifications.getExpoPushTokenAsync(projectId ? { projectId } : undefined);
    await endpoints.registerPushDevice(token.data, Platform.OS);
    return 'granted';
  } catch { return 'unavailable'; } // e.g. no EAS project / no push service: local alerts still work
}

/** While the app is open, poll for new notifications and raise a local alert for each unseen one. */
export function useNotificationAlerts(enabled: boolean, intervalMs = 30000) {
  const seen = useRef<Set<string>>(new Set());
  const primed = useRef(false);
  const poll = useCallback(async () => {
    try {
      const { items } = await endpoints.notifications();
      for (const n of items) {
        if (!primed.current) { seen.current.add(n.id); continue; } // don't alert for history on first load
        if (!n.read_at && !seen.current.has(n.id)) { seen.current.add(n.id); await Notifications.scheduleNotificationAsync({ content: { title: n.title, body: n.body }, trigger: null }); }
      }
      primed.current = true;
    } catch { /* offline: try again next tick */ }
  }, []);
  useEffect(() => { if (!enabled) return; poll(); const id = setInterval(poll, intervalMs); return () => clearInterval(id); }, [enabled, poll, intervalMs]);
}

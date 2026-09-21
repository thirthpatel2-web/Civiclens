// CivicLens - Event-Driven Notification Service (custom backend)
//
// Real-time push now happens via a plain WebSocket connection to the
// server (server/src/ws/realtime.js), which relays Postgres LISTEN/NOTIFY
// events — the direct, self-hosted replacement for Supabase Realtime.

import { apiRequest, openRealtimeSocket, isBackendConfigured } from './apiClient';

export async function loadNotifications(citizenId, limit = 30) {
  if (!citizenId || !isBackendConfigured) return [];
  const { data, error } = await apiRequest(`/notifications?limit=${limit}`);
  if (error) {
    console.log('loadNotifications error:', error);
    return [];
  }
  return data?.notifications || [];
}

export async function markNotificationRead(notificationId) {
  if (!isBackendConfigured) return { success: false };
  const { error } = await apiRequest(`/notifications/${notificationId}/read`, { method: 'PATCH' });
  return { success: !error, error };
}

/**
 * Subscribes to real-time notification pushes for this citizen. Returns
 * an unsubscribe function — same shape as the old Supabase version so
 * callers (HomeScreen.js) didn't need to change.
 */
export function subscribeToNotifications(citizenId, onNewNotification) {
  if (!citizenId || !isBackendConfigured) return () => {};

  let unsubscribed = false;
  let cleanup = () => {};

  openRealtimeSocket((message) => {
    if (message.type === 'notification' && message.data?.citizen_id === citizenId) {
      onNewNotification(message.data);
    }
  }).then((unsub) => {
    if (unsubscribed) unsub();
    else cleanup = unsub;
  });

  return () => {
    unsubscribed = true;
    cleanup();
  };
}

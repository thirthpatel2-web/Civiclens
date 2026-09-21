// CivicLens - API Client (replaces @supabase/supabase-js entirely)
//
// Talks to the custom Express + Postgres backend in /server. Handles
// attaching the JWT (stored in AsyncStorage after login) to every
// request, and exposes a small WebSocket helper for real-time
// notifications — the direct replacements for what supabase-js used to
// do automatically.

import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';

const extra = Constants.expoConfig?.extra || Constants.manifest?.extra || {};
export const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_URL || extra.apiBaseUrl || 'http://localhost:4000';

export const isBackendConfigured = Boolean(
  API_BASE_URL && !API_BASE_URL.includes('YOUR-SERVER')
);

const TOKEN_KEY = '@civiclens_auth_token_v1';

export async function getToken() {
  return AsyncStorage.getItem(TOKEN_KEY);
}

export async function setToken(token) {
  if (token) {
    await AsyncStorage.setItem(TOKEN_KEY, token);
  } else {
    await AsyncStorage.removeItem(TOKEN_KEY);
  }
}

/**
 * Core request helper. Every service file in src/services/ calls this
 * instead of supabase.from(...) — same role, plain HTTP underneath.
 */
export async function apiRequest(path, { method = 'GET', body, auth = true } = {}) {
  if (!isBackendConfigured) {
    return { data: null, error: 'Backend server URL is not configured. Set EXPO_PUBLIC_API_URL or app.json -> expo.extra.apiBaseUrl.' };
  }

  const headers = { 'Content-Type': 'application/json' };
  if (auth) {
    const token = await getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const json = await response.json().catch(() => ({}));
    if (!response.ok) {
      return { data: null, error: json.error || `Request failed (${response.status})`, status: response.status, raw: json };
    }
    return { data: json, error: null };
  } catch (err) {
    return { data: null, error: err.message || 'Network request failed.' };
  }
}

/**
 * Phase 3: same role as apiRequest, but sends multipart/form-data
 * instead of JSON — needed for the one endpoint that now accepts a
 * binary file (POST /complaints with an evidence photo). Every other
 * endpoint keeps using apiRequest unchanged.
 *
 * `fields` is a plain object of form fields (arrays/objects are
 * JSON.stringified — server/src/routes/complaints.js parses them back
 * on that side). `file`, if provided, is a { uri, name, type } object
 * as returned by expo-image-picker's result.assets[0].
 */
export async function apiRequestMultipart(path, { method = 'POST', fields = {}, file, fileFieldName = 'image', auth = true } = {}) {
  if (!isBackendConfigured) {
    return { data: null, error: 'Backend server URL is not configured. Set EXPO_PUBLIC_API_URL or app.json -> expo.extra.apiBaseUrl.' };
  }

  const headers = {};
  if (auth) {
    const token = await getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const formData = new FormData();
  Object.entries(fields).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    formData.append(key, typeof value === 'object' ? JSON.stringify(value) : String(value));
  });
  if (file?.uri) {
    formData.append(fileFieldName, {
      uri: file.uri,
      name: file.name || `evidence.${(file.type || 'image/jpeg').split('/')[1] || 'jpg'}`,
      type: file.type || 'image/jpeg',
    });
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers, // deliberately no Content-Type — fetch sets the multipart boundary itself
      body: formData,
    });
    const json = await response.json().catch(() => ({}));
    if (!response.ok) {
      return { data: null, error: json.error || `Request failed (${response.status})`, status: response.status, raw: json };
    }
    return { data: json, error: null };
  } catch (err) {
    return { data: null, error: err.message || 'Network request failed.' };
  }
}

/**
 * Opens a WebSocket connection to the server's realtime relay
 * (server/src/ws/realtime.js), authenticated with the current JWT.
 * Returns an unsubscribe function, mirroring the shape
 * notificationService.js's callers already expect from the old
 * Supabase Realtime version.
 */
export async function openRealtimeSocket(onMessage) {
  if (!isBackendConfigured) return () => {};
  const token = await getToken();
  if (!token) return () => {};

  const wsUrl = API_BASE_URL.replace(/^http/, 'ws') + `/ws?token=${encodeURIComponent(token)}`;
  let ws;
  try {
    ws = new WebSocket(wsUrl);
  } catch (err) {
    console.log('Realtime socket failed to open:', err.message);
    return () => {};
  }

  ws.onmessage = (event) => {
    try {
      const parsed = JSON.parse(event.data);
      onMessage(parsed);
    } catch (err) {
      console.log('Realtime message parse error:', err.message);
    }
  };
  ws.onerror = (err) => console.log('Realtime socket error:', err.message);

  return () => {
    try {
      ws.close();
    } catch (err) {}
  };
}

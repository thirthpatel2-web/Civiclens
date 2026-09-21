// CivicLens - Authentication Service (custom backend, not Supabase Auth)
//
// One real difference from the old Supabase version worth knowing: our
// own magic-link flow can't deep-link back into the app the way an email
// client tapping a URL could, so it's implemented as a one-time 6-digit
// code emailed to the user instead — same security idea (something sent
// to your email proves you own it), different UX (enter a code, not tap
// a link). See sendMagicLinkCode / verifyMagicLinkCode below.

import { apiRequest, setToken, isBackendConfigured } from './apiClient';

export const backendReady = isBackendConfigured;

export async function signUpWithPassword({ email, password, fullName }) {
  const { data, error } = await apiRequest('/auth/signup', { method: 'POST', body: { email, password, fullName }, auth: false });
  if (error) return { user: null, session: null, error };
  await setToken(data.token);
  return { user: data.user, session: { user: data.user }, error: null };
}

export async function signInWithPassword({ email, password }) {
  const { data, error } = await apiRequest('/auth/login', { method: 'POST', body: { email, password }, auth: false });
  if (error) return { user: null, session: null, error };

  // Account has MFA enabled — no session yet, the caller must collect a
  // TOTP code and call verifyMfaLogin() before a real session exists.
  if (data.mfaRequired) {
    return { user: data.user, session: null, mfaRequired: true, pendingToken: data.pendingToken, error: null };
  }

  await setToken(data.token);
  return { user: data.user, session: { user: data.user }, mfaSetupRequired: data.mfaSetupRequired, error: null };
}

/** Completes sign-in for an account with MFA enabled, given the
 *  pendingToken from signInWithPassword() and a code from the user's
 *  authenticator app. */
export async function verifyMfaLogin({ pendingToken, token }) {
  const { data, error } = await apiRequest('/auth/mfa/verify-login', { method: 'POST', body: { pendingToken, token }, auth: false });
  if (error) return { user: null, session: null, error };
  await setToken(data.token);
  return { user: data.user, session: { user: data.user }, error: null };
}

/** Starts MFA setup for the signed-in user — returns a QR code data URL
 *  to display (e.g. in a modal/popup) and the raw secret as a manual
 *  fallback for authenticator apps that can't scan. */
export async function setupMfa() {
  const { data, error } = await apiRequest('/auth/mfa/setup', { method: 'POST' });
  if (error) return { qrCodeDataUrl: null, secret: null, error };
  return { qrCodeDataUrl: data.qrCodeDataUrl, secret: data.secret, error: null };
}

/** Verifies the first code and turns MFA on for the signed-in user. */
export async function enableMfa(token) {
  const { error } = await apiRequest('/auth/mfa/enable', { method: 'POST', body: { token } });
  return { success: !error, error };
}

/** Requests a 6-digit sign-in code be emailed to this address. */
export async function sendMagicLinkCode(email) {
  const { data, error } = await apiRequest('/auth/magic-link/request', { method: 'POST', body: { email }, auth: false });
  return { error, devFallback: data?.devFallback };
}

/** Verifies the code from sendMagicLinkCode and completes sign-in. */
export async function verifyMagicLinkCode({ email, code }) {
  const { data, error } = await apiRequest('/auth/magic-link/verify', { method: 'POST', body: { email, code }, auth: false });
  if (error) return { user: null, session: null, error };
  await setToken(data.token);
  return { user: data.user, session: { user: data.user }, error: null };
}

export async function getCurrentSession() {
  const { data, error } = await apiRequest('/auth/me', { method: 'GET' });
  if (error || !data?.profile) return null;
  return { user: { id: data.profile.id } };
}

// No server-push auth state change mechanism (that was a Supabase SDK
// convenience) — AppContext instead re-checks the session on mount and
// after explicit sign-in/sign-out calls. Kept as a no-op subscription so
// existing callers don't need restructuring.
export function onAuthStateChange() {
  return { unsubscribe() {} };
}

export async function signOut() {
  await setToken(null);
  return { error: null };
}

export async function fetchProfile(userId) {
  const { data, error } = await apiRequest('/profiles/me', { method: 'GET' });
  return { profile: data?.profile || null, error };
}

export async function upsertProfile(userId, fields) {
  const { data, error } = await apiRequest('/profiles/me', {
    method: 'PATCH',
    body: {
      fullName: fields.full_name,
      phone: fields.phone,
      address: fields.address,
      city: fields.city,
      pincode: fields.pincode,
      role: fields.role,
      departmentId: fields.department_id,
      officerId: fields.officer_id,
      designation: fields.designation,
      jurisdiction: fields.jurisdiction,
    },
  });
  return { profile: data?.profile || null, error };
}

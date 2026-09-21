// CivicLens - Master Data Management (Golden Record) Service (custom backend)
// ID hashing still happens on-device before anything is transmitted —
// only the server changed, not the privacy design.

import * as Crypto from 'expo-crypto';
import { apiRequest, isBackendConfigured } from './apiClient';

export const ID_SYSTEMS = [
  { id: 'aadhaar_ref', label: 'Aadhaar (reference only, never the full number)' },
  { id: 'pan', label: 'PAN' },
  { id: 'voter_id', label: 'Voter ID (EPIC)' },
  { id: 'ration_card', label: 'Ration Card Number' },
  { id: 'driving_license', label: 'Driving Licence Number' },
  { id: 'other', label: 'Other Government ID' },
];

async function hashIdValue(rawValue) {
  return Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, rawValue.trim().toUpperCase());
}

export async function loadLinkedExternalIds(citizenId) {
  if (!citizenId || !isBackendConfigured) return [];
  const { data, error } = await apiRequest('/master-data');
  if (error) {
    console.log('loadLinkedExternalIds error:', error);
    return [];
  }
  return data?.links || [];
}

export async function linkExternalId(citizenId, idSystem, rawIdValue) {
  if (!citizenId || !isBackendConfigured) {
    return { success: false, error: 'Sign in with a real account to link identity documents.' };
  }
  const idValueHash = await hashIdValue(rawIdValue);
  const { data, error, status } = await apiRequest('/master-data', { method: 'POST', body: { idSystem, idValueHash } });
  if (error) return { success: false, error, conflict: status === 409 };
  return { success: true, link: data.link };
}

export async function resolveGoldenRecord(idSystem, rawIdValue) {
  if (!isBackendConfigured) return null;
  const idValueHash = await hashIdValue(rawIdValue);
  const { data, error } = await apiRequest(`/master-data/resolve/${idSystem}/${idValueHash}`);
  if (error) return null;
  return data?.citizenId || null;
}

export async function unlinkExternalId(linkId) {
  if (!isBackendConfigured) return { success: false, error: 'Backend not configured.' };
  const { error } = await apiRequest(`/master-data/${linkId}`, { method: 'DELETE' });
  if (error) return { success: false, error };
  return { success: true };
}

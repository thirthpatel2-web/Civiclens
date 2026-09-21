// CivicLens - Consent-Based Data Sharing Service (custom backend)
import { apiRequest, isBackendConfigured } from './apiClient';

export const DATA_SCOPE_OPTIONS = [
  { id: 'name', label: 'Full Name' },
  { id: 'phone', label: 'Phone Number' },
  { id: 'email', label: 'Email' },
  { id: 'address', label: 'Address' },
  { id: 'filing_history', label: 'Filing History with this Department' },
];

export async function loadConsentGrants(citizenId) {
  if (!citizenId || !isBackendConfigured) return [];
  const { data, error } = await apiRequest('/consent');
  if (error) {
    console.log('loadConsentGrants error:', error);
    return [];
  }
  return data?.grants || [];
}

export async function grantConsent(citizenId, departmentId, dataScope) {
  if (!citizenId || !isBackendConfigured) {
    return { success: false, error: 'Sign in with a real account to manage consent.' };
  }
  const { data, error } = await apiRequest('/consent', { method: 'POST', body: { departmentId, dataScope } });
  if (error) return { success: false, error };
  return { success: true, grant: data.grant };
}

export async function revokeConsent(grantId) {
  if (!isBackendConfigured) return { success: false, error: 'Backend not configured.' };
  const { data, error } = await apiRequest(`/consent/${grantId}/revoke`, { method: 'PATCH' });
  if (error) return { success: false, error };
  return { success: true, grant: data.grant };
}

export async function hasActiveConsent(citizenId, departmentId, scopeField) {
  if (!isBackendConfigured) return false;
  const { data, error } = await apiRequest(`/consent/check/${citizenId}/${departmentId}/${scopeField}`);
  if (error) return false;
  return !!data?.hasConsent;
}

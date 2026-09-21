// CivicLens - External Service Links Service (custom backend)
import { apiRequest, isBackendConfigured } from './apiClient';

const KNOWN_SYSTEMS = [
  { id: 'cpgrams', label: 'CPGRAMS (Central Grievance Portal)', url: 'https://pgportal.gov.in/status' },
  { id: 'state_portal', label: 'State Grievance Portal', url: '' },
  { id: 'scheme_application', label: 'Government Scheme Application', url: '' },
  { id: 'umang', label: 'UMANG App Service', url: 'https://web.umang.gov.in/' },
  { id: 'other', label: 'Other Government Portal', url: '' },
];

export function getKnownExternalSystems() {
  return KNOWN_SYSTEMS;
}

export async function loadExternalLinks(userId) {
  if (!userId || !isBackendConfigured) return [];
  const { data, error } = await apiRequest('/external-links');
  if (error) {
    console.log('loadExternalLinks error:', error);
    return [];
  }
  return data?.links || [];
}

export async function addExternalLink(userId, { systemName, referenceNumber, portalUrl, description }) {
  if (!userId || !isBackendConfigured) {
    return { success: false, error: 'Sign in with a real account (not Guest Mode) to track external references.' };
  }
  const { data, error } = await apiRequest('/external-links', {
    method: 'POST',
    body: { systemName, referenceNumber, portalUrl, description },
  });
  if (error) return { success: false, error };
  return { success: true, link: data.link };
}

export async function deleteExternalLink(linkId) {
  if (!isBackendConfigured) return { success: false, error: 'Backend not configured.' };
  const { error } = await apiRequest(`/external-links/${linkId}`, { method: 'DELETE' });
  return { success: !error, error };
}

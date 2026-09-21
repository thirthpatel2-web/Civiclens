// CivicLens - Integration Exception Handling Service (custom backend)
import { apiRequest, isBackendConfigured } from './apiClient';

export async function logIntegrationException({ sourceSystem, rawPayload, errorMessage }) {
  if (!isBackendConfigured) {
    console.log('Integration exception (not persisted, backend not configured):', errorMessage);
    return { success: false };
  }
  const { error } = await apiRequest('/exceptions', { method: 'POST', body: { sourceSystem, rawPayload, errorMessage }, auth: false });
  if (error) console.log('logIntegrationException failed:', error);
  return { success: !error };
}

export async function loadOpenExceptions() {
  if (!isBackendConfigured) return [];
  const { data, error } = await apiRequest('/exceptions/open');
  if (error) {
    console.log('loadOpenExceptions error:', error);
    return [];
  }
  return data?.exceptions || [];
}

export async function resolveException(exceptionId, userId, resolution = 'resolved') {
  if (!isBackendConfigured) return { success: false, error: 'Backend not configured.' };
  const { error } = await apiRequest(`/exceptions/${exceptionId}/resolve`, { method: 'PATCH', body: { resolution } });
  return { success: !error, error };
}

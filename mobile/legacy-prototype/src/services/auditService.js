// CivicLens - Audit Log Service (custom backend)
// Entries are written automatically by Postgres triggers on the server
// (see server/src/db/schema.sql) — this just reads them back.
import { apiRequest, isBackendConfigured } from './apiClient';

export async function loadMyAuditTrail(userId, limit = 50) {
  if (!userId || !isBackendConfigured) return [];
  const { data, error } = await apiRequest(`/audit?limit=${limit}`);
  if (error) {
    console.log('loadMyAuditTrail error:', error);
    return [];
  }
  return data?.entries || [];
}

// CivicLens - Real Civic Heatmap Data Service (custom backend)
//
// Previously src/data/heatmapData.js contained entirely fabricated
// statistics (invented total-complaint counts, invented "civic health
// scores", invented ward names, invented officer names like "AEE
// Srikanth", invented upvote counts) presented as if they were real
// municipal data. That was replaced with a genuine aggregation of
// complaints citizens actually filed — and the aggregation itself now
// runs server-side (server/src/routes/complaints.js ->
// GET /complaints/city/:cityId/summary), which only returns counts and
// categories, never raw complaint text or citizen contact info, since
// this is intentionally a public endpoint with no login required.

import { apiRequest, isBackendConfigured } from './apiClient';

export const CATEGORY_METADATA = {
  'Roads & Potholes': { icon: '🛣️', color: '#C24545' },
  'Water & Sewage': { icon: '💧', color: '#3B8FA8' },
  Electricity: { icon: '⚡', color: '#BF6B3D' },
  Sanitation: { icon: '🗑️', color: '#2E9E63' },
  Encroachment: { icon: '🏗️', color: '#7A5FB0' },
  Other: { icon: '📋', color: '#64748B' },
};

/**
 * Returns a real aggregation for a city — or a `hasData: false` flag when
 * there's nothing filed yet / backend isn't connected, so the UI can show
 * an honest empty state instead of fabricated numbers.
 */
export async function loadCityHeatmapSummary(cityId) {
  if (!isBackendConfigured) {
    return { hasData: false, backendConnected: false };
  }
  const { data, error } = await apiRequest(`/complaints/city/${cityId}/summary`, { auth: false });
  if (error) {
    return { hasData: false, backendConnected: true, error };
  }
  return { backendConnected: true, ...data };
}

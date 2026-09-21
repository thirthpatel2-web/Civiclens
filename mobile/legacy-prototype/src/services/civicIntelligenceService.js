// CivicLens - Civic Intelligence Service (RAG Assistant, Documents,
// Dashboards, Anomalies, Investigation Mode)
//
// Thin wrapper over the new backend routes built in server/src/routes/
// (assistant.js, documents.js, dashboards.js, intelligence.js).

import { apiRequest } from './apiClient';

// ---- AI Civic Assistant (grounded RAG) -----------------------------------
export async function askCivicAssistant(query, { ward, department, documentType, lang } = {}) {
  const { data, error } = await apiRequest('/assistant/ask', {
    method: 'POST',
    body: { query, ward, department, documentType, lang },
  });
  if (error) return { answer: null, error };
  return { ...data, error: null };
}

// ---- Document Search & Upload (officials) --------------------------------
export async function searchDocuments(query, filters = {}) {
  const { data, error } = await apiRequest('/documents/search', { method: 'POST', body: { query, ...filters } });
  return { results: data?.results || [], stats: data?.stats, error };
}

export async function listDocuments(filters = {}) {
  const params = new URLSearchParams(filters).toString();
  const { data, error } = await apiRequest(`/documents${params ? `?${params}` : ''}`);
  return { documents: data?.documents || [], error };
}

export async function getDocumentStatus(documentId) {
  const { data, error } = await apiRequest(`/documents/${documentId}/status`);
  return { status: data, error };
}

// ---- Dashboards -----------------------------------------------------------
export async function getWardDashboard(wardId, weights = {}) {
  const params = new URLSearchParams(weights).toString();
  const { data, error } = await apiRequest(`/dashboards/ward/${wardId}${params ? `?${params}` : ''}`);
  return { dashboard: data, error };
}

export async function getDepartmentDashboard(deptId, dateFrom, dateTo) {
  const params = new URLSearchParams({ ...(dateFrom && { dateFrom }), ...(dateTo && { dateTo }) }).toString();
  const { data, error } = await apiRequest(`/dashboards/department/${deptId}${params ? `?${params}` : ''}`);
  return { dashboard: data, error };
}

export async function getBudgetTransparency(ward, category, fiscalYear) {
  const params = new URLSearchParams({ ward, ...(category && { category }), ...(fiscalYear && { fiscalYear }) }).toString();
  const { data, error } = await apiRequest(`/dashboards/budget?${params}`);
  return { budget: data, error };
}

export async function getDelayedProjects(ward, department) {
  const params = new URLSearchParams({ ...(ward && { ward }), ...(department && { department }) }).toString();
  const { data, error } = await apiRequest(`/dashboards/budget/delayed-projects${params ? `?${params}` : ''}`);
  return { delayedProjects: data?.delayedProjects || [], error };
}

export async function compareWards(wardA, wardB, category) {
  const params = new URLSearchParams({ wardA, wardB, ...(category && { category }) }).toString();
  const { data, error } = await apiRequest(`/dashboards/budget/compare-wards?${params}`);
  return { comparison: data, error };
}

// ---- Advanced Intelligence ------------------------------------------------
export async function getAnomalies() {
  const { data, error } = await apiRequest('/intelligence/anomalies');
  return { anomalies: data, error };
}

export async function predictComplaintVolume(ward, category, weeksAhead = 1) {
  const params = new URLSearchParams({ ward, ...(category && { category }), weeksAhead: String(weeksAhead) }).toString();
  const { data, error } = await apiRequest(`/intelligence/predict/complaints?${params}`);
  return { prediction: data, error };
}

export async function getSlaOverloadRisk() {
  const { data, error } = await apiRequest('/intelligence/predict/sla-overload');
  return { risks: data?.risks || [], error };
}

export async function investigateProject(projectIdOrCode) {
  const { data, error } = await apiRequest(`/intelligence/investigate/${encodeURIComponent(projectIdOrCode)}`);
  return { investigation: data, error };
}

// ---- Complaint Intelligence (classification review, duplicates, SLA) ----
export async function overrideClassification(complaintId, fields) {
  const { data, error } = await apiRequest(`/complaints/${complaintId}/classification`, { method: 'PATCH', body: fields });
  return { complaint: data?.complaint, error };
}

export async function getComplaintDuplicates(complaintId) {
  const { data, error } = await apiRequest(`/complaints/${complaintId}/duplicates`);
  return { relationships: data?.relationships || [], error };
}

export async function reviewDuplicateRelationship(relationshipId, decision) {
  const { data, error } = await apiRequest(`/complaints/relationships/${relationshipId}/review`, { method: 'PATCH', body: { decision } });
  return { relationship: data?.relationship, error };
}

export async function getComplaintSla(complaintId) {
  const { data, error } = await apiRequest(`/complaints/${complaintId}/sla`);
  return { sla: data, error };
}

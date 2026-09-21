// CivicLens - Grievance Tracking Service (custom backend, not Supabase)
//
// Canonical complaint shape stays identical to before — only the
// transport changed (REST calls to /complaints instead of
// supabase.from('complaints')). See server/src/routes/complaints.js for
// the matching backend side.

import AsyncStorage from '@react-native-async-storage/async-storage';
import { apiRequest, apiRequestMultipart, isBackendConfigured, API_BASE_URL } from './apiClient';

const STORAGE_KEY = '@civiclens_complaints_v4';

function rowToComplaint(row) {
  return {
    id: row.id,
    referenceCode: row.reference_code,
    type: row.type,
    title: row.title,
    category: row.category,
    department: row.department_name,
    departmentId: row.department_id,
    city: row.city,
    issue: row.issue_text,
    letterText: row.letter_text,
    targetEmail: row.target_email,
    citizenPhone: row.citizen_phone,
    citizenEmail: row.citizen_email,
    citizenName: row.citizen_name,
    status: row.status,
    stage: row.stage,
    slaDays: row.sla_days,
    officer: row.officer,
    officerRemarks: row.officer_remarks,
    atrFile: row.atr_file_name,
    timeline: row.timeline || [],
    notes: row.notes || [],
    history: row.history || [],
    canEscalate: row.can_escalate,
    dateFiled: row.created_at,
    updatedAt: row.updated_at,
    // AI intelligence fields. The backend computes and stores these on
    // POST /complaints (best-effort — they are absent if Ollama was down,
    // or if an official has not reviewed them yet). They were previously
    // dropped here, so the data never reached the UI at all.
    aiClassification: row.ai_classification || null,
    priority: row.priority || null,
    severity: row.severity || null,
    priorityReasoning: row.priority_reasoning || null,
    aiClassificationConfirmed: row.ai_classification_confirmed || false,
    duplicateRelationships: row._duplicateRelationships ?? null,
    // Phase 3 — evidence photo + precise location. image_url is a path
    // relative to the API server (e.g. "/uploads/complaints/xyz.jpg");
    // screens that display it prepend API_BASE_URL — see
    // resolveComplaintImageUrl below.
    imageUrl: row.image_url || null,
    imageOriginalName: row.image_original_name || null,
    address: row.address || null,
    wardNumber: row.ward_number || null,
    lat: row.lat ?? null,
    lng: row.lng ?? null,
    // SLA / escalation fields (Phase 4 additions) — already computed and
    // stored server-side by the existing SLA triggers/sweep (see
    // server/src/services/slaEscalation.js); just weren't reaching the
    // UI before because this mapper dropped them.
    slaDueAt: row.sla_due_at || null,
    escalationLevel: row.escalation_level ?? 0,
    escalatedAt: row.escalated_at || null,
  };
}

/**
 * image_url from the backend is a relative path (never a full URL —
 * the same complaint can be viewed through different tunnels/hosts
 * over its lifetime, e.g. a changing ngrok URL during development), so
 * screens resolve it against the current API_BASE_URL right before
 * display rather than baking a host into the stored value.
 */
export const resolveComplaintImageUrl = (imageUrl) => {
  if (!imageUrl) return null;
  if (/^https?:\/\//i.test(imageUrl)) return imageUrl;
  return `${API_BASE_URL}${imageUrl}`;
};

async function loadLocalComplaints() {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
}

async function saveLocalComplaints(list) {
  try {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch (e) {
    console.log('Error caching complaints locally:', e.message);
  }
}

export const loadComplaints = async (userId = null) => {
  if (userId && isBackendConfigured) {
    const { data, error } = await apiRequest('/complaints');
    if (!error && data?.complaints) {
      const mapped = data.complaints.map(rowToComplaint);
      await saveLocalComplaints(mapped);
      return mapped;
    }
    console.log('Backend loadComplaints fallback to cache:', error);
  }
  return loadLocalComplaints();
};

export const saveNewComplaint = async (complaint, userId = null) => {
  if (userId && isBackendConfigured) {
    // Phase 3 — a complaint's evidence photo (complaint.imageAsset, set
    // by ComplaintScreen from expo-image-picker) means this has to go
    // as multipart/form-data instead of JSON; everything else about
    // the request is identical. No image -> the original JSON path,
    // completely unchanged.
    const fields = {
      type: complaint.type || 'civic',
      title: complaint.title,
      category: complaint.category,
      departmentId: complaint.departmentId,
      department: complaint.department,
      city: complaint.city,
      issue: complaint.issue,
      letterText: complaint.letterText,
      targetEmail: complaint.targetEmail,
      citizenPhone: complaint.citizenPhone,
      citizenEmail: complaint.citizenEmail,
      citizenName: complaint.citizenName,
      status: complaint.status,
      stage: complaint.stage,
      slaDays: complaint.slaDays,
      timeline: complaint.timeline,
      notes: complaint.notes,
      history: complaint.history,
      canEscalate: complaint.canEscalate,
      // Phase 3 — precise location
      address: complaint.address,
      wardNumber: complaint.wardNumber,
      lat: complaint.lat,
      lng: complaint.lng,
    };

    const { data, error } = complaint.imageAsset
      ? await apiRequestMultipart('/complaints', { fields, file: complaint.imageAsset })
      : await apiRequest('/complaints', { method: 'POST', body: fields });

    if (!error && data?.complaint) {
      const saved = rowToComplaint(data.complaint);
      const existing = await loadLocalComplaints();
      await saveLocalComplaints([saved, ...existing]);
      return { success: true, complaint: saved };
    }
    console.log('Backend saveNewComplaint failed, saving locally only:', error);
  }

  const existing = await loadLocalComplaints();
  const updated = [complaint, ...existing];
  await saveLocalComplaints(updated);
  return { success: true, complaint, offlineOnly: !userId || !isBackendConfigured };
};

export const addNoteToComplaint = async (complaintId, noteText, userId = null) => {
  const stamp = `${new Date().toLocaleDateString('en-IN')}: ${noteText}`;

  if (userId && isBackendConfigured) {
    const { data, error } = await apiRequest(`/complaints/${complaintId}/note`, { method: 'PATCH', body: { note: noteText } });
    if (!error && data?.complaint) {
      const updated = rowToComplaint(data.complaint);
      const local = await loadLocalComplaints();
      const updatedLocal = local.map((c) => (c.id === complaintId ? updated : c));
      await saveLocalComplaints(updatedLocal);
      return { success: true, complaints: updatedLocal };
    }
    console.log('Backend addNoteToComplaint failed, falling back to local cache.');
  }

  const existing = await loadLocalComplaints();
  const updated = existing.map((c) => (c.id === complaintId ? { ...c, notes: [...(c.notes || []), stamp] } : c));
  await saveLocalComplaints(updated);
  return { success: true, complaints: updated };
};

export const updateComplaintStatusRemote = async (complaintId, fields) => {
  if (!isBackendConfigured) return { success: false, error: 'Backend not configured yet.' };
  // `stage` and `history` are no longer sent — the server now computes
  // `stage` from `status` and builds the history entry itself (see
  // PATCH /complaints/:id/status), so a client can no longer overwrite
  // another officer's prior history by passing its own array here.
  const { data, error } = await apiRequest(`/complaints/${complaintId}/status`, {
    method: 'PATCH',
    body: {
      status: fields.status,
      officer: fields.officer,
      officerRemarks: fields.officer_remarks,
      atrFileName: fields.atr_file_name,
    },
  });
  if (error) return { success: false, error };
  return { success: true, complaint: rowToComplaint(data.complaint) };
};

export const loadDepartmentQueue = async (departmentId) => {
  if (!isBackendConfigured) return [];
  const { data, error } = await apiRequest(`/complaints/department/${departmentId}`);
  if (error) {
    console.log('loadDepartmentQueue error:', error);
    return [];
  }
  return (data?.complaints || []).map(rowToComplaint);
};

/** Officer dashboard summary counts (total/pending/in-progress/resolved/
 *  escalated) for the officer's own department — computed server-side
 *  from real DB values (server/src/services/sqlQueries.js), never
 *  invented client-side. See GET /dashboards/department/:deptId. */
export const loadDepartmentDashboard = async (departmentId) => {
  const { data, error } = await apiRequest(`/dashboards/department/${departmentId}`);
  if (error) return { success: false, error };
  return { success: true, stats: data.stats, categoryBreakdown: data.categoryBreakdown, weeklyTrend: data.weeklyTrend };
};

/** Full detail for one complaint — used by both the citizen tracking
 *  screen and the officer portal's detail view. The server enforces who
 *  may see it (owning citizen, or an official of the routed department). */
export const loadComplaintDetail = async (complaintId) => {
  const { data, error } = await apiRequest(`/complaints/${complaintId}`);
  if (error) return { success: false, error };
  return { success: true, complaint: rowToComplaint(data.complaint), slaStatus: data.slaStatus };
};

/** Merged update log (status changes + officer notes, with remarks text)
 *  and the DB-trigger-written audit trail for one complaint. */
export const loadComplaintHistory = async (complaintId) => {
  const { data, error } = await apiRequest(`/complaints/${complaintId}/history`);
  if (error) return { success: false, error };
  return { success: true, updateLog: data.updateLog || [], auditTrail: data.auditTrail || [] };
};

/** Officer adds an investigation/action-taken note WITHOUT changing the
 *  complaint's status — see server's POST /complaints/:id/updates. */
export const addOfficerUpdate = async (complaintId, note) => {
  const { data, error } = await apiRequest(`/complaints/${complaintId}/updates`, { method: 'POST', body: { note } });
  if (error) return { success: false, error };
  return { success: true, complaint: rowToComplaint(data.complaint) };
};

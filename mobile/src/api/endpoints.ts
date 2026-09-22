import { Platform } from 'react-native';
import type { ApiClient } from './client.ts';
import type * as T from './types.ts';
import type { LanguageCode } from '../i18n/languages.ts';

/** One function per backend endpoint; screens and the sync engine depend on this, never on raw fetch. */
export function createEndpoints(api: ApiClient) {
  const fileForm = async (fieldName: string, file: T.LocalFile, fields: Record<string, string> = {}) => {
    const fd = new FormData();
    for (const [k, v] of Object.entries(fields)) fd.append(k, v);
    if (Platform.OS === 'web') {
      // React Native's { uri, name, type } object trick only works through RN's native FormData bridge.
      // On web, FormData is the browser's real implementation, which needs an actual Blob/File part -
      // file.uri here is a blob: URL (from expo-audio's recorder or an <input type=file>), so fetch it back.
      const blob = await (await fetch(file.uri)).blob();
      fd.append(fieldName, blob, file.name);
    } else {
      fd.append(fieldName, { uri: file.uri, name: file.name, type: file.type } as any);
    }
    return fd;
  };
  return {
    register: (email: string, password: string, full_name: string) => api.post<{ id: string }>('/auth/register', { email, password, full_name }, { auth: false }),
    login: (email: string, password: string, otp?: string) => api.post<T.LoginResponse>('/auth/mobile/login', { email, password, otp: otp || null }, { auth: false }),
    logout: () => api.post<{ ok: boolean }>('/auth/logout'),
    me: () => api.get<{ user: T.SessionUser; mfa_verified: boolean }>('/auth/me'),
    forgotPassword: (email: string) => api.post<{ message: string }>('/auth/password/forgot', { email }, { auth: false }),

    listComplaints: (filter = 'all') => api.get<{ items: T.Complaint[] }>('/complaints', { filter }),
    complaintDetail: (id: string) => api.get<T.ComplaintDetail>(`/complaints/${id}`),
    createComplaint: (body: T.ComplaintInput) => api.post<T.CreateComplaintResponse>('/complaints', body),
    classifyPreview: (title: string, description: string, ward?: string | null) => api.post<T.ClassifyPreview>('/complaints/classify-preview', { title, description, ward: ward || null }),
    uploadEvidence: async (file: T.LocalFile) => api.request<T.Evidence>('POST', '/complaints/evidence', { form: await fileForm('file', file), timeoutMs: 120000 }),
    feedback: (id: string, rating: number, comment: string | null) => api.post(`/complaints/${id}/feedback`, { rating, comment }),

    voiceLanguages: () => api.get<T.VoiceCapabilities>('/voice/languages'),
    // language: a code, or "auto" (only if the engine declares auto-detect). The result is in the SPOKEN language; it is never translated.
    transcribe: async (file: T.LocalFile, language: LanguageCode | 'auto') => api.request<T.VoiceResult>('POST', '/voice/transcribe', { form: await fileForm('audio', file, { language }), timeoutMs: 120000 }),

    ask: (question: string, language: LanguageCode, conversationId?: string | null) => api.post<T.AskResponse>('/assistant/ask', { question, language, conversation_id: conversationId ?? null }),
    assistantRoute: (text: string, ward?: string | null) => api.post<T.AssistantRouteResult>('/assistant/route', { text, ward: ward ?? null }),
    notifications: () => api.get<{ items: T.NotificationItem[]; unread: number }>('/notifications'),
    markRead: (id: string) => api.post(`/notifications/${id}/read`),
    registerPushDevice: (token: string, platform: string) => api.post('/notifications/devices', { token, platform }),
    helplines: (lang: string) => api.get<{ notice: string; items: T.Helpline[]; configured: boolean }>('/emergency/helplines', { lang }),
    radar: (q: { category?: string; ward?: string } = {}) => api.get<T.RadarResponse>('/gis/radar', q),
    createRti: (body: { subject: string; public_authority: string; questions: string[]; applicant_name: string; applicant_address: string; language?: string }) => api.post<T.RtiApplication>('/rti', body),
    generateRti: (id: string) => api.post<T.RtiApplication>(`/rti/${id}/generate`),
    fileRti: (id: string) => api.post<T.RtiApplication>(`/rti/${id}/file`, {}),
    rtiCategories: () => api.get<{ categories: T.RtiCategory[] }>('/rti/categories'),
    previewRtiQuestions: (body: { subject: string; category?: string | null; location?: string | null; records_requested?: string[]; tender_reference?: string | null; time_period?: string | null; custom_questions?: string[] }) =>
      api.post<T.RtiQuestionsPreview>('/rti/questions/preview', body),
    consents: () => api.get<Record<string, { granted: boolean }>>('/consent'),
    setConsent: (purpose: string, granted: boolean) => api.put(`/consent/${purpose}`, { granted }),
    listRti: () => api.get<{ items: T.RtiApplication[] }>('/rti'),
    analyzeLegal: (problem: string) => api.post<T.LegalAnalysis>('/legal/analyze', { problem }),
    profile: () => api.get<any>('/profiles/me'),
    updateProfile: (fields: { full_name?: string; phone?: string; city?: string; ward?: string; language?: string; complete_onboarding?: boolean }) => api.put<any>('/profiles/me', fields),

    // ---- officer / department -----------------------------------------------------------------
    departmentDashboard: () => api.get<T.DepartmentDashboard>('/dashboards/department'),
    officerQueue: (q: { mine_only?: boolean; status?: string | null } = {}) => api.get<{ items: T.OfficerQueueItem[] }>('/officer/queue', q),
    officerComplaintDetail: (id: string) => api.get<T.OfficerComplaintDetail>(`/officer/complaints/${id}`),
    setStatus: (id: string, status: string, remarks?: string) => api.post<T.OfficerComplaintDetail['complaint']>(`/officer/complaints/${id}/status`, { status, remarks: remarks || null }),
    resolveComplaint: (id: string, resolution_notes: string) => api.post(`/officer/complaints/${id}/resolve`, { resolution_notes }),
    remarkComplaint: (id: string, text: string, internal = true) => api.post(`/officer/complaints/${id}/remark`, { text, internal }),
    fieldVisit: (id: string, scheduled_for: string, notes?: string) => api.post(`/officer/complaints/${id}/field-visit`, { scheduled_for, notes: notes || null }),
    inspection: (id: string, findings: string, notes?: string) => api.post(`/officer/complaints/${id}/inspection`, { findings, notes: notes || null }),
    workOrder: (id: string, order_ref: string, description: string, team?: string) => api.post(`/officer/complaints/${id}/work-order`, { order_ref, description, team: team || null }),
    coordinationNote: (id: string, with_team: string, note: string) => api.post(`/officer/complaints/${id}/coordination`, { with_team, note }),
    progressUpdate: (id: string, percent: number, notes?: string) => api.post(`/officer/complaints/${id}/progress`, { percent, notes: notes || null }),
    escalate: (id: string, reason: string) => api.post(`/officer/complaints/${id}/escalate`, { reason }),
    correctCategory: (id: string, category: string) => api.post<T.OfficerQueueItem>(`/officer/complaints/${id}/category`, { category }),
    assign: (id: string, officer_id: string) => api.post(`/officer/complaints/${id}/assign`, { officer_id }),
    triage: (id: string, department_code: string) => api.post(`/officer/complaints/${id}/triage`, { department_code }),
    duplicateCandidates: (id: string) => api.get<{ items: T.DuplicateCandidate[] }>(`/officer/complaints/${id}/duplicates`),
    duplicateDecision: (id: string, other_complaint_id: string, decision: string, note?: string) => api.post(`/officer/complaints/${id}/duplicates/decision`, { other_complaint_id, decision, note: note || null }),
    governmentStates: (id: string) => api.get<{ items: T.GovernmentSubmissionState[] }>(`/complaints/${id}/government-submissions`),
    requestGovernmentSubmission: (id: string, platform: string) => api.post(`/complaints/${id}/government-submissions`, { platform }),
    officerGovernmentStates: (id: string) => api.get<{ items: T.GovernmentSubmissionState[] }>(`/officer/complaints/${id}/government-submissions`),
    officerRequestGovernmentSubmission: (id: string, platform: string) => api.post(`/officer/complaints/${id}/government-submissions`, { platform }),

    openInvestigation: (subject_type: string, subject_id: string) => api.post<T.Investigation>('/officer/investigations', { subject_type, subject_id }),
    listInvestigations: () => api.get<{ items: T.Investigation[] }>('/officer/investigations'),
    investigationReport: (id: string) => api.get<T.InvestigationReport>(`/officer/investigations/${id}`),
    addInvestigationNote: (id: string, text: string) => api.post(`/officer/investigations/${id}/notes`, { text }),
    closeInvestigation: (id: string) => api.post(`/officer/investigations/${id}/close`, {}),

    // ---- reference / directory -----------------------------------------------------------------
    directory: () => api.get<T.DirectoryData>('/reference/directory'),

    // ---- documents (scan/upload -> OCR/text-extract -> chunk -> embed -> searchable by Civic Saathi) ------------
    uploadDocument: async (file: T.LocalFile) => api.request<T.DocumentRecord>('POST', '/documents', { form: await fileForm('file', file, { visibility: 'private' }), timeoutMs: 120000 }),
    listDocuments: () => api.get<{ items: T.DocumentRecord[] }>('/documents'),
    documentStatus: (id: string) => api.get<T.DocumentRecord>(`/documents/${id}`),
    retryDocument: (id: string) => api.post<T.DocumentRecord>(`/documents/${id}/retry`, {}),
    linkDocument: (id: string, linked_type: 'complaint' | 'rti' | 'legal_case', linked_id: string) => api.post(`/documents/${id}/link`, { linked_type, linked_id }),

    // ---- interoperability layer (fragmentation diagnostic, live normalization demo, Golden Record, exceptions) ----
    interopSystems: () => api.get<{ items: T.InteropSystem[] }>('/interop/systems'),
    interopFragmentation: () => api.get<T.FragmentationDiagnostic>('/interop/fragmentation'),
    interopNormalizeDemo: (system: string, corrupt: boolean) => api.post<T.NormalizeDemoResult>('/interop/normalize-demo', { system, corrupt }),
    interopLogException: (source_system: string, reason: string, payload: Record<string, unknown>) => api.post<T.IntegrationException>('/interop/exceptions', { source_system, reason, payload }),
    interopExceptions: (status?: string | null) => api.get<{ items: T.IntegrationException[] }>('/interop/exceptions', status ? { status } : undefined),
    interopExceptionCounts: () => api.get<Record<string, number>>('/interop/exceptions/counts'),
    interopResolveException: (id: string, note: string, ignore: boolean) => api.post(`/interop/exceptions/${id}/resolve`, { note, ignore }),
    listMasterData: () => api.get<{ items: T.ExternalIdLink[] }>('/interop/master-data'),
    linkMasterData: (id_type: string, raw_value: string) => api.post<T.ExternalIdLink>('/interop/master-data', { id_type, raw_value }),
    unlinkMasterData: (id: string) => api.del(`/interop/master-data/${id}`),
    listExternalLinks: () => api.get<{ items: T.ExternalServiceLink[] }>('/interop/external-links'),
    addExternalLink: (platform: string, external_reference: string, title: string, status_note?: string) => api.post<T.ExternalServiceLink>('/interop/external-links', { platform, external_reference, title, status_note: status_note || '' }),
    updateExternalLink: (id: string, status_note: string) => api.put(`/interop/external-links/${id}`, { status_note }),
    removeExternalLink: (id: string) => api.del(`/interop/external-links/${id}`),

    // ---- monitoring / integrations (admin) --------------------------------------------------------
    integrationStatus: () => api.get<{ items: T.IntegrationHealth[] }>('/integrations'),
    integrationCheck: () => api.post<{ items: T.IntegrationHealth[] }>('/integrations/check', {}),
    systemStatus: () => api.get<T.SystemStatus>('/monitoring/system'),
    queueStatus: () => api.get<T.QueueStats>('/monitoring/queue'),
    notificationStatus: () => api.get<T.NotificationStatus>('/monitoring/notifications'),
    governmentStatus: () => api.get<T.GovernmentStatus>('/monitoring/government'),
    monitoringJobs: (status?: string | null) => api.get<{ items: T.JobRecordView[]; stats: T.QueueStats }>('/monitoring/jobs', status ? { status } : undefined),
    retryJob: (id: string) => api.post<T.JobRecordView>(`/monitoring/jobs/${id}/retry`, {}),

    // ---- workflow rules (admin) --------------------------------------------------------------------
    workflowRules: () => api.get<{ rules: T.WorkflowRule[]; executions: T.WorkflowExecution[] }>('/admin/workflow-rules'),
    saveWorkflowRule: (id: string, body: { name: string; trigger: string; action: string; conditions?: Record<string, unknown>; params?: Record<string, unknown>; priority?: number; active?: boolean }) =>
      api.put<T.WorkflowRule>(`/admin/workflow-rules/${id}`, body),
    deleteWorkflowRule: (id: string) => api.del(`/admin/workflow-rules/${id}`),
  };
}
export type Endpoints = ReturnType<typeof createEndpoints>;

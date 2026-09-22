// Types mirroring the FastAPI responses (backend: app/api/v1/*, app/schemas/api.py). Keep in sync with docs/API_CONTRACT.md.
import type { LanguageCode } from '../i18n/languages.ts';

export interface SessionUser { id: string; role: 'citizen' | 'officer' | 'admin' | 'super_admin'; department_code: string | null; email: string | null; full_name: string | null; mfa_enabled: boolean; language: string; onboarding_complete: boolean }
export interface LoginResponse { user: SessionUser; mfa_verified: boolean; csrf_token: string; session_token: string; token_type: 'Bearer' }

export interface Complaint {
  id: string; reference: string; title: string;
  description: string; language: string;            // ORIGINAL citizen text/language: never rewritten
  original_text: string; original_language: string; // explicit aliases of the two fields above
  detected_language: string | null;
  translated_text: string | null; translated_language: string | null; translation_provider: string | null; // derived, optional
  input_method: 'typed' | 'voice'; voice_id: string | null;
  category: string; severity: string; priority: string; status: string; department_code: string | null;
  ward: string | null; lat: number | null; lng: number | null; address: string | null;
  created_at: string; updated_at: string; sla_due_at: string | null; escalation_level: number; ai_status: string;
  duplicates: Array<{ reference: string; explanation: string; verdict: string }>;
}
export interface CreateComplaintResponse { complaint: Complaint; replayed: boolean; warnings: string[] }
export interface TimelineStep { label: string; state: 'done' | 'current' | 'upcoming' | 'skipped' | 'rejected'; at: string | null }
export interface ComplaintEvent { id: string; kind: string; to_status: string | null; actor_label: string | null; remarks: string | null; at: string }
export interface Evidence { id: string; name: string; mime: string; analysis_status: string }
export interface ComplaintDetail { complaint: Complaint; timeline: TimelineStep[]; events: ComplaintEvent[]; evidence: Evidence[]; feedback: { rating: number; comment: string | null } | null }

export interface VoiceLanguage { code: LanguageCode; name: string; native: string; script: string }
export interface VoiceCapabilities { state: 'CONFIGURED' | 'NOT_CONFIGURED'; provider: string | null; auto_detect: boolean; languages: VoiceLanguage[] }
export interface VoiceResult {
  id: string; status: 'OK' | 'NOT_CONFIGURED' | 'FAILED'; language_requested: string; language_detected: string | null; detected_by: 'provider' | 'script' | null;
  transcript: string | null; provider: string | null; error: string | null; script_ok: boolean; warnings: string[]; confidence: number | null;
}

export interface Citation { marker: string; documentName: string; page: number | null; excerpt: string }
export interface AskResponse { conversation_id: string; status: string; answer: string | null; citations: Citation[]; database_facts: unknown; warnings: string[]; insufficient_evidence: boolean }
export interface NotificationItem { id: string; kind: string; title: string; body: string; created_at: string; read_at: string | null }
export interface Helpline { code: string; number: string; name: string; description: string; tel_uri: string; translated: boolean }
export interface Hotspot { lat: number; lng: number; count: number; severity_score: number; categories: Record<string, number> }
export interface RadarResponse { total_complaints: number; mappable: number; not_mappable: number; hotspots: Hotspot[]; offices: Array<{ id: string; name: string; lat: number; lng: number }>; privacy: string | null }
export interface RtiApplication { id: string; reference: string | null; status: string; generated_text: string | null; due_at: string | null; draft: { subject: string; public_authority: string } }
export interface RtiCategory { code: string; default_records: string[] }
export interface RtiQuestionsPreview { questions: string[]; records_used: string[] }
export interface LegalPrecedent {
  cnr: string; neutralCitation: string; reporterCitation: string | null; title: string; bench: string[];
  decisionDate: string; disposal: string | null; court: string; matchedOn: string; score: number; origin: string;
}
export interface LegalFullTextExcerpt {
  judgmentId: string; title: string | null; court: string; neutralCitation: string | null; reporterCitation: string | null;
  decisionDate: string | null; page: number | null; text: string; similarity: number; origin: string;
}
export interface LegalAnalysis {
  status: string; concepts: string[]; precedents: LegalPrecedent[]; interpretation: string | null;
  confidence: string; bias_and_coverage: string[]; warnings: string[]; disclaimer: string;
  full_text_excerpts: LegalFullTextExcerpt[];
}

export interface ComplaintInput {
  title: string; description: string; language: LanguageCode; category?: string | null; ward?: string | null; lat?: number | null; lng?: number | null;
  client_request_id?: string; evidence_ids?: string[]; voice_id?: string | null;
}
export interface LocalFile { uri: string; name: string; type: string }
export interface DocumentRecord {
  id: string; owner_id: string; name: string; mime: string; size: number; sha256: string;
  visibility: 'private' | 'department' | 'public'; department_id: string | null;
  status: 'uploaded' | 'processing' | 'ready' | 'failed'; error: string | null;
  chunk_count: number; semantic_indexed: boolean; attempts: number; created_at: string; updated_at: string;
}
export interface ClassifyPreview {
  category: string; severity: string; confidence: number; source: string; matched_keywords: string[];
  explanation: string; ambiguous: boolean; department_code: string | null; department_name: string | null;
  routing_explanation: string; needs_manual_triage: boolean;
}

// ---- the voice/text triage assistant: "which screen does this belong to" -----------------------
export type AssistantDestination = 'complaint' | 'rti' | 'legal' | 'track' | 'document' | 'map' | 'locator' | 'emergency';
export interface AssistantRouteResult {
  destination: AssistantDestination;
  confidence: number;
  certain: boolean; // exactly one destination keyword matched - safe to auto-navigate; otherwise show alternatives
  matched: string[];
  explanation: string;
  alternatives: AssistantDestination[];
  classification?: ClassifyPreview; // present only when destination === 'complaint'
}

// ---- interoperability layer --------------------------------------------------------------------
export interface InteropSystem { code: string; label: string }
export interface FragmentationDiagnostic {
  national: { services: number; departments: number; source: string };
  personal: { distinct_departments: number; total_filings: number; profile_reuses: number };
}
export interface CanonicalRecordView {
  source_system: string; external_id: string; category: string; status: string; title: string; department: string;
  citizen_name: string | null; citizen_contact: string | null; location: string | null; filed_on: string | null;
}
export interface NormalizeDemoResult {
  payload: Record<string, unknown>; record: CanonicalRecordView;
  quality: { score: number; grade: 'excellent' | 'good' | 'poor' | 'unusable'; issues: string[] };
}
export interface IntegrationException {
  id: string; source_system: string; reason: string; payload: Record<string, unknown>; detected_at: string;
  status: 'open' | 'resolved' | 'ignored'; resolved_at: string | null; resolved_by: string | null; resolution_note: string | null;
}
export interface ExternalIdLink { id: string; user_id: string; id_type: string; id_hash: string; last4: string | null; linked_at: string }
export interface ExternalServiceLink { id: string; user_id: string; platform: string; external_reference: string; title: string; created_at: string; updated_at: string; status_note: string }

// ---- monitoring / integrations (admin) --------------------------------------------------------
export interface IntegrationHealth {
  platform: string; display_name: string; state: string; detail: string; checked_at: string;
  last_success_at: string | null; last_error: string | null; avg_response_ms: number | null;
  total_calls: number; total_failures: number; configured: boolean;
}
export interface QueueStats { by_status: Record<string, number>; backend_reachable: boolean; backend_depth: number; workers: Record<string, unknown> }
export interface JobRecordView {
  id: string; kind: string; payload: Record<string, unknown>; idempotency_key: string; status: string;
  attempts: number; max_attempts: number; run_at: string; created_at: string; updated_at: string;
  error: string | null; result: Record<string, unknown> | null; worker_id: string | null; started_at: string | null; finished_at: string | null;
}
export interface SystemStatus {
  queue: QueueStats; websocket_connections: number; adapters: Record<string, string>;
  storage: { provider: string; state: string; detail?: string }; ollama: string;
  rag: { chunks: number; semantic_search: boolean; model: boolean };
}
export interface NotificationStatus { by_channel: Record<string, Record<string, number>>; email_configured: boolean; push_configured: boolean }
export interface GovernmentStatus { submissions_by_state: Record<string, Record<string, number>>; adapters: Record<string, string> }

// ---- workflow rules (admin) --------------------------------------------------------------------
export interface WorkflowRule {
  id: string; name: string; trigger: string; conditions: Record<string, unknown>; action: string;
  params: Record<string, unknown>; priority: number; active: boolean; created_by: string | null; created_at: string;
}
export interface WorkflowExecution { rule_id: string; complaint_id: string; executed_at: string; outcome: string }

// ---- officer / department --------------------------------------------------------------------
// officer.queue() returns full ComplaintRecord rows (same shape as Complaint, plus officer-only fields).
export type OfficerQueueItem = Complaint & { classification: Record<string, unknown>; routing: Record<string, unknown>; priority_factors: string[]; assigned_officer_id: string | null; complaint_type: string };
// SlaStatus.remaining: a Python timedelta, which FastAPI's jsonable_encoder serializes as total seconds (float).
export interface SlaStatus { state: 'on_track' | 'at_risk' | 'breached' | 'no_policy' | 'finished'; due_at: string | null; remaining: number | null; policy_id: string | null }
export interface OfficerComplaintDetail {
  complaint: OfficerQueueItem;
  timeline: TimelineStep[]; events: ComplaintEvent[]; evidence: Evidence[]; sla: SlaStatus; feedback: { rating: number; comment: string | null } | null;
}
export interface DuplicateCandidate {
  complaint_id: string; reference: string; score: number; verdict: string; explanation: string; other_status: string | null; other_title: string | null;
  review: { decision: string; reviewer_id: string; at: string; note: string | null } | null;
}
export interface DepartmentDashboard {
  department_code: string | null; has_data: boolean; total: number; open: number; resolved: number; escalated: number; unrouted: number; backlog: number;
  sla: { on_track: number; at_risk: number; breached: number; no_policy: number };
  resolution_hours: { median: number; mean: number; count: number } | null;
  by_category: Record<string, number>; by_status: Record<string, number>; by_priority: Record<string, number>;
  by_department: Record<string, number>; by_ward: Record<string, number>; routing_sources: Record<string, number>; priority_counts: Record<string, number>;
  trend_daily: Array<{ date: string; count: number }>; workload: Record<string, number>;
  anomalies: Array<{ id: string; kind: string; subject: string; severity: string; score: number; explanation: string; detected_at: string; status: string }>;
}
export interface Investigation {
  id: string; subject_type: 'complaint' | 'anomaly'; subject_id: string; opened_by: string; department_code: string | null;
  status: 'open' | 'closed'; created_at: string; closed_at: string | null; notes: Array<{ by: string; at: string; text: string }>;
}
export interface InvestigationReport {
  investigation: Investigation; generated_at: string;
  // present when subject_type === 'anomaly'
  anomaly?: { id: string; kind: string; subject: string; severity: string; score: number; explanation: string; detected_at: string } | null;
  related_complaints?: Complaint[];
  // present when subject_type === 'complaint'
  complaint?: OfficerQueueItem; timeline?: TimelineStep[]; events?: ComplaintEvent[]; evidence?: Evidence[];
  location?: { lat: number | null; lng: number | null; address: string | null; ward: string | null; city: string | null };
  duplicates?: Array<{ complaint_id: string; reference: string; score: number; verdict: string; explanation: string }>;
  nearby_same_category?: Complaint[]; ward_category_cluster?: Complaint[];
  anomalies?: Array<{ id: string; kind: string; subject: string; severity: string; score: number; explanation: string; detected_at: string }>;
  audit_trail?: Array<{ action: string; actor_id: string | null; resource_type: string | null; resource_id: string | null; occurred_at: string; correlation_id: string | null; metadata: Record<string, unknown> }>;
  rag_findings?: { status: string; answer?: string | null; citations?: Citation[]; warnings?: string[] };
  legal_sources?: { status: string; precedents?: LegalAnalysis['precedents']; concepts?: string[]; coverage?: string[]; full_text_excerpts?: LegalFullTextExcerpt[] };
}

// ---- reference / directory --------------------------------------------------------------------
export interface DirectoryData {
  departments: Array<{ code: string; name: string }>;
  cities: Array<{ code: string; name: string; state: string | null; lat: number | null; lng: number | null }>;
  wards: Array<{ code: string; name: string; city_code: string | null }>;
  services: Array<{ code: string; name: string; department_code: string }>;
  offices: Array<{ id: string; name: string; department_code: string | null; lat: number; lng: number; address: string | null; city_code: string | null }>;
}
export interface GovernmentSubmissionState {
  platform: string; display_name: string; adapter_state: string; configured: boolean; consent_granted: boolean;
  state: string; external_reference: string | null; attempts: number; last_error: string | null;
}

// CivicLens Interoperability Layer — Department Adapters
//
// Each adapter below takes a RAW payload shaped the way that department's
// own system would actually structure it (different field names, different
// nesting, different status vocabularies, different date formats — this is
// realistic of how heterogeneous government IT systems actually look, not
// simplified for convenience) and returns a CDM_SERVICE_REQUEST object
// (see commonDataModel.js). This is the literal technical mechanism that
// solves "systems don't talk to each other": each system keeps its own
// native format, and a thin adapter translates at the boundary — the same
// approach real interoperability platforms (API Setu, X-Road) use.
//
// SAMPLE_PAYLOADS below are realistic fixtures for the live demo in
// InteroperabilityScreen.js — they are illustrative examples of each
// system's data shape (since this project has no data-sharing MOU with
// any real department to pull live payloads from), not live scraped data.

import { NORMALIZED_STATUSES } from './commonDataModel';

function normalizeStatus(sourceSystem, rawStatus) {
  const maps = {
    bbmp_civic: {
      'NEW': 'submitted',
      'ACK_BY_WARD': 'acknowledged',
      'ENGINEER_ASSIGNED': 'in_progress',
      'REPAIR_DONE': 'resolved',
      'REJECTED_DUPLICATE': 'rejected',
    },
    discom_utility: {
      'Ticket Raised': 'submitted',
      'Assigned to JE': 'acknowledged',
      'Field Visit Scheduled': 'in_progress',
      'Closed - Resolved': 'resolved',
      'Closed - Invalid': 'rejected',
    },
    police_ccnts: {
      'FIR_REGISTERED': 'submitted',
      'UNDER_INVESTIGATION': 'in_progress',
      'CHARGESHEET_FILED': 'resolved',
      'CASE_CLOSED_UNTRACED': 'rejected',
    },
    state_grievance_portal: {
      1: 'submitted',
      2: 'acknowledged',
      3: 'in_progress',
      4: 'resolved',
      5: 'escalated',
    },
  };
  const mapped = maps[sourceSystem]?.[rawStatus];
  return NORMALIZED_STATUSES.includes(mapped) ? mapped : 'submitted';
}

// ---- Adapter 1: Municipal Corporation civic-complaint system ------------
// Realistic of a legacy municipal system: SCREAMING_SNAKE_CASE fields,
// DD-MM-YYYY dates, ward-based jurisdiction.
export function adaptBbmpCivic(raw) {
  return {
    requestId: `cdm_${raw.COMPLAINT_ID}`,
    sourceSystem: 'bbmp_civic',
    sourceReferenceId: raw.COMPLAINT_ID,
    requestType: 'grievance',
    category: (raw.CATEGORY_DESC || '').toLowerCase().includes('road') ? 'roads' : 'civic',
    citizenId: raw.CITIZEN_MOBILE || 'unknown',
    title: raw.CATEGORY_DESC,
    description: raw.COMPLAINT_TEXT,
    status: normalizeStatus('bbmp_civic', raw.CURRENT_STATE),
    filedAt: ddmmyyyyToIso(raw.FILED_ON),
    lastUpdatedAt: ddmmyyyyToIso(raw.LAST_ACTION_ON || raw.FILED_ON),
    jurisdiction: raw.WARD_NAME ? `Ward ${raw.WARD_NO} — ${raw.WARD_NAME}` : null,
    rawSourcePayload: raw,
  };
}

// ---- Adapter 2: Electricity Board (DISCOM) utility system ---------------
// Realistic of a utility CRM: camelCase, nested consumer object, its own
// English-phrase status vocabulary.
export function adaptDiscomUtility(raw) {
  return {
    requestId: `cdm_${raw.ticketNumber}`,
    sourceSystem: 'discom_utility',
    sourceReferenceId: raw.ticketNumber,
    requestType: 'utility_request',
    category: 'electricity',
    citizenId: raw.consumer?.contactNumber || 'unknown',
    title: raw.faultType,
    description: raw.remarks,
    status: normalizeStatus('discom_utility', raw.ticketStatus),
    filedAt: raw.raisedTimestamp,
    lastUpdatedAt: raw.lastUpdateTimestamp || raw.raisedTimestamp,
    jurisdiction: raw.consumer?.subDivision || null,
    rawSourcePayload: raw,
  };
}

// ---- Adapter 3: Police CCTNS-style FIR system ----------------------------
// Realistic of CCTNS (Crime and Criminal Tracking Network & Systems):
// ALL_CAPS enums, a very different vocabulary entirely (legal terms, not
// "tickets").
export function adaptPoliceCcnts(raw) {
  return {
    requestId: `cdm_${raw.FIR_NO}`,
    sourceSystem: 'police_ccnts',
    sourceReferenceId: raw.FIR_NO,
    requestType: 'police_report',
    category: 'police',
    citizenId: raw.INFORMANT_PHONE || 'unknown',
    title: `FIR under ${raw.SECTIONS_APPLIED}`,
    description: raw.BRIEF_FACTS,
    status: normalizeStatus('police_ccnts', raw.INVESTIGATION_STAGE),
    filedAt: raw.REGISTRATION_DATETIME,
    lastUpdatedAt: raw.LAST_UPDATE_DATETIME || raw.REGISTRATION_DATETIME,
    jurisdiction: raw.PS_NAME ? `${raw.PS_NAME} Police Station` : null,
    rawSourcePayload: raw,
  };
}

// ---- Adapter 4: State Grievance Portal (numeric status codes) -----------
// Realistic of many state portals: numeric status codes instead of text
// (meaning you can't even tell what a status means without that state's
// own lookup table — a very real, very common interoperability failure
// mode), snake_case fields.
export function adaptStateGrievancePortal(raw) {
  return {
    requestId: `cdm_${raw.grievance_id}`,
    sourceSystem: 'state_grievance_portal',
    sourceReferenceId: raw.grievance_id,
    requestType: 'grievance',
    category: raw.department_code === 'PWD' ? 'roads' : raw.department_code === 'PHED' ? 'water' : 'civic',
    citizenId: raw.applicant_mobile || 'unknown',
    title: raw.subject,
    description: raw.grievance_detail,
    status: normalizeStatus('state_grievance_portal', raw.status_code),
    filedAt: raw.submission_date,
    lastUpdatedAt: raw.last_action_date || raw.submission_date,
    jurisdiction: raw.district || null,
    rawSourcePayload: raw,
  };
}

function ddmmyyyyToIso(ddmmyyyy) {
  if (!ddmmyyyy) return new Date().toISOString();
  const [d, m, y] = ddmmyyyy.split('-');
  return new Date(`${y}-${m}-${d}`).toISOString();
}

export const ADAPTERS = {
  bbmp_civic: { fn: adaptBbmpCivic, label: 'Municipal Corporation (Civic Complaints)' },
  discom_utility: { fn: adaptDiscomUtility, label: 'Electricity Board (DISCOM Utility CRM)' },
  police_ccnts: { fn: adaptPoliceCcnts, label: 'Police CCTNS (FIR System)' },
  state_grievance_portal: { fn: adaptStateGrievancePortal, label: 'State Grievance Portal' },
};

// Realistic sample raw payloads for the live interoperability demo —
// illustrative fixtures modeled on how each type of system actually
// structures data, not live data pulled from any real department (no
// data-sharing agreement exists for that).
export const SAMPLE_PAYLOADS = {
  bbmp_civic: {
    COMPLAINT_ID: 'BBMP-2026-88213',
    CATEGORY_DESC: 'Road Pothole',
    COMPLAINT_TEXT: 'Large pothole near bus stop causing two-wheeler accidents.',
    CURRENT_STATE: 'ENGINEER_ASSIGNED',
    FILED_ON: '02-09-2026',
    LAST_ACTION_ON: '05-09-2026',
    WARD_NO: '150',
    WARD_NAME: 'HSR Layout',
    CITIZEN_MOBILE: '+919876500001',
  },
  discom_utility: {
    ticketNumber: 'BESCOM-TCK-771029',
    faultType: 'Transformer Overload',
    remarks: 'Frequent voltage fluctuation damaging appliances in the locality.',
    ticketStatus: 'Field Visit Scheduled',
    raisedTimestamp: '2026-09-01T10:15:00+05:30',
    lastUpdateTimestamp: '2026-09-04T16:40:00+05:30',
    consumer: { contactNumber: '+919876500002', subDivision: 'Koramangala Sub-Division' },
  },
  police_ccnts: {
    FIR_NO: 'KA01-2026-004521',
    SECTIONS_APPLIED: 'BNS Sec 303 (Theft)',
    BRIEF_FACTS: 'Two-wheeler stolen from residential parking area overnight.',
    INVESTIGATION_STAGE: 'UNDER_INVESTIGATION',
    REGISTRATION_DATETIME: '2026-08-28T21:05:00+05:30',
    LAST_UPDATE_DATETIME: '2026-09-03T11:00:00+05:30',
    PS_NAME: 'HSR Layout',
    INFORMANT_PHONE: '+919876500003',
  },
  state_grievance_portal: {
    grievance_id: 'KAR-SGP-2026-190345',
    department_code: 'PHED',
    subject: 'Contaminated water supply',
    grievance_detail: 'Discolored water supply for the past week affecting entire street.',
    status_code: 3,
    submission_date: '2026-08-30T09:00:00+05:30',
    last_action_date: '2026-09-02T14:20:00+05:30',
    district: 'Bengaluru Urban',
    applicant_mobile: '+919876500004',
  },
};

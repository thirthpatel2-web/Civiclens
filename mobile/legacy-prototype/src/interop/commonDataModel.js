// CivicLens Interoperability Layer — "Setu" Common Data Model (CDM)
//
// THE PROBLEM: "System integration and interoperability among government
// digital platforms, resulting in fragmented service delivery" is, at its
// technical core, a DATA MODEL problem: a municipal corporation's system
// calls a citizen "Petitioner Name", the electricity board's calls it
// "Consumer Name", the police FIR system calls it "Complainant", and a
// state grievance portal calls it "Applicant Full Name" — same real-world
// concept, four different field names, four different formats, zero
// ability for these systems to exchange or reconcile data about the same
// citizen or the same request.
//
// THE SOLUTION PATTERN (this file + adapters.js): a single canonical
// schema (below) that every department-specific format gets translated
// into and out of, via small, explicit, testable "adapter" functions —
// the same integration pattern used by real interoperability
// infrastructure like India's own API Setu / IndEA framework, and by
// data-exchange layers like Estonia's X-Road. This is a demonstrable,
// working example of that pattern, not a claim that we've connected to
// real department backends (which would require formal data-sharing MOUs
// this project doesn't have) — see InteroperabilityScreen.js for a live,
// interactive demo of raw department payloads being normalized.

/**
 * CDM_CITIZEN — canonical representation of a citizen's identity, the
 * "Golden Record" every department-specific record should resolve to.
 */
export const CDM_CITIZEN_SCHEMA = {
  citizenId: 'string (CivicLens internal UUID — the Golden Record key)',
  fullName: 'string',
  phone: 'string | null',
  email: 'string | null',
  address: 'string | null',
  city: 'string | null',
  pincode: 'string | null',
  externalIds: 'array of { system: string, idType: string, idValue: string } — e.g. Aadhaar/PAN/Voter ID references once available',
};

/**
 * CDM_SERVICE_REQUEST — canonical representation of ANY interaction with
 * ANY department: a grievance, an RTI application, a scheme application,
 * a status inquiry. Every adapter in adapters.js maps a department's raw
 * format into this one shape.
 */
export const CDM_SERVICE_REQUEST_SCHEMA = {
  requestId: 'string — canonical ID within CivicLens',
  sourceSystem: 'string — which department/portal this came from (e.g. "bbmp_civic", "cpgrams", "discom")',
  sourceReferenceId: 'string — the ID that system itself uses (its own reference/ticket number)',
  requestType: 'enum: grievance | rti | scheme_application | utility_request | police_report',
  category: 'string — normalized category (e.g. "roads", "water", "electricity", "police")',
  citizenId: 'string — foreign key to CDM_CITIZEN.citizenId',
  title: 'string',
  description: 'string',
  status: 'enum: submitted | acknowledged | in_progress | resolved | rejected | escalated (normalized — each source system has its own status vocabulary, mapped here)',
  filedAt: 'ISO 8601 datetime',
  lastUpdatedAt: 'ISO 8601 datetime',
  jurisdiction: 'string | null — city/district/state',
  rawSourcePayload: 'object — the original untouched data, kept for audit/traceability',
};

// Central status vocabulary every adapter maps into. This is the actual
// "translation table" that lets CivicLens show one consistent status
// across systems that each use their own words for the same real state.
export const NORMALIZED_STATUSES = [
  'submitted',
  'acknowledged',
  'in_progress',
  'resolved',
  'rejected',
  'escalated',
];

/**
 * Validates that an object actually conforms to the CDM service-request
 * shape (required fields present, status is from the normalized
 * vocabulary). Used by the adapter demo screen to prove normalization
 * actually succeeded, not just claim it did.
 */
export function validateCdmServiceRequest(obj) {
  const errors = [];
  const required = ['requestId', 'sourceSystem', 'sourceReferenceId', 'requestType', 'citizenId', 'title', 'status', 'filedAt'];
  required.forEach((field) => {
    if (obj[field] === undefined || obj[field] === null || obj[field] === '') {
      errors.push(`Missing required field: ${field}`);
    }
  });
  if (obj.status && !NORMALIZED_STATUSES.includes(obj.status)) {
    errors.push(`Status "${obj.status}" is not in the normalized vocabulary: ${NORMALIZED_STATUSES.join(', ')}`);
  }
  return { valid: errors.length === 0, errors };
}

/**
 * Real data-quality checks beyond schema validation — completeness
 * scoring and format checks, the kind of checks a genuine integration
 * layer runs before trusting a record. Returns a score (0-100) and a
 * list of specific issues found, not just a pass/fail.
 */
export function runDataQualityChecks(cdmRecord) {
  const issues = [];
  let checks = 0;
  let passed = 0;

  const fieldsToCheck = ['requestId', 'sourceSystem', 'sourceReferenceId', 'title', 'description', 'jurisdiction', 'citizenId'];
  fieldsToCheck.forEach((f) => {
    checks++;
    if (cdmRecord[f] && String(cdmRecord[f]).trim().length > 0) {
      passed++;
    } else {
      issues.push({ field: f, issue: 'Missing or empty', severity: f === 'jurisdiction' ? 'low' : 'medium' });
    }
  });

  // Phone-shaped citizenId sanity check (many adapters use phone as the
  // interim citizen key before Golden Record linking — see
  // masterDataService.js)
  checks++;
  if (cdmRecord.citizenId && /^\+?\d{10,13}$/.test(String(cdmRecord.citizenId).replace(/[\s-]/g, ''))) {
    passed++;
  } else if (cdmRecord.citizenId && cdmRecord.citizenId !== 'unknown') {
    issues.push({ field: 'citizenId', issue: 'Does not look like a valid phone-shaped identifier', severity: 'low' });
  } else {
    issues.push({ field: 'citizenId', issue: 'No usable citizen identifier', severity: 'high' });
  }

  // Date sanity: filedAt should actually parse and not be in the future.
  checks++;
  const filedDate = new Date(cdmRecord.filedAt);
  if (!isNaN(filedDate.getTime()) && filedDate.getTime() <= Date.now() + 86400000) {
    passed++;
  } else {
    issues.push({ field: 'filedAt', issue: 'Unparseable or future-dated', severity: 'medium' });
  }

  const score = Math.round((passed / checks) * 100);
  return { score, passed, checks, issues, qualityLevel: score >= 90 ? 'high' : score >= 70 ? 'medium' : 'low' };
}

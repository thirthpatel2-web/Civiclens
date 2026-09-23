# Data model — interoperability platform

The 13 tables added by migration `0010` (`app/db/models/interop_platform.py`). Scoped to this
subsystem only — the rest of CivicLens's ~40 tables are unrelated to the interop platform and are
not documented here; see `ARCHITECTURE.md`'s "Data" section for those.

## Entity relationships

```
 MockDeptAResident ──1:N──► MockDeptADocument
 MockDeptBBeneficiary ──1:N──► MockDeptBApplication
 MockDeptCGrievance                                            (standalone; not FK-linked to anything)

 MasterEntity ──1:N──► MasterIdentifier          (system, identifier_type, identifier_value) per row,
              ──1:N──► IdentityMatchCandidate     unique on (system, identifier_type, identifier_value)
              ──1:N──► InteropConsentGrant
              ──1:N──► UnifiedApplication

 ConnectorRegistration                                          (standalone; keyed by connector_id string)

 InteropTransaction ──N:1──► MasterEntity (nullable)
                     ──N:1──► InteropConsentGrant (nullable)

 UnifiedApplication ──1:N──► UnifiedApplicationEvent
                     ──N:1──► MasterEntity
```

Nothing here has a foreign key *into* `MockDeptA*`/`MockDeptB*`/`MockDeptC*` from the resolution
layer — deliberately. `MasterIdentifier.identifier_value` is a plain string that happens to match a
`resident_id`/`beneficiary_code` elsewhere; the resolution layer treats each mock system as opaque,
exactly as it would treat a real external department it has no schema control over.

## Tables

### Mock Department A — Maharashtra Revenue Records System (demo)

| `mockgov_a_residents` | Type | Notes |
|---|---|---|
| `resident_id` (PK) | `String(40)` | e.g. `RES-MH-00101` |
| `full_name` | `String(200)` | |
| `mobile` | `String(20)` | Stored as digits, e.g. `9876543210` |
| `address`, `city`, `state` | `String` | |
| `created_at` | `timestamptz` | |

| `mockgov_a_documents` | Type | Notes |
|---|---|---|
| `document_id` (PK) | `uuid` | |
| `resident_id` (FK, CASCADE) | → `mockgov_a_residents` | |
| `document_type` | `String(60)` | e.g. `residence_certificate` |
| `status` | `String(20)` | `verified` \| `pending` \| `rejected` |
| `reference_no` | `String(60)` | The identifier the no-reupload flow carries into Department B |
| `issued_on`, `created_at` | `timestamptz` | |

### Mock Department B — Seva Setu Service Application System (demo)

| `mockgov_b_beneficiaries` | Type | Notes |
|---|---|---|
| `beneficiary_code` (PK) | `String(40)` | e.g. `BEN-MH-90011` — unrelated to Dept A's `resident_id` |
| `full_name`, `mobile_number` | `String` | Deliberately different formatting from Dept A's copy of the same person in seed data (`+91-` prefix, spacing) |
| `created_at` | `timestamptz` | |

| `mockgov_b_applications` | Type | Notes |
|---|---|---|
| `application_no` (PK) | `String(40)` | e.g. `APP-MH-2026-5501` |
| `beneficiary_code` (FK, CASCADE) | → `mockgov_b_beneficiaries` | |
| `service_type` | `String(80)` | |
| `status` | `String(30)` | `pending_document` \| `processing` \| `approved` \| `rejected` |
| `required_document_type` | `String(60)` | |
| `document_status` | `String(30)` | `missing` \| `requested` \| `received` \| `verified` — the no-reupload flow flips this |
| `document_reference` | `String(60)`, nullable | Set to Department A's `reference_no` once fetched — never a re-uploaded file |
| `created_at`, `updated_at` | `timestamptz` | |

### Mock Department C — Nagrik Grievance Cell (demo)

| `mockgov_c_grievances` | Type | Notes |
|---|---|---|
| `grievance_ref` (PK) | `String(40)` | |
| `citizen_ref` | `String(40)` | Department C's own name for "whoever filed this" — not `resident_id` or `beneficiary_code` |
| `subject`, `status`, `department` | `String` | |
| `created_at` | `timestamptz` | |

### Master Data Management

| `interop_master_entities` | Type | Notes |
|---|---|---|
| `master_id` (PK) | `uuid` | The one identity every system's record ultimately links to |
| `display_name` | `String(200)` | |
| `created_at` | `timestamptz` | |

| `interop_master_identifiers` | Type | Notes |
|---|---|---|
| `id` (PK) | `uuid` | |
| `master_id` (FK, CASCADE) | → `interop_master_entities` | |
| `system` | `String(40)` | `dept_a` \| `dept_b` \| `dept_c` \| `civiclens` |
| `identifier_type` | `String(40)` | `resident_id` \| `beneficiary_code` \| `grievance_citizen_ref` \| `user_id` |
| `identifier_value` | `String(80)` | |
| `confidence` | `float` | 0.0–1.0; 1.0 = exact/verified or officer-confirmed |
| `matched_on` | `String(200)` | Human-readable evidence, e.g. `"name similarity 0.93; exact mobile number match"` |
| `created_at` | `timestamptz` | |
| — | `UNIQUE(system, identifier_type, identifier_value)` | The real entity-resolution guard: one identifier can never be linked to two master entities |

| `interop_identity_match_candidates` | Type | Notes |
|---|---|---|
| `id` (PK) | `uuid` | |
| `master_id` (FK, CASCADE) | → `interop_master_entities` | The *proposed* match |
| `system`, `identifier_type`, `identifier_value` | as above | The identifier awaiting a decision |
| `score` | `float` | 0.55–0.90 by construction — anything ≥0.90 auto-links and never reaches this table |
| `explanation` | `String(300)` | Same evidence format as `matched_on` |
| `status` | `String(20)` | `pending` \| `confirmed` \| `rejected` |
| `resolved_by` (FK, nullable) | → `users.id` | Who decided — never the algorithm |
| `resolved_at` | `timestamptz`, nullable | |
| `created_at` | `timestamptz` | |

### Consent

| `interop_consent_grants` | Type | Notes |
|---|---|---|
| `consent_id` (PK) | `uuid` | |
| `master_id` (FK, CASCADE) | → `interop_master_entities` | |
| `citizen_user_id` (FK) | → `users.id` | Who this grant is attributed to |
| `requesting_system`, `providing_system` | `String(40)` | e.g. `dept_b` requesting from `dept_a` |
| `purpose` | `String(200)` | Generated per-request, e.g. "Verify residence certificate for application APP-MH-2026-5501" |
| `data_category` | `String(80)` | e.g. `residence_certificate` |
| `fields` | `jsonb` list | Exactly which fields, e.g. `["full_name", "reference_no", "issued_on", "status"]` |
| `status` | `String(20)` | `pending` \| `granted` \| `denied` \| `expired` \| `revoked` |
| `created_at`, `expires_at`, `decided_at`, `revoked_at` | `timestamptz`, nullable where applicable | Granted consents expire 30 days after `decided_at` |
| `revocation_reason` | `String(300)`, nullable | |

### Connector registry

| `interop_connector_registry` | Type | Notes |
|---|---|---|
| `connector_id` (PK) | `String(60)` | `dept_a` \| `dept_b` \| `dept_c` (real government adapters could register here too) |
| `name`, `department` | `String` | |
| `version` | `String(20)` | |
| `supported_operations` | `jsonb` list | e.g. `["get_entity", "fetch_document", "health_check"]` |
| `enabled` | `bool` | |
| `health_state` | `String(20)` | `healthy` \| `degraded` \| `unavailable` \| `not_configured` \| `unknown` — set from real calls |
| `last_health_check`, `last_success_at`, `last_failure_at` | `timestamptz`, nullable | |
| `total_calls`, `total_failures` | `int` | |
| `avg_response_ms` | `float`, nullable | Running average, updated on every real call |
| `created_at` | `timestamptz` | |

### Transaction and timeline

| `interop_transactions` | Type | Notes |
|---|---|---|
| `transaction_id` (PK) | `uuid` | |
| `correlation_id` | `String(60)` | Shared with the `UnifiedApplicationEvent` rows and the `AuditService` entries from the same exchange |
| `operation` | `String(60)` | e.g. `document_exchange` |
| `source_system`, `target_system` | `String(40)` | |
| `master_id` (FK, nullable) | → `interop_master_entities` | |
| `consent_id` (FK, nullable) | → `interop_consent_grants` | |
| `status` | `String(30)` | `success` \| `failed` \| `pending_consent` \| `rejected` |
| `error_code`, `error_message` | `String`, nullable | Populated only on failure — never both null and status=failed |
| `fields_exchanged` | `jsonb` list | Empty on failure |
| `duration_ms` | `float`, nullable | Real elapsed time of the connector call |
| `created_at` | `timestamptz` | |

| `interop_unified_applications` | Type | Notes |
|---|---|---|
| `application_id` (PK) | `uuid` | |
| `reference` (unique) | `String(30)` | e.g. `CL-APP-APP-MH-2026-5501` |
| `master_id` (FK, CASCADE) | → `interop_master_entities` | |
| `service_type`, `primary_system` | `String` | |
| `external_reference` | `String(60)`, nullable | The primary system's own key, e.g. Dept B's `application_no` |
| `status` | `String(30)` | `in_progress` \| `completed` \| `rejected` |
| `created_at`, `updated_at` | `timestamptz` | |

| `interop_unified_application_events` | Type | Notes |
|---|---|---|
| `id` (PK) | `uuid` | |
| `application_id` (FK, CASCADE) | → `interop_unified_applications` | |
| `step` | `String(120)` | e.g. `identity_resolved_cross_system`, `document_fetched_from_dept_a`, `document_applied_to_dept_b_application` |
| `source_system` | `String(40)` | |
| `status` | `String(30)` | |
| `correlation_id` | `String(60)`, nullable | |
| `detail` | `jsonb` dict | Step-specific facts, e.g. `{"reference_no": "...", "quality_score": 1.0}` |
| `occurred_at` | `timestamptz` | |

## Why no `CHECK` constraints on the string enum-ish columns

`status`, `health_state`, `system`, `identifier_type` and similar columns are plain
`String`/`VARCHAR`, not a Postgres `ENUM` or `CHECK` constraint. This matches the rest of this
codebase's convention (see e.g. `complaints.status` in the pre-existing schema) — application code
is the single source of truth for the valid vocabulary (see the docstrings in
`app/db/models/interop_platform.py` for each column's real value set), which keeps adding a new
status value a code-only change, no migration required.

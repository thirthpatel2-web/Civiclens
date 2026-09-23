# Data model — interoperability platform

The 13 tables added by migration `0010` (`app/db/models/interop_platform.py`), the 3 columns
migration `0011` added to `interop_transactions` for field-level consent tracking, and the 2 mock
Government IdP tables migration `0012` added. Scoped to this
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
| `sla_max_avg_response_ms`, `sla_min_success_rate` | `float`, nullable — migration `0015` | This connector's own SLA thresholds; `NULL` falls back to `app.interop.monitoring.sla`'s defaults (1000ms / 95%) |
| `sla_status` | `String(20)` — migration `0015` | `met` \| `breached` \| `unknown` — recomputed on every real call inside `record_call`, never a separate simulated pass |

### Connector alerts — migration `0015`

| `interop_connector_alerts` | Type | Notes |
|---|---|---|
| `alert_id` (PK) | `uuid` | |
| `connector_id` (FK) | → `interop_connector_registry` | |
| `alert_type` | `String(40)` | `SLA_BREACHED` \| `CONNECTOR_UNAVAILABLE` |
| `severity` | `String(10)` | `warning` \| `critical` |
| `message` | `String(300)` | |
| `created_at` | `timestamptz` | |
| `acknowledged` | `bool`, indexed | |
| `acknowledged_at`, `acknowledged_by` | `timestamptz`/`String(36)`, nullable | |

Created only on a genuine state transition (`app/interop/monitoring/alerts.py::raise_alert_if_needed`),
never once per subsequent failed call for the same ongoing breach - see
`docs/INTEROPERABILITY.md`'s "SLA thresholds & alerting" section.

### Service catalog & field mapping catalog — migration `0016`

| `interop_service_catalog` | Type | Notes |
|---|---|---|
| `service_id` (PK) | `String(80)` | e.g. `residence_certificate_verification` |
| `name`, `description` | `String` | |
| `source_system`, `target_system` (FK) | → `interop_connector_registry` | |
| `data_category` | `String(80)` | Matches `InteropConsentGrant.data_category` |
| `workflow_id` (FK, nullable) | → `interop_workflow_definitions` | |
| `active` | `bool` | |
| `created_at` | `timestamptz` | |

| `interop_field_mappings` | Type | Notes |
|---|---|---|
| `mapping_id` (PK) | `String(120)` | e.g. `dept_a_document_to_canonical:reference` |
| `service_id` (FK, nullable, indexed) | → `interop_service_catalog` | |
| `direction` | `String(30)` | `external_to_canonical` \| `canonical_to_external` |
| `system_id` (FK) | → `interop_connector_registry` | |
| `entity` | `String(60)` | Canonical entity name, e.g. `Document` |
| `source_field`, `target_field` | `String(80)` | |
| `transform_note` | `String(300)`, nullable | e.g. `verbatim`, or a renamed/converted-value description |
| `created_at` | `timestamptz` | |

Seeded (`app/interop/catalog.py::seed_if_empty`) from what `app.interop.canonical.v1.transform`'s
real functions actually do for the one live-wired service — not a parallel, independently-authored
description. `tests/unit/test_field_mapping_catalog.py` cross-checks every seeded row against the
real transform functions' output on fixture input, so this table can't silently drift from the code
it describes.

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
| `fields_exchanged` | `jsonb` list | The destination system's own field names for what was actually written (e.g. `["document_reference", "document_status"]`). Empty on failure |
| `requested_fields` | `jsonb` list | Canonical field names (migration `0011`) this operation needed to read from the source - `["reference", "status", "issued_on"]` for the document exchange |
| `approved_fields` | `jsonb` list | `consent.fields` at the moment this transaction ran - the field-level authorization actually checked, not just what the consent record says today |
| `denied_fields` | `jsonb` list | `requested_fields` not in `approved_fields` - non-empty only when `status="failed"`, `error_code="data_field_not_consented"` |
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

### Mock Government Identity Provider (federated identity / SSO, demo) — migration `0012`

| `interop_federation_clients` | Type | Notes |
|---|---|---|
| `client_id` (PK) | `String(60)` | One per connector today, e.g. `dept_a` |
| `name` | `String(120)` | |
| `client_secret_hash` | `String(255)` | Argon2id - never the raw secret |
| `system` | `String(40)` | Which connector/department this federation client represents - the role/department mapping a token's claims carry |
| `allowed_scopes` | `jsonb` list | e.g. `["interop:read", "interop:write"]` - a token can only ever be issued a subset of this |
| `enabled` | `bool` | Disabling a client invalidates its already-issued tokens too (`validate_token` re-checks the client, not just the token row) |
| `created_at` | `timestamptz` | |

| `interop_federation_tokens` | Type | Notes |
|---|---|---|
| `token_id` (PK) | `uuid` | |
| `token_hash` (unique) | `String(64)` | sha256 hex of the raw bearer token - only the hash is ever stored, same as session tokens |
| `client_id` (FK, CASCADE) | → `interop_federation_clients` | |
| `scope` | `jsonb` list | The actually-granted scope for this token (may be narrower than the client's `allowed_scopes` if a narrower scope was requested) |
| `issued_at`, `expires_at` | `timestamptz` | 1-hour TTL (`idp.TOKEN_TTL`) |
| `revoked_at` | `timestamptz`, nullable | Set by `revoke_token` - checked before expiry, so revocation is immediate even for a token that hasn't expired yet |

### Interop events (not a SQL table)

`app/interop/events/` deliberately has no database table - events live in a Redis stream
(`civiclens:interop:events`, capped at ~10,000 entries) or, without Redis configured, an in-memory
list that doesn't survive a process restart. This is intentional: the durable, queryable record of
what happened is already `InteropTransaction` + `UnifiedApplicationEvent` (both real SQL tables,
above) + the audit log; the event bus's job is notifying *other* consumers in near-real-time, not
being a second system of record. See `docs/INTEROPERABILITY.md`'s "Event-driven pub/sub" section.

### Configurable workflows — migration `0013`

| `interop_workflow_definitions` | Type | Notes |
|---|---|---|
| `workflow_id` (PK) | `String(80)` | e.g. `residence_certificate_verification` |
| `name`, `version` | `String` | |
| `steps` | `jsonb` list | Ordered step dicts - `step_id`, `on_failure`, `retry_max_attempts`, `timeout_seconds`, `requires_approval`, `condition_key` (see `app/interop/workflow/engine.py::StepSpec`) |
| `active` | `bool` | |
| `created_at` | `timestamptz` | |

| `interop_workflow_executions` | Type | Notes |
|---|---|---|
| `execution_id` (PK) | `uuid` | |
| `workflow_id` (FK) | → `interop_workflow_definitions` | |
| `correlation_id` | `String(60)` | |
| `status` | `String(20)` | `running` \| `completed` \| `failed` \| `waiting_approval` |
| `current_step_index` | `int` | Where a paused or failed execution stopped - `resume()` continues from here |
| `context` | `jsonb` dict | Accumulated step outputs, merged as each step completes - only ever plain JSON-safe values, never a raw ORM row |
| `started_at`, `finished_at` | `timestamptz`, latter nullable | |

| `interop_workflow_step_executions` | Type | Notes |
|---|---|---|
| `id` (PK) | `uuid` | |
| `execution_id` (FK, CASCADE) | → `interop_workflow_executions` | |
| `step_id`, `step_index` | `String` / `int` | |
| `status` | `String(20)` | `completed` \| `failed` \| `skipped` (no `pending`/`running` row is ever persisted - only a step that actually ran gets a row) |
| `attempt` | `int` | One row per attempt - a retried step leaves a full history, not just its last try |
| `error_message` | `String(400)`, nullable | |
| `started_at`, `finished_at` | `timestamptz`, nullable | |

### Data quality rule sets & central exception management — migration `0014`

| `interop_quality_rule_sets` | Type | Notes |
|---|---|---|
| `ruleset_id` (PK) | `String(80)` | e.g. `residence_certificate_v1` |
| `name`, `version` | `String` | |
| `rules` | `jsonb` list | List of `QualityRule` dicts (`app/interop/quality/engine.py::QualityRule.to_dict()`) - field, rule type, params, message |
| `active` | `bool` | |
| `created_at` | `timestamptz` | |

Real and migrated; nothing reads from it yet — `InteropGatewayService._document_quality` still
evaluates a fixed Python list of `QualityRule` objects, not a row loaded from this table. Named as
partial in `docs/REQUIREMENT_TRACEABILITY.md`.

| `interop_exceptions` | Type | Notes |
|---|---|---|
| `exception_id` (PK) | `uuid` | |
| `error_code` | `String(40)` | One of `app.interop.exceptions.taxonomy.EXCEPTION_TYPES` (20 canonical codes) |
| `message` | `String(500)` | |
| `source_system`, `target_system` | `String(40)`, nullable | |
| `correlation_id` | `String(60)`, nullable, indexed | Shared with the `InteropTransaction`/audit rows the same failure produced |
| `retryable` | `bool` | Defaults from `taxonomy.is_retryable(error_code)` unless overridden |
| `retry_count`, `max_retries` | `int` | |
| `next_action` | `String(200)`, nullable | Human-readable guidance; cleared on resolve |
| `resolution_state` | `String(20)`, indexed | `open` \| `retrying` \| `resolved` \| `dead` |
| `created_at` | `timestamptz` | |
| `resolved_at` | `timestamptz`, nullable | |

Distinct from the pre-existing `IntegrationExceptionRecord`/`ExceptionService`
(`app/services/interop_service.py`) — that is a simpler "log a malformed inbound payload for a
human to review" queue with no taxonomy, no `correlation_id`, and no retry tracking. Both are real
tables serving different purposes; neither replaces the other. See `docs/INTEROPERABILITY.md`'s
"Central exception management" section for how `log_exception()` is wired into
`InteropGatewayService`'s real failure branches.

## Why no `CHECK` constraints on the string enum-ish columns

`status`, `health_state`, `system`, `identifier_type` and similar columns are plain
`String`/`VARCHAR`, not a Postgres `ENUM` or `CHECK` constraint. This matches the rest of this
codebase's convention (see e.g. `complaints.status` in the pre-existing schema) — application code
is the single source of truth for the valid vocabulary (see the docstrings in
`app/db/models/interop_platform.py` for each column's real value set), which keeps adding a new
status value a code-only change, no migration required.

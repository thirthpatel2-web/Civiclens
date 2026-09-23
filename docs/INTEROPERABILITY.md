# CivicLens interoperability platform

**Problem statement answered:** SIH26129 — *System integration and interoperability among
government digital platforms, resulting in fragmented service delivery* (Government of
Maharashtra, Department of Skills, Employment, Entrepreneurship and Innovation).

This document describes the middleware layer CivicLens adds on top of its existing
citizen-complaint product: a working demonstration of one department reusing another
department's data — without the citizen re-entering or re-uploading anything — governed by
explicit consent, resolved identity, and a full audit trail. It is written so a reader who has
never seen the code can understand what is real, what is a demo, and how to run it themselves.

## What's real, what's a demo, what's not configured

No Maharashtra government department has given CivicLens a live data-sharing agreement or API
credential. Nothing in this project claims otherwise. Concretely:

| Component | Status | What that means |
|---|---|---|
| Three government systems (Dept A/B/C) | **MOCK / DEMO** | Real, persisted, independently-queryable PostgreSQL tables with deliberately different schemas and identifier vocabularies — not static fixtures, not three screens on one shared table. Seeded with realistic (fictional) Maharashtra demo data. Every place this surfaces in the UI is labelled "(demo)". |
| Identity resolution, consent, connector registry, transaction/event/audit trail | **REAL** | The matching algorithm, the consent state machine, the health checks, the orchestration logic, and everything written to the database are the genuine mechanism — the only thing mocked is *which systems* sit on the other end of the connectors. The day a real department supplies a credential, only `app/interop/mock_systems.py`'s query functions change to real HTTP/SOAP/SFTP calls; identity resolution, consent, and the audit trail need no changes. |
| Live government API integration (CPGRAMS, UMANG, state portals) | **NOT CONFIGURED** | `app/services/government_service.py` and `app/interop/adapters.py` handle this honestly today: `not_configured` if no adapter credential exists, never a fabricated success. Unrelated to the mock-systems demo above — see `ARCHITECTURE.md`'s "Government platforms" section. |
| Citizen-initiated Golden Record linking (Aadhaar/PAN/voter-ID hash) | **REAL** | Pre-existing, separate feature (`app/services/interop_service.py::MasterDataService`) — a citizen links their own external IDs to their CivicLens profile by salted hash. Distinct from the automated cross-system resolution described below. |

## Why three systems, and why their schemas actually differ

A demo with three UI tabs backed by one shared table doesn't prove interoperability — it proves
a single form with three labels. CivicLens's three mock systems are separate PostgreSQL tables
with separate primary keys and separate field names, chosen to mirror what real fragmentation
looks like:

| System | File | Primary identifier | Other identifiers | Notes |
|---|---|---|---|---|
| **Department A** — Maharashtra Revenue Records System (demo) | `mockgov_a_residents` / `mockgov_a_documents` | `resident_id` (e.g. `RES-MH-00101`) | — | Holds verified documents (e.g. `residence_certificate`) with a `reference_no` |
| **Department B** — Seva Setu Service Application System (demo) | `mockgov_b_beneficiaries` / `mockgov_b_applications` | `beneficiary_code` (e.g. `BEN-MH-90011`) | `application_no` (e.g. `APP-MH-2026-5501`) | An application records `required_document_type` / `document_status` / `document_reference` — this is the field the no-reupload flow fills in |
| **Department C** — Nagrik Grievance Cell (demo) | `mockgov_c_grievances` | `grievance_ref` (e.g. `GRV-MH-3301`) | `citizen_ref` | Present to prove "at least three independent systems" is a fact, not a claim — not used by the headline demo |

The seed data (`app/interop/mock_systems.py::seed_if_empty`, idempotent, runs on every app
startup) deliberately gives the *same* fictional citizen different name formatting and phone
number formatting across Department A and Department B (e.g. `"Priya Deshmukh"` / `"9876543210"`
in A vs `"Priya S. Deshmukh"` / `"+91-9876543210"` in B) — this is what identity resolution has
to see through.

## Identity resolution (Master Data Management)

`app/interop/identity_resolution.py::IdentityResolutionService`. Every system's record is linked
to one `MasterEntity` (a `interop_master_entities` row) via `MasterIdentifier` rows (one per
(system, identifier) pair, each carrying the confidence and evidence that produced it).

Evidence, in order of strength:
1. **An identifier already linked** — exact, confidence 1.0. Fast path once a link exists.
2. **Exact mobile number match**, normalized to the last 10 digits (absorbs `+91-`, leading `0`,
   spacing) — strong signal.
3. **Name similarity** — trigram + token lexical similarity (`app/services/duplicate_service.py`,
   the same metric already used for duplicate-complaint detection, reused rather than
   reinvented), alone or combined with a mobile match.

```
score = max(name_score, 0.6·mobile_score + 0.4·name_score)   if a mobile match exists
score = name_score                                            otherwise
```

Two thresholds decide what happens next — **nothing is ever auto-merged below the confirm
threshold**:

- **`score ≥ 0.90`** → auto-link. The new identifier joins the existing master entity.
- **`0.55 ≤ score < 0.90`** → queued as an `IdentityMatchCandidate` (`interop_identity_match_candidates`,
  status `pending`) for a human to confirm or reject. The caller must treat this as *identity
  ambiguous* and stop — the gateway does exactly that (see below).
- **`score < 0.55`** → treated as a new, unrelated person. A fresh `MasterEntity` is created.

An officer resolves a pending candidate at `POST /api/v1/interop-gateway/identity-candidates/{id}/resolve`
(`InteropGatewayService.resolve_identity_candidate`): **approve** links the identifier to the
proposed master entity at full confidence, attributed to the officer, not the algorithm;
**reject** creates a *new*, separate master entity for that identifier instead of leaving it
unlinked — a reject is itself a positive claim ("this is a different person"), not a no-op.

## Consent

`InteropConsentGrant` (`interop_consent_grants`) is a fine-grained, per-exchange artifact —
distinct from the existing broad `data_sharing_government` consent purpose
(`app/services/profile_service.py`). Each grant names exactly *what* is being shared
(`data_category`, e.g. `residence_certificate`), *between which two systems*
(`requesting_system`/`providing_system`), *why* (`purpose`, generated per-request — e.g. "Verify
residence certificate for application APP-MH-2026-5501"), and *which fields*
(`fields: ["reference", "status", "issued_on"]` — the canonical `Document` field names, see
"Field-level consent enforcement" below).

State machine: `pending → granted | denied`, and a granted consent can later be `revoked`
(with a reason, timestamped). A grant expires 30 days after it's granted
(`InteropGatewayService.CONSENT_VALIDITY`). **No data is read from the providing system until a
grant exists in `granted` state** — `request_document_exchange` checks for one first and returns
`consent_required` (with nothing else having happened) if none exists yet.

**Field-level consent enforcement**: `fields` is checked, not decorative. Before the Department A
connector is called at all, `InteropGatewayService` compares `REQUIRED_DOCUMENT_FIELDS` (what this
operation needs: `reference`, `status`, `issued_on`) against `consent.fields`; anything missing
refuses the exchange with `data_field_not_consented` and the exact denied field names, recorded on
the `InteropTransaction` row's `requested_fields`/`approved_fields`/`denied_fields` columns
(migration `0011`). See `docs/SECURITY.md`'s "Field-level consent enforcement" section.

**Citizen-controlled consent**: `grant_consent`/`deny_consent`/`revoke_consent` accept either an
`INTEROP_MANAGE`-holding integration admin *or* the citizen the grant is attributed to
(`citizen_user_id == ctx.user_id`) — checked in the service layer, since it's a data-dependent
question, not a static permission. `GET /my-consents` is the citizen-facing list. See
`docs/SECURITY.md`'s "Citizen-controlled consent" section, including its one named limitation
(today's demo personas aren't linked to real CivicLens accounts, so `citizen_user_id` is set to
whoever operates the demo console rather than a citizen who logged in themselves).

## Canonical data model

`app/interop/canonical/v1/` — external systems never talk to CivicLens's internal SQLAlchemy
models. Every connector transforms its own system's shape into one of 16 frozen dataclasses
(`Citizen`, `MasterIdentity`, `Organization`, `Address`, `Department`, `Office`, `Service`,
`Application`, `Grievance`, `Document`, `Approval`, `Beneficiary`, `Consent`, `Event`, `Workflow`,
`Notification` — `models.py`) on the way in, and back into that system's native field names on the
way out (`transform.py`):

```
Department A format -> Connector -> External-to-Canonical Transformer -> Canonical Record
Canonical Record -> Canonical-to-External Transformer -> Department B format
```

Only `Document` and `Application` are wired into a live data flow today — the no-reupload exchange
transforms Department A's row into a canonical `Document` (`dept_a_document_to_canonical`), quality
checks *that*, then derives exactly what Department B needs
(`canonical_document_to_dept_b_fields`) rather than forwarding Department A's row wholesale. The
other 14 dataclasses are real and typed, ready for the next connector operation that needs them,
but a dataclass existing is not itself a claim that it's wired anywhere — see
`docs/REQUIREMENT_TRACEABILITY.md`.

`Application.status` is constrained to `CANONICAL_APPLICATION_STATES` (`DRAFT`, `SUBMITTED`,
`IN_PROGRESS`, `WAITING_FOR_CITIZEN`, `WAITING_FOR_DEPARTMENT`, `WAITING_FOR_EXTERNAL_SYSTEM`,
`APPROVED`, `REJECTED`, `COMPLETED`, `FAILED`, `CANCELLED`) — the shared vocabulary every
department's own status words map into, so a citizen's cross-department timeline reads
consistently rather than switching vocabulary mid-view. Dept B's `pending_document` maps to
`WAITING_FOR_EXTERNAL_SYSTEM`, `processing` to `IN_PROGRESS`, and so on
(`transform.py::_DEPT_B_STATUS_TO_CANONICAL`).

Schema versioning: this is v1. A breaking change adds `app.interop.canonical.v2` alongside it
rather than editing v1 in place — existing connectors keep transforming into v1 until migrated.

## Reusable connector abstraction

`app/interop/connectors/` — the gateway calls Department A/B/C **only** through
`GovernmentConnector` (`base.py`), resolved by a runtime (`runtime.py`), never by importing a
mock-system query function directly:

```
Interop Gateway -> Connector Runtime -> GovernmentConnector -> Dept A / Dept B / Dept C / future systems
```

Every connector — `DeptAConnector`, `DeptBConnector`, `DeptCConnector` today — implements the same
interface: `authenticate()`, `health_check()`, `get_entity()`, `query()`, `submit()`, `update()`,
`fetch_document()`, plus `send_event()`/`transform_request()`/`transform_response()`/
`handle_error()` with sensible defaults a connector only overrides if it needs to. Adding a new
government system means implementing this interface and registering it
(`app.interop.connector_registry`) — it never requires touching gateway orchestration logic. The
runtime checks the connector registry's `enabled` flag before dispatching and records every real
call's timing/success against the registry's live stats (`connector_registry.record_call`) — the
same accounting the connector health cards show, now sourced from one place regardless of which
operation triggered the call.

The three demo connectors are all read-mostly against real persisted tables: `DeptAConnector`
refuses `submit`/`update` honestly (`CONNECTOR_UNAVAILABLE`, "read-only"); `DeptBConnector.update`
is the actual no-reupload write; `DeptCConnector` is read-only and not part of the headline demo.
See `tests/integration/test_connectors.py` for interface-conformance and registry-gating coverage.

## Federated identity / SSO — **DEMO / MOCK IDENTITY PROVIDER**

`app/interop/federation/idp.py`. Not connected to any real government identity federation — every
client, secret and token here is demo data. A real, working OAuth2 client_credentials authorization
server (RFC 6749 §4.4): `FederationClient`/`FederationToken` (`interop_federation_clients`/
`interop_federation_tokens`, migration `0012`), opaque bearer tokens hashed at rest (the same
discipline `app.core.security.hash_token` already uses for session tokens — no new crypto
dependency, no JWT signing), 1-hour expiry, and revocation.

```
Mock Government IdP -> OAuth2 client_credentials grant -> CivicLens connector -> Dept A / B / C
```

`GovernmentConnector.authenticate()` (previously a `return True` stub) is now real:
`authenticate_via_federation()` (`app/interop/connectors/base.py`) performs the actual grant for
the connector's own seeded demo client, and `ConnectorRuntime.resolve()` **enforces** it — a
connector whose federation client is disabled or whose grant fails is refused with
`AUTHENTICATION_FAILURE` before any operation runs, not just described as a stub in the interface.
Every connector call in the live no-reupload demo goes through this gate today (verified: all
existing tests — including the full end-to-end demo — stayed green after wiring it in as a hard
gate, and `test_runtime_refuses_a_connector_whose_federation_client_is_disabled` proves it actually
blocks a disabled client, not just a disabled connector-registry row, which is a separate check).

REST surface (`app/api/v1/federation.py`, intentionally **not** gated by a CivicLens session — a
department's own system authenticates as itself via its client_id/client_secret, exactly like a
real OAuth2 token endpoint):

| Method | Path | Does |
|---|---|---|
| `GET` | `/federation/issuer` | Issuer metadata (clearly labelled mock/demo) |
| `POST` | `/federation/token` | The client_credentials grant — client_id + client_secret → access_token |
| `POST` | `/federation/introspect` | RFC 7662-shaped `{"active": bool, ...}` — never explains *why* a token is invalid |
| `POST` | `/federation/revoke` | "Logout" for a federated client — immediate, even before expiry |

Claims carried on every issued token: `client_id`, `system` (the role/department mapping — which
connector this client represents), `scope`, `issued_at`/`expires_at`. See
`tests/integration/test_federation_idp.py` for token issuance/validation/expiry/revocation/
disabled-client coverage, and `docs/DEMO_GUIDE.md` for a live curl walkthrough of the full grant.

## Connector registry

`app/interop/connector_registry.py` + `ConnectorRegistration` (`interop_connector_registry`).
One row per connector (`dept_a`, `dept_b`, `dept_c`; the existing real government adapters — CPGRAMS,
UMANG, state portals — could be registered here too as their credentials arrive), independent of
the business logic that calls them: `enabled`/`disabled` without touching the gateway,
`health_state` (`healthy | degraded | unavailable | not_configured | unknown`) computed from
**real** calls (`record_call` updates `total_calls`/`total_failures`/`avg_response_ms` on every
actual invocation — not a simulated heartbeat), and a manual `POST
/interop-gateway/connectors/{id}/health-check` that genuinely queries the connector's own tables.

## The no-reupload scenario, step by step

This is the demo the spec calls the single most important proof that CivicLens answers SIH26129:
a citizen's residence certificate, already verified and on file with Department A, satisfies
Department B's application requirement — the citizen never downloads or re-uploads anything.

Orchestrated by `InteropGatewayService.request_document_exchange`
(`app/services/interop_gateway_service.py`):

1. Look up the Department B application by `application_no`. If its document requirement is
   already `verified`, return `already_completed` immediately (idempotent — safe to call again).
2. Look up the Department B beneficiary and resolve their identity (§ Identity resolution above).
   If ambiguous, stop and return `identity_ambiguous` with the candidate id.
3. Find the matching Department A resident by normalized mobile number (falling back to name), and
   resolve *their* identity too. If ambiguous, stop the same way. If the two systems resolved to
   **different** master entities, stop and return `identity_conflict` (this should not happen in
   the normal case — it means the two resolutions genuinely disagree and a human must look).
4. Check for a granted consent for this exact (master, requesting system, providing system, data
   category) tuple. None exists yet on a fresh application → create a `pending` grant, audit
   `interop.consent_requested`, and return `consent_required` with the grant id. **Nothing has
   been read from Department A at this point.**
5. Once `POST /interop-gateway/consents/{id}/grant` is called, calling
   `request_document_exchange` again proceeds:
   - Calls the Department A connector (`mock_systems.dept_a_find_document`), timing the call and
     recording it against the connector registry.
   - Runs a document-specific quality check (not the generic grievance-shaped `score_quality` in
     `common_data_model.py` — reusing that rubric here would score irrelevant fields like
     "location" against a resident document and produce a misleading number; see
     `_document_quality` in the gateway service): source status is `verified`, a real-looking
     reference number, an issue date present. Below 70% quality, the exchange fails honestly
     with `data_quality_failed` and the specific issues, rather than writing bad data forward.
   - Writes Department A's reference into Department B's application
     (`mock_systems.dept_b_receive_document`) — **the actual no-reupload moment**: `document_status
     → verified`, `document_reference` set to Department A's reference, `status → processing`.
   - Records an `InteropTransaction` (source/target system, status, fields exchanged, duration),
     `UnifiedApplicationEvent` rows building the cross-department timeline
     (`identity_resolved_cross_system → document_fetched_from_dept_a →
     document_applied_to_dept_b_application`), and an `AuditService.record(...)` entry — all
     sharing one `correlation_id` set for the whole call via `correlation_id_var`
     (`app/core/logging.py`), so every row from a single exchange can be pulled back together.
6. Returns `success` with the document reference, quality score, transaction id, and correlation id.

## API

All endpoints below live at `/api/v1/interop-gateway/*` (`app/api/v1/interop_gateway.py`), gated on
two permissions: `INTEROP_READ` on every `GET`, `INTEROP_MANAGE` on every mutating call. `ADMIN` and
`SUPER_ADMIN` hold both; the dedicated `INTEGRATION_ADMIN` role holds both too but nothing outside
the interop platform (not `admin.users`/`departments`/`*_rules`); `AUDITOR` holds only
`INTEROP_READ` — it can watch every exchange, consent decision and identity resolution, but can
never make one. See `app/core/authorization.py`. The three consent-decision routes and
`/my-consents` are the exception — see "Citizen-controlled consent" above.

| Method | Path | Does |
|---|---|---|
| `POST` | `/document-exchange` | Runs (or resumes) the scenario above for one `application_no` |
| `GET` | `/timeline/{application_no}` | The full cross-department event timeline for one application |
| `GET` | `/transactions` | Recent `InteropTransaction` rows |
| `GET` | `/consents` | Every consent grant (admin view) |
| `GET` | `/my-consents` | The caller's own consent grants (citizen view, `PROFILE_MANAGE`-gated) |
| `POST .../grant` / `.../deny` / `.../revoke` | `/consents/{id}` | Consent decisions - the grant owner or an integration admin |
| `GET` | `/identity-candidates` | The manual-review queue |
| `POST` | `/identity-candidates/{id}/resolve` | Approve or reject an ambiguous match |
| `GET` | `/connectors` | Connector registry, with live health/call stats |
| `POST` | `/connectors/{id}/health-check` | Run a real health check now |
| `PUT` | `/connectors/{id}/enabled` | Enable/disable a connector |

## Running the demo yourself

1. Start the backend (`python run.py`) — mock system and connector-registry seed data load
   automatically and idempotently on startup (`app/main.py::_seed_interop_demo_data`).
2. Open classic-app (`npm run web` in `classic-app/`, or the already-running dev server) as an
   **admin** account, then Account → **Interop Gateway** (`classic-app/app/interop-gateway.tsx`).
3. Pick one of the two seeded demo applications (Priya Deshmukh / `APP-MH-2026-5501`, or Arjun
   Patil / `APP-MH-2026-5502`) and press **Request document exchange** — first call returns
   *consent required*.
4. Press **Grant consent**, then **Request document exchange** again — this time it completes,
   and the screen shows the document reference, quality score, and the full cross-department
   timeline.
5. The **Identity match review queue** and **Recent transactions** sections show the manual-review
   path and the machine-to-machine record respectively, and refresh after every action.

The same flow run over plain HTTP (exactly what the screen calls) is in `docs/DEMO_GUIDE.md`'s
curl walkthrough, and as an automated, repeatable test in the next section.

## Tests

`tests/integration/test_interop_gateway_e2e.py` is the end-to-end test the completion spec asks
for — it runs against a **live PostgreSQL** connection (unlike the rest of this suite, which runs
on in-memory doubles; see the file's docstring for why this subsystem is the exception) and
covers:

- The full happy path: consent required → grant → exchange succeeds → Department B's record is
  genuinely updated → calling again is idempotent → the timeline and transaction log are correct
  → the connector registry reflects the real call.
- The manual-review path: a deliberately weak name/mobile match is queued, not auto-linked, and
  an officer's reject creates a distinct identity rather than leaving the identifier dangling.
- A citizen without `INTEROP_MANAGE` cannot grant consent; an `AUDITOR` (real, live database) can
  read every surface but is refused by every mutating call, including the connector health check.

Every row the test creates is deleted in `tearDown`, scoped narrowly by the master entity ids and
fixture ids the test itself created — repeated runs stay deterministic and the shared dev database
is never left with accumulating test junk. It skips (not fails) cleanly if no live database is
reachable. Run it with `pytest tests/integration/test_interop_gateway_e2e.py -v`.

## Deferred (not built in this milestone)

Named here rather than left silently missing, per this project's rule against claiming
"implemented" for a placeholder:

- A `INTEGRATION_ADMIN`/`AUDITOR` login door in the legacy NiceGUI web admin (`app/ui/pages/public.py`)
  — classic-app routes both roles to a working home (the Interop Gateway screen) on login, but no
  screens exist for either role in the older NiceGUI admin app specifically
- A connector health *dashboard* (the data exists via `GET /connectors`; no charts/SLA view yet)
- Routing real interop events through the WebSocket event bus (`app/realtime/events.py`) — it's
  tightly coupled to the complaint/notification domain; this milestone uses the dedicated
  `InteropTransaction`/`UnifiedApplicationEvent` tables as the interop-specific record instead
- Field-mapping UI / service catalog / a fourth+ mock system
- `docs/CONNECTOR_GUIDE.md`, `docs/WORKFLOW_GUIDE.md`, and the full requirement traceability matrix

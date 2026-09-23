# CivicLens architecture

## Shape
```
 Expo app (TypeScript) ──HTTPS + Bearer──┐                       ┌── PostgreSQL (+pgvector)   source of truth
 NiceGUI pages (Python) ─in-process──────┼─► services ─► ports ─►├── Redis  queue transport, locks, pub/sub, shared rate limits
 REST clients ──cookie + CSRF────────────┘   (app/services,      ├── Ollama (chat/embeddings/vision) · STT (Whisper|Bhashini) · OCR (Tesseract|vision)
                     WebSocket /ws  ◄── events                   └── SMTP · Expo push · Google Drive/local storage · government adapters
```
Dependencies point inwards. Services, RAG and legal code know only *ports* (`app/services/ports.py`, `uow.py`), never a web framework or the ORM. `app/container.py` is the only place infrastructure is chosen and
it degrades honestly when an optional piece is absent. Routes (`app/api/v1`) and pages (`app/ui`) only authenticate → call a service → serialise.

## Complaint intake (one transaction)
validate → location → **rules-only** classification (native-script lexicons for 10 languages; no model, no network) → duplicate candidates → priority → routing rules (AI only a recorded fallback) → reference → assignment →
SLA → **workflow rules (`complaint.created`)** → persist + events + notifications + audit → job written **in the same transaction** (outbox). After commit: jobs pushed to Redis, events published.
`client_request_id` makes replays return the original complaint. `voice_id` links the unedited STT output; `description`/`language` are never rewritten.
Worker enrichment (only with the citizen's `ai_processing` consent): optional **derived** translation (separate columns) → model classification on the translated text if the rules were unsure → image analysis → routing of previously unroutable complaints.

## Voice
`VoiceService` (app/services/voice_service.py) is the single place audio becomes text; web upload and the mobile recorder both call it. Provider contract (`app/providers/stt.py`): return the spoken language in its own script, declare
`capabilities()` (languages, auto-detect), never translate. The service refuses undeclared languages/auto-detect, rejects an engine flagged as translating, flags wrong-script output (`script_ok=false`), and stores the record with
provider/detection/confidence/warnings. No engine ⇒ `NOT_CONFIGURED`.

## Jobs, notifications, real-time
* Jobs: PostgreSQL `jobs` is the truth (`pending → queued → running → succeeded | retrying → dead`, attempts, `started_at/finished_at`, error); Redis is transport. Idempotency keys, backoff, orphan repair
  (pending, queued and retrying jobs stranded by a Redis loss), admin retry of dead jobs. Kinds: `complaint.enrich`, `notification.email`, `notification.push`, `document.ingest`, `gov.submit`, `evidence.analyze`.
* Notifications: in-app is delivered in the transaction; e-mail and push follow `queued → sending → delivered | failed | not_configured` (state persisted *before* the external call; nothing is "delivered" without a real send).
* Real-time: `DomainEvent` (citizen-safe payload + staff-only part) → event bus (`LocalEventBus` in-process, `RedisEventBus` across processes) → `WebSocketManager`, which applies `may_receive(ctx, event)` **per connection**
  (owner / department / admin scope). Sockets are bound to their session: logout closes them, a periodic sweep drops sockets whose session expired or was revoked, failed sockets are dropped.

## Government platforms
`GovernmentSubmissionService`: request → consent (`data_sharing_government`) → adapter configured? → queued → submitting → `submitted` only after an adapter SUCCESS, else `failed`/`not_configured`/`consent_required`.
Canonical payload carries no citizen identity. When a platform's contract is supplied only the adapter mapping changes.

## Interoperability platform (cross-department document exchange)
`app/interop/mock_systems.py` + `identity_resolution.py` + `connector_registry.py` + `app/services/interop_gateway_service.py` + `app/db/models/interop_platform.py`. Distinct from the citizen-facing fragmentation/Golden-Record
tools in `app/interop/adapters.py`/`interop_service.py`: this is the middleware demo — three independently-schemad **mock** government systems (`resident_id` / `beneficiary_code` & `application_no` / `grievance_ref`, deliberately
unrelated identifier vocabularies, clearly labelled "(demo)" everywhere they surface), a confidence-scored `IdentityResolutionService` that links records across them (auto-links ≥0.90, queues an `IdentityMatchCandidate` for manual
review between 0.55–0.90, never below), fine-grained per-exchange `InteropConsentGrant`s (distinct from the broad `data_sharing_government` consent purpose), and a `ConnectorRegistration` registry with real health checks. The
gateway orchestrates the full no-reupload scenario — consent check/request → identity resolution across systems → Department A connector call → a document-specific quality check → the `dept_b_receive_document` write (the
actual no-reupload moment) → `InteropTransaction` + `UnifiedApplicationEvent` + `AuditService` — all tagged with one `correlation_id`. See `docs/INTEROPERABILITY.md` for the full write-up and demo script.

## Workflow rules (distinct from routing rules and SLA policies)
`trigger + conditions → action` (`complaint.created | complaint.status_changed | scheduled`; escalate, auto_close, assign_least_loaded, notify_admins, add_internal_note). A pure matcher, an idempotent executor
(unique rule×complaint), an event on the complaint, an audit record, admin CRUD (organisation-wide admins only) and a scheduled sweep for age-based rules.

## Security model
Argon2 passwords · TOTP encrypted at rest with replay protection · random session tokens stored **hashed** (web: HttpOnly SameSite=Lax cookie (+Secure in production) with CSRF token + Origin check; mobile: Bearer token in the OS secure store) ·
idle/absolute expiry, revocation on logout/password change · role & department from the DB row · RBAC + record-level checks + department isolation inside queries · MFA for privileged roles · admin-assisted password reset issues a
one-time token (never a password) · upload validation (extension + magic bytes + size, server-side names) · SSRF guard on outbound calls · prompt-injection defence (quarantine, fence, cite-or-withhold) · Redis-shared rate limits/lock-out with
in-process fallback (degraded mode is reported) · secrets redacted from logs · denied privileged actions audited. `tests/api/test_audits.py` scans for dangerous patterns and hard-coded credentials.

## Offline behaviour
* Web (NiceGUI cannot persist while disconnected): server-side drafts every 10 s, idempotent `client_request_id`, `draft → pending_sync → synced | failed`, header badge, "Sync now".
* Mobile: drafts + attachments + recordings persist on the device (app-private storage; token only in the secure store). `syncAll` (pure, tested) runs on reconnect, on foreground and in a background task: uploads each attachment once (evidence ids
  persisted per file), transcribes offline recordings then **stops for review** (never auto-submits), posts the complaint with `client_request_id`, backs off on network/5xx, stops on 401, surfaces 4xx to the user. `synced` is set only after the server returns a complaint id.

## Data
42 tables: migration `0001` (37) + `0004` (5 new: workflow_rules/executions, emergency_contacts, government_submissions, push_devices; 13 added columns). Both generated from the models by `scripts/generate_initial_migration.py` and drift-checked by a test;
`0002/0003` add the pgvector column and HNSW index. Readiness (`/api/v1/monitoring/ready`) reports whether the database is at the expected head. BM25 needs corpus statistics, so each process keeps an in-memory BM25 index synced from PostgreSQL;
vector search runs in PostgreSQL.

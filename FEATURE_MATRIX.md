# Feature matrix (final source tree)

**V** executed & verified here (unit/application tests on in-memory repositories and test doubles, real Tesseract, Node tests of the mobile logic, static audits) ·
**E** implemented, statically checked, **not run** (needs PostgreSQL / Redis / Ollama / FastAPI / NiceGUI / an Expo device) ·
**X** needs an external credential, API contract, dataset or browser capability ·
**M** genuinely missing (not built).
Columns: Logic (service) · Data (SQL repository + migration) · API · Web (NiceGUI) · Mobile · AuthZ (server-side).

| Feature | Logic | Data | API | Web | Mobile | AuthZ | Notes |
|---|---|---|---|---|---|---|---|
| Register / login / logout / sessions / `/me` | V | E | E | E | E | V | citizen-only registration; role never accepted from the client |
| Mobile Bearer sessions (14 d idle / 60 d cap, revocable) | V | E | E | – | E | V | HTTP tests written, skipped without FastAPI |
| 2-factor (TOTP, backup codes, re-auth to disable) | V | E | E | E | M (enrol screen) | V | login with OTP works on mobile; enrolment UI is web-only. Real pyotp/qrcode/argon2 wrappers: E |
| Password change / reset / admin-assisted one-time reset | V | E | E | E | M | V | e-mail link needs SMTP (X); without it the API says `email_delivery:not_configured`; admin issues a one-time token instead |
| Complaint intake, classification (10-language lexicons), routing, SLA, assignment, duplicates | V | E | E | E | E | V | rules-only at intake; AI is an async, consent-gated job |
| **Original text preserved; derived translation separate** | V | E | E | E | E | V | `description/language` never rewritten; translation needs a provider (X) |
| **Voice → same-language, native-script text (kn/hi/ta/te/en …)** | V (scripted engine) | E | E | E (upload) | E (live recorder) | V | guarantees tested with a scripted engine; **real-model accuracy X/unmeasured**; engines: Whisper (needs `faster-whisper`, model) / Bhashini (credentials) |
| Voice language picker limited to what the engine supports; auto-detect only if declared | V | – | E | E | V (state machine) / E (UI) | V | |
| Script-mismatch / translated-output detection | V | E | E | E | V | V | flags, never rewrites |
| Evidence upload, attach later, audited preview/download, re-analysis | V | E | E | E | E (upload at creation; M attach-later screen) | V | |
| Image analysis | V (states) | E | E | E | – | V | provider = Ollama vision (X for a model); else `IMAGE_ANALYSIS_UNAVAILABLE` |
| OCR (scanned PDFs / photos) | V (real Tesseract, eng) | E | via documents | E | – | V | Kannada/Hindi etc. need the Tesseract packs (X); vision-model OCR = Ollama (X) |
| Duplicate review (advisory, never merges) | V | E | E | E | – | V | |
| Officer workflow (queue, detail, field actions, escalation, resolve, close, investigation) | V | E | E | E | – | V | department isolation enforced in queries |
| Workflow rules engine (created / status-changed / scheduled) | V | E | E | E | – | V | organisation-wide admins only |
| SLA + escalation (scheduled) | V | E | – | E | – | V | scheduler process |
| Notifications: in-app / e-mail / push states (queued→sending→delivered\|failed\|not_configured) | V | E | E | E | E | V | e-mail needs SMTP (X); push needs Expo + EAS project (X) |
| Real-time: event → bus → manager → authorised sockets; session-bound; sweep | V (LocalEventBus, Redis subscriber path on a fake client) | – | E (`/ws`) | E | E (poll; WS client M) | V | Redis pub/sub on real Redis: E. Mobile uses polling while open; a WebSocket client screen is not built |
| Jobs: pending→queued→running→succeeded\|retrying→dead, timestamps, orphan repair, admin retry | V | E | E | E | – | V | real Redis: E |
| Rate limiting / lock-out (in-process + Redis-shared with fallback) | V (fake Redis) | – | E | – | – | V | fixed-window in Redis; degraded mode reported |
| RAG (BM25+vector+RRF+rerank+gates+grounding+citations+injection defence) via Copilot | V | E (pgvector) | E (POST only) | E | E | V | quality with a real embedding model unmeasured |
| Documents: upload→extract/OCR→chunk→embed→index, retry | V | E | E | E | – | V | |
| Legal analyzer, persisted history | V (real 856 rows) | E | E | E | E | V | metadata only; never states holdings |
| RTI draft / deadline / PDF / reminders | V | E | E | E | E (no PDF download) | V | non-Latin PDF needs `RTI_PDF_FONT` (X) |
| Government submission orchestration (consent → configured? → queued → submitted\|failed) | V (stub adapter) | E | E | E | – | V | **live submission X**: no platform contract/credentials; nothing is sent |
| Emergency hub (DB-configured, admin CRUD, public API) | V | E | E | E | E | V | empty ⇒ says "not configured"; six national helplines are *seed data* |
| Dashboards (citizen/officer/department/admin) + historical analytics | V | E | E | E | – | V | history reads hourly snapshots; "no data" until they exist |
| GIS radar | V | E | E | E | E | V | ward boundary polygons X (no dataset) |
| Anomaly detection | V | E | E | E | – | V | |
| Storage: Local and Google Drive on one interface + health | V (Drive on a fake client) | – | – | E (status) | – | – | Drive credentials X |
| Web offline drafts + idempotent sync | V | E | E | E | – | V | |
| Mobile offline drafts + sync engine | V (Node tests) | – | – | – | E (storage, NetInfo, background task) | – | never run on a device |
| Multilingual UI | V (fallback logic, drift test) | – | – | E | E | – | ported dictionary ×7; ~120 new strings EN+HI only (others fall back, reported) |
| Audit log (incl. denied privileged actions, evidence access, workflow, government) | V | E | E | E | – | V | |
| Migrations 0001–0004 generated from models, drift-checked, readiness check | V (structure) | E (not applied) | E | – | – | – | |
| Browser microphone capture on web | – | – | – | X (needs client-side JavaScript; web uses upload) | – | – | |
| Mobile: password-reset screen, 2FA enrolment screen, add-evidence-to-existing screen, document scanner | – | – | API exists | – | **M** | – | not built |
| Ported legacy screens: locator, department directory, official portal, diagnostics | – | – | – | – | **M** | – | in `mobile/legacy-prototype/` for reference |

# CivicLens

Civic grievance, RTI and legal-intelligence platform for Indian citizens.

| Part | Technology | Where |
|---|---|---|
| Backend / API / WebSocket | Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL + pgvector, Redis | `app/` |
| Web app (citizen, officer, admin) | Python **NiceGUI** (no JavaScript written) | `app/ui/` |
| Mobile app (citizen) | **React Native + Expo (TypeScript)** | `mobile/` |
| AI | Ollama (chat / embeddings / vision), hybrid RAG (BM25 + vectors + RRF + rerank), self-hosted or Bhashini speech-to-text, Tesseract / vision OCR | `app/rag`, `app/providers` |

One backend serves both clients: **there is no Node/Express server**. The mobile app is a client of the same FastAPI API and the same PostgreSQL,
queue, RAG and notification infrastructure as the web app. Business logic lives only in Python services; routes and screens are thin.

> **Read `VERIFICATION_REPORT.md` first.** It states exactly what was executed and what was only written. Short version: the domain/application
> layer and the mobile *logic* are covered by executed tests; FastAPI, NiceGUI, PostgreSQL, Redis, Ollama, real speech engines and the Expo app
> were **not** run in the build environment (no network / services / device).

## MULTILINGUAL VOICE INPUT

Speech language → **same-language transcription in its native script** → original text preserved → optional translation only as a *separate, derived* field.

* The citizen speaks Kannada → the text is Kannada (`ನನ್ನ ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ ಇದೆ`); Hindi stays Hindi; Tamil stays Tamil; Telugu stays Telugu; English stays English.
  Nothing is translated to English on the way in.
* The mobile screen shows the language, an **editable** transcription, Start/Stop/Cancel/Retry, and "Use this text". Language is either picked or **auto-detected**
  (auto only if the configured engine really supports it — the UI is driven by `GET /api/v1/voice/languages`, so it never offers what the engine cannot do).
* Engines (`STT_PROVIDER`): `whisper` (self-hosted `faster-whisper`, always called with `task="transcribe"`) or `bhashini` (ASR task only). None configured ⇒ `NOT_CONFIGURED`,
  no fake transcript. If an engine returns text in the wrong script (romanised/translated) the record is flagged `script_ok=false` with a warning — it is never silently rewritten.
* On the complaint: `description`/`language` (exposed as `original_text`/`original_language`) are the citizen's words and are never overwritten. `detected_language`, `input_method`
  (`typed|voice`), `voice_id` (the engine's *unedited* output is kept in `voice_transcripts`) and, if a translation provider is configured, `translated_text` + `translated_language`
  + `translation_provider` are separate fields, produced by the consent-gated background job. Classification works on native-script keyword lexicons (10 languages), so a Kannada
  complaint is routed without translation.
* The assistant answers in the user's language where the model supports it (`language` code is passed to the RAG prompt).
* Supported languages (registry `app/i18n/languages.py`, mirrored in `mobile/src/i18n/languages.ts`): en, hi, mr, bn, gu, pa, ta, te, kn, ml. *Engine* support is declared by each engine, not assumed. Accuracy of a real model for a
  given language was **not measured** here (see the report).
* Web: the NiceGUI Report page uses the same backend service via audio **upload** (live microphone capture in a browser needs JavaScript, which the web app deliberately does not use).

## Quick start (real environment)
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                       # fill DATABASE_URL, secrets, OLLAMA_*, EMBEDDING_DIMENSIONS, STT_*, OCR_* ...
createdb civiclens && psql civiclens -c 'CREATE EXTENSION vector'
export EMBEDDING_DIMENSIONS=<embedding model output size>
alembic upgrade head                       # 0001 schema, 0002 pgvector, 0003 HNSW, 0004 multilingual/workflow/integrations
python scripts/seed.py                     # departments, cities, routing rules, emergency contacts (config only)
ADMIN_SETUP_TOKEN=... python scripts/create_admin.py --email you@org --name "You"
python scripts/ingest_legal_metadata.py metadata.parquet --db
python scripts/verify_environment.py

python run.py                              # web + REST + WebSocket on :8080
python -m app.workers.run worker           # jobs: AI enrichment, e-mail, push, documents, government submission, evidence analysis
python -m app.workers.run scheduler        # SLA scan, RTI reminders, anomalies, workflow sweep, integration health, analytics snapshots
```
Mobile: see `mobile/README.md` (`npm install`, `npx expo install --fix`, set `EXPO_PUBLIC_API_URL`, `npx expo start`).

## Test & audit commands
```bash
python -m unittest discover -s tests -t .          # or python -m pytest -q
python scripts/audit_imports.py                     # internal imports resolve, no cycles, dependencies declared
python scripts/audit_ui_links.py                    # every web + mobile navigation target exists
python scripts/generate_initial_migration.py --check   # migrations == models
cd mobile && npm test                               # Node test runner over the pure TypeScript logic
cd mobile && sh tools/stubcheck.sh                  # tsc over the app against ambient stubs (no node_modules needed)
ruff check . && ruff format --check . && mypy app   # not run in the build environment
```

## Honest degradation (nothing pretends to work)
No Redis ⇒ jobs stay `pending` in PostgreSQL and are pushed later; rate limits use the in-process limiter and say so. No Ollama ⇒ rules-only routing, `ai_status` explains, RAG shows sources but composes no answer.
No STT/translation engine ⇒ `NOT_CONFIGURED`. No vision model ⇒ `IMAGE_ANALYSIS_UNAVAILABLE`. No OCR ⇒ scanned documents fail with a stated reason. No SMTP ⇒ e-mail `not_configured`. Push disabled ⇒ `not_configured`.
Government platforms (CPGRAMS, UMANG, Swachhata, BBMP Sahaaya, MyGov): orchestration, consent gate, state machine and admin view are complete; without base URL/key/endpoints the state is `not_configured` and **nothing is sent**.
The legal index is metadata-only (856 Supreme Court rows): it can show that a case exists; it never states a holding.

## Map
`app/core` config/security/RBAC/limits · `app/services` domain + application services · `app/rag` retrieval pipeline · `app/legal` precedents · `app/integrations` gov adapters · `app/providers` STT, OCR, vision, push ·
`app/i18n` languages + dictionaries · `app/db` models/repositories/UoW/schema check · `alembic/` migrations · `app/api/v1` REST · `app/ui` NiceGUI · `app/workers` queue/scheduler/handlers ·
`app/realtime` events + WebSocket manager · `mobile/` Expo app · `scripts/` operations + audits · `tests/` · `docs/` API contract.

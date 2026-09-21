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
The legal index has two layers: a metadata-only citation index (38,000+ Supreme Court judgments, 1950-2026 - can confirm a case exists, cites and dates) and a growing full-text corpus (`legal_judgments`/`legal_judgment_chunks`, ingested by `scripts/ingest_legal_fulltext.py`) that can quote and reason over what a case actually says wherever real text has been ingested. See `THIRD_PARTY_DATA.md` for the data's license and attribution.

## Map
`app/core` config/security/RBAC/limits · `app/services` domain + application services · `app/rag` retrieval pipeline · `app/legal` precedents · `app/integrations` gov adapters · `app/providers` STT, OCR, vision, push ·
`app/i18n` languages + dictionaries · `app/db` models/repositories/UoW/schema check · `alembic/` migrations · `app/api/v1` REST · `app/ui` NiceGUI · `app/workers` queue/scheduler/handlers ·
`app/realtime` events + WebSocket manager · `mobile/` Expo app · `scripts/` operations + audits · `tests/` · `docs/` API contract.

## Running with Docker
```
cp .env.example .env        # then edit it - at minimum APP_SECRET_KEY and EMBEDDING_DIMENSIONS
docker compose up -d --build
docker compose exec ollama ollama pull llama3.1:8b       # once, after first start
docker compose exec ollama ollama pull nomic-embed-text  # once, after first start
```
Brings up Postgres+pgvector, Redis, Ollama, a one-shot `migrate` service (runs `alembic upgrade
head` before `app`/`worker` start), the API/UI (`:8080`), and the background worker. Postgres/
Ollama ports are exposed to the host for local development convenience; remove those `ports:`
entries for anything beyond a single dev machine.

**Honesty note:** this Dockerfile/compose setup was written and statically checked (YAML parses,
service graph and env vars cross-referenced against `app/core/config.py`) but not build-tested
end-to-end, because this development environment has no Docker installed. Verify it with a real
`docker compose up --build` before relying on it.

## Backups
```
python scripts/backup_database.py backup                       # -> backups/civiclens_<db>_<timestamp>.dump
python scripts/backup_database.py restore backups/<file> --yes # DESTRUCTIVE: replaces current data
```
Reads `DATABASE_URL` the same way the app does, so it always targets whatever database is actually configured - never a hardcoded guess. Uses `pg_dump`/`pg_restore` custom format (compressed, consistent snapshot); verified end-to-end against a real database with `pg_restore --list`.

## License
CivicLens's own code is MIT-licensed (`LICENSE`). Ingested government judgment data carries its own separate license - see `THIRD_PARTY_DATA.md`.

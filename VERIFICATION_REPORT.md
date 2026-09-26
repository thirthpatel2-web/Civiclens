# CivicLens — Verification Report (release build)

> **Historical report — read this first.** This document records the *early* build, verified in an
> offline sandbox before any server, database or model had run (hence "not run" throughout).
> Everything it lists as unexecuted has since been run for real: the full suite is now **765 tests,
> passing against a live PostgreSQL database**, and a single live end-to-end session passed **31/31**
> checks across the whole interoperability platform. Current status lives in
> [`docs/REQUIREMENT_TRACEABILITY.md`](docs/REQUIREMENT_TRACEABILITY.md) and the
> [README](README.md); this file is kept unchanged below as the original record.


Written from the final source tree. Nothing here is carried over from earlier reports.

## A. Environment (exact)
Linux sandbox, **no network**. Python 3.12.3 (3.14 is the deployment target and was not available). Node v22.22.2, TypeScript (`tsc`) 6.0.3. Tesseract 5.3.4 with language data `eng`, `osd`; `pytesseract`, Pillow 12.1.1, `pypdfium2`, pandas 3.0.2.
**Not installed / not available:** FastAPI, Starlette, uvicorn, NiceGUI, Pydantic, SQLAlchemy, psycopg, pgvector, Alembic, redis, httpx, pytest, ruff, mypy, argon2-cffi, pyotp, qrcode, pyarrow, faster-whisper, `npm` packages (React Native, Expo…), Expo/Android/iOS tooling, a device, a microphone; **no PostgreSQL, Redis or Ollama server**. `scripts/verify_environment.py` prints this list (`MISSING` / `NOT_CONFIGURED` / `UNREACHABLE` entries are real).

## B. Commands run and results
| Command | Result |
|---|---|
| `python3 -m compileall -q app scripts tests tools` | OK |
| `python3 -m unittest discover -s tests -t .` (from a clean tree, bytecode disabled) | **Ran 537 tests — OK (skipped=25)** |
| `python3 scripts/audit_imports.py` | 0 problems (internal imports resolve, no import cycles, third-party imports declared) — it initially found 14 real problems, all fixed |
| `python3 scripts/audit_ui_links.py` | 0 problems — 70 navigation targets checked (43 web pages, 23 mobile routes) |
| `python3 scripts/generate_initial_migration.py --check` | migrations 0001 + 0004 identical to what the models generate |
| `cd mobile && node --experimental-strip-types --no-warnings --test tests/*.test.ts` | **30 tests, 30 pass, 0 fail** |
| `tsc` over all mobile `.ts/.tsx` (syntax) | 0 syntax errors |
| `sh mobile/tools/stubcheck.sh` (type-check against ambient stubs) | 0 errors in project code (errors caused only by the stubs' `any` typing are filtered: TS2503/TS7006/TS7031) |
| Mutation checks (defects injected one at a time, bytecode disabled) | 25 defects in this session's code (voice guarantees, Whisper `task`, translation overwrite, voice-id ownership, government consent/configured/success gates, workflow idempotency, duplicate-candidate check, evidence access, Redis limiter, socket sweep, push/`retrying` states, OCR empty-text, mobile sync/voice/client rules) — **all killed** (the one apparent survivor was a docstring edit; re-run on the real code line: killed). Earlier sessions: 29 more, all killed. |
| `pytest`, `ruff check`, `ruff format --check`, `mypy app`, `alembic heads/upgrade head`, `python -c "from app.main import create_app"`, `npm run typecheck` | **not run** — tools/packages/services unavailable |

## C. Tests skipped (25), each with its reason
* 22 — `fastapi/httpx not installed in this environment`: `tests/api/test_http_api.py` (17 HTTP tests of routers, cookies, CSRF, cross-origin, 2FA, RBAC, RAG POST-only, RTI PDF, WebSocket isolation; 5 more for Bearer/mobile login, public emergency, voice languages, devices, government states, evidence access).
* 1 — `argon2-cffi not installed`; 1 — `pyotp not installed`; 1 — `qrcode not installed` (real-library interoperability tests; the reference TOTP engine and test hasher are used otherwise).

## D. What the executed tests cover
Domain and application logic through the real composition root (`AppContainer`) on in-memory repositories: registration/login/2FA/sessions (web + mobile kinds), RBAC and department isolation, complaint intake (10-language native-script lexicons), original-vs-derived
text, voice → complaint, officer workflow, SLA/escalation, duplicate review, workflow rules, government submission state machine (stub adapter), notifications (in-app/e-mail/push states), job lifecycle, real-time propagation
(`LocalEventBus` and the Redis-subscriber path on a fake client → manager → fake sockets; audience isolation; session drop/sweep), RAG pipeline with a scripted model, legal analysis on the real 856 rows, RTI, documents, **real Tesseract OCR** (image, image-only PDF, ingestion end to end),
storage contract (Local + Drive fake), Redis limiters (fake client), analytics history, emergency configuration, admin-assisted reset, schema-check logic. Plus static audits (routes authenticated, no GET on RAG, nav↔pages, UI string keys, security patterns, imports, links, migrations vs models).
`tests/end_to_end/test_full_flow.py` runs the whole citizen → officer → admin flow across all layers in one test.

**Voice tests (critical requirement):** with a *scripted engine* (a test double that returns what a correct engine returns) Kannada, Hindi, Tamil, Telugu and English samples stay in their own language and script for both selected and auto-detected language; no English translation is produced or stored; a translating engine is rejected;
romanised/translated-looking output is flagged not altered; undeclared languages/auto-detect are refused; no engine ⇒ no transcript. These are **provider-independent tests, not real-provider tests**.

## E. Runtime verification actually performed
* Real Tesseract 5.3.4 (English) on a generated image and image-only PDF; document ingestion → chunks → BM25 search. Missing language pack reported as an error (Kannada pack absent here).
* Real Python execution of the whole domain/application layer and the mobile TypeScript logic (Node type-stripping).
* **No** application server, database, queue, model, browser or device was started.

## F. Externally blocked (internal side implemented)
PostgreSQL/pgvector, Redis, Ollama, FastAPI/NiceGUI runtime, Expo device/emulator, `faster-whisper` model and Bhashini credentials (voice accuracy for Kannada/Tamil/Telugu etc. is therefore **unmeasured**; Bhashini's request shape is written from its public docs and unverified),
Tesseract packs for Indic languages, SMTP, Expo push (EAS project + `EXPO_PUSH_ENABLED`), Google Drive credentials, government platform contracts/credentials (nothing is ever sent without them), ward-boundary dataset, browser-side microphone capture for the web app, the two reference inputs (`civiclens-source-updated(2).zip`, `SIH2026-IDEA-Presentation finalyyyyy.pdf`) that were never supplied — the web/mobile UI is **not** a reproduction of them.

## G. Genuine remaining limitations
1. Nothing above the domain layer has run: SQL semantics (constraints, `ON CONFLICT`, JSONB, pgvector), routes, NiceGUI pages, Redis behaviour, WebSocket transport, and the Expo app are written and statically audited only. Expect first-run fixes (NiceGUI `ui.run_with` + lifespan, upload `e.content`, Expo package versions — run `npx expo install --fix`).
2. Migration `0004` was generated and drift-checked, never applied.
3. Redis rate limiting is a fixed window (bursts up to 2× the limit across a window boundary); Redis behaviour verified only on a fake client. During a Redis outage the in-process limiter's counters start from zero (reported as degraded).
4. Mobile screens not built: password reset, 2FA enrolment, adding evidence to an existing complaint, document scanner, WebSocket client (polling is used); legacy prototype screens not ported. The API supports the first three.
5. New UI strings exist in English and Hindi only (other languages fall back to English and coverage is reported). Tamil/Telugu/Marathi/Bengali also lack 10 ported keys.
6. Web voice input is upload-based (no JavaScript by design).
7. Retrieval/embedding quality and STT/OCR accuracy for Indic languages are unmeasured.
8. Static-analysis tools (ruff, mypy) and the real `tsc` type-check against actual React Native types were not run.

## H. Commands to run in a real environment (in order)
```
pip install -r requirements-dev.txt && alembic upgrade head          # EMBEDDING_DIMENSIONS set
python -m pytest -q                                                   # the 25 skips become runs
ruff check . && ruff format --check . && mypy app
python scripts/seed.py && python scripts/create_admin.py ... && python scripts/ingest_legal_metadata.py <parquet> --db
python run.py &  python -m app.workers.run all &
python scripts/verify_environment.py
cd mobile && npm install && npx expo install --fix && npm run typecheck && npm test && npx expo start
```
Then run the citizen → officer → admin flow in a browser and on a phone, record a Kannada/Hindi/Tamil/Telugu sentence with your chosen engine, and fix what the first real run reveals.

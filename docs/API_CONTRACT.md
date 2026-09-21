# API contract (mobile ⇄ FastAPI)

Base: `{API_BASE_URL}/api/v1`. JSON unless multipart. Types: `mobile/src/api/types.ts` (mirror of the backend responses; keep in sync).

**Auth.** Web uses an HttpOnly cookie + `X-CSRF-Token`. Mobile uses `Authorization: Bearer <session_token>` from `POST /auth/mobile/login` (no cookie, no CSRF needed because a browser never attaches
a Bearer header automatically). Sessions are server-side, revocable, expiring (mobile: 14 days idle / 60 days absolute). Role and department always come from the database row. Admin/privileged
actions additionally need a verified second factor.

**Errors.** `{ "error": { "code", "message", "details?", "correlation_id" } }` with HTTP 401 (auth / `mfa_required`), 403, 404 (also for "not yours"), 409, 422 (`details` = field → message), 429 (`Retry-After`), 501 (`not_configured`).

| Method & path | Auth | Request → response |
|---|---|---|
| POST `/auth/register` | – | `{email,password,full_name}` → `{id,email,role:"citizen"}` (unknown fields such as `role` ⇒ 422) |
| POST `/auth/mobile/login` | – | `{email,password,otp?}` → `{user, mfa_verified, csrf_token, session_token, token_type:"Bearer"}`; 401 `mfa_required` if a code is needed |
| GET `/auth/me` · POST `/auth/logout` | Bearer | current session · revokes it (and closes its live sockets) |
| POST `/auth/password/forgot` | – | `{email}` → `{ok, message, email_delivery:"configured"\|"not_configured"}` (same for unknown accounts) |
| GET `/voice/languages` | Bearer | `{state, provider, auto_detect, languages:[{code,name,native,script}]}` — exactly what the engine supports |
| POST `/voice/transcribe` | Bearer | multipart `audio`, `language` (`auto`\|code) → `{id,status:OK\|NOT_CONFIGURED\|FAILED, transcript, language_requested, language_detected, detected_by, script_ok, warnings, confidence, error}`. **Same-language, native script, never translated.** |
| POST `/complaints` | Bearer | `{title,description,language,category?,ward?,lat?,lng?,client_request_id?,evidence_ids?,voice_id?}` → `{complaint, replayed, warnings}`; `client_request_id` makes it idempotent |
| GET `/complaints?filter=` · GET `/complaints/{id}` | Bearer | list · `{complaint,timeline,events,evidence,feedback}`; `complaint.original_text/original_language` = the citizen's words, `translated_text` = derived (optional) |
| POST `/complaints/evidence` (multipart `file`) · POST `/complaints/{id}/evidence` `{evidence_id}` | Bearer | upload · attach more evidence to an unfinished complaint |
| GET `/complaints/evidence/{id}/file` · POST `/complaints/evidence/{id}/analyze` | Bearer | authorised, audited download · re-run image analysis |
| POST `/complaints/{id}/feedback` | Bearer | `{rating 1-5, comment?}` |
| GET/POST `/complaints/{id}/government-submissions` | Bearer | per-platform state · `{platform}` → 202 `{state: consent_required\|not_configured\|queued\|…}` |
| POST `/assistant/ask` | Bearer | `{question, language, conversation_id?}` → grounded answer + citations (POST only; no GET on the RAG surface) |
| GET `/notifications` · POST `/notifications/{id}/read` · POST `/notifications/devices` `{token,platform}` | Bearer | list · mark read · register Expo push token |
| GET `/emergency/helplines?lang=` | – | `{configured, items[], notice}` (empty + `configured:false` if none are configured) |
| GET `/gis/radar` | Bearer | hotspots (citizens see only groups ≥ 3), offices |
| GET/POST `/rti`, POST `/rti/{id}/generate`, `/file` | Bearer | RTI drafting/tracking |
| POST `/legal/analyze` · GET `/legal/analyses[/{id}]` | Bearer | persisted analysis of verified-index records (metadata only) |
| GET/PUT `/profiles/me` · GET/PUT `/consent[/{purpose}]` | Bearer | profile (language) · consent |
| WebSocket `/ws` | Bearer header | server → client domain events, filtered per connection |

Staff/admin endpoints (`/officer/*`, `/admin/*`, `/monitoring/*`, `/analytics/*`, `/dashboards/*`) are listed by `GET /api/docs` (disabled in production) and audited by `tests/api/test_static_audit.py`.

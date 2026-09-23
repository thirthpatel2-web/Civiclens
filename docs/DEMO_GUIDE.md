# Demo guide: the no-reupload cross-department exchange

This is a copy-pasteable walkthrough of the SIH26129 demo over plain HTTP — the same calls the
Interop Gateway screen in classic-app makes. Every step below was run against a live local
instance of this backend while writing it; the responses shown are real, not illustrative.

## Prerequisites

- The backend running locally (`python run.py`) against a migrated PostgreSQL database
  (`alembic upgrade head`, currently through revision `0010`).
- An account with the `admin` or `super_admin` role, with two-factor authentication enrolled
  (`ADMIN_INTEGRATIONS`-gated endpoints require a session with `mfa_verified=true` — see
  `require_mfa_for_privileged` in `app/core/authorization.py`). If you don't have one yet:

  ```bash
  ADMIN_SETUP_TOKEN=... python scripts/create_admin.py --email you@example.org --name "Your Name"
  # then sign in and enrol 2FA via POST /api/v1/auth/mfa/enroll + /confirm, or through the app's
  # settings screen once one exists.
  ```

## 1. Log in and confirm a session

```bash
curl -s -c cookies.txt -X POST http://localhost:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.org","password":"..."}'
```

If two-factor is enrolled, add `"otp":"123456"` (the current code from your authenticator app).
The response's `csrf_token` is needed on every mutating call below as an `X-CSRF-Token` header.

## 2. Look at what's registered

```bash
curl -s -b cookies.txt http://localhost:8080/api/v1/interop-gateway/connectors | python -m json.tool
```

Three connectors: `dept_a` (Maharashtra Revenue Records System, demo), `dept_b` (Seva Setu Service
Application System, demo), `dept_c` (Nagrik Grievance Cell, demo) — each with its own
`health_state`, `total_calls`, `avg_response_ms`, all starting honest (`unknown`/`0`) until a real
call happens.

## 3. Ask for the exchange — first call always needs consent

```bash
curl -s -b cookies.txt -X POST http://localhost:8080/api/v1/interop-gateway/document-exchange \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF" \
  -d '{"application_no":"APP-MH-2026-5501"}'
```

```json
{"status": "consent_required", "consent_id": "752f67e8-77cf-4134-b593-ba2ffa403cce", "master_id": "98f1f38e-edfc-4340-b0d3-d0f515cbc2a2"}
```

Nothing has been read from Department A yet — this is the point. `master_id` is the resolved
identity shared across Department A and Department B's independently-schemad records for this
citizen (Priya Deshmukh, in the seeded demo data).

## 4. Grant the consent

```bash
curl -s -b cookies.txt -X POST http://localhost:8080/api/v1/interop-gateway/consents/752f67e8-77cf-4134-b593-ba2ffa403cce/grant \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF" -d '{}'
```

```json
{"status": "granted", "consent_id": "752f67e8-77cf-4134-b593-ba2ffa403cce", "expires_at": "2026-10-23T12:39:05.476206+00:00"}
```

## 5. Ask again — this time it actually runs

```bash
curl -s -b cookies.txt -X POST http://localhost:8080/api/v1/interop-gateway/document-exchange \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF" \
  -d '{"application_no":"APP-MH-2026-5501"}'
```

```json
{"status": "success", "transaction_id": "b632b761-a461-4cb9-952b-11d70c1fe66c", "application_id": "88308724-a555-4998-9e26-299a482399b0", "document_reference": "RC-MH-2026-7701", "quality_score": 1.0, "correlation_id": "37412e88-e0a9-43ae-9945-767546df7af5"}
```

`document_reference` is Department A's own reference number for Priya's residence certificate —
fetched, transformed, quality-checked, and written into Department B's application without the
citizen touching a file.

## 6. See the cross-department timeline

```bash
curl -s -b cookies.txt http://localhost:8080/api/v1/interop-gateway/timeline/APP-MH-2026-5501 | python -m json.tool
```

Three ordered events, all `status: "success"`, sharing the same `correlation_id` as the transaction
above: `identity_resolved_cross_system` (civiclens) → `document_fetched_from_dept_a` (dept_a) →
`document_applied_to_dept_b_application` (dept_b).

## 7. It's idempotent

Calling step 5 again returns `{"status": "already_completed", ...}` immediately — no second
connector call, no duplicate write. Check `GET /connectors` again and `dept_a`'s `total_calls`
will not have incremented a second time.

## The manual-review path (ambiguous identity)

To see the path where the resolver refuses to guess: introduce a beneficiary whose name/mobile
only weakly resembles an already-linked identity (lexical similarity in the 0.55–0.90 band — see
`docs/INTEROPERABILITY.md`'s Identity resolution section for the exact scoring). The exchange
returns `identity_ambiguous` with a `candidate_id` instead of proceeding:

```bash
curl -s -b cookies.txt http://localhost:8080/api/v1/interop-gateway/identity-candidates?status=pending
```

An officer resolves it explicitly:

```bash
curl -s -b cookies.txt -X POST http://localhost:8080/api/v1/interop-gateway/identity-candidates/{id}/resolve \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF" -d '{"approve": false}'
```

`approve: true` links the identifier to the proposed master entity at full confidence, attributed
to the officer. `approve: false` creates a *separate* master entity instead — the resolver never
leaves an identifier silently unlinked after a human has looked at it.

`tests/integration/test_interop_gateway_e2e.py::test_ambiguous_identity_match_requires_manual_review_before_anything_proceeds`
exercises this exact path automatically, against a real database, on every test run.

## Field-level consent (a narrower grant genuinely blocks the exchange)

To see the field-level enforcement Section 7 of the completion spec asks for: after step 3 above
(consent requested, not yet granted), narrow what's authorized before granting it -

```bash
curl -s -b cookies.txt -X GET http://localhost:8080/api/v1/interop-gateway/consents?status=pending
# find the consent_id from step 3, then, directly in the database (there's no "edit fields" UI
# yet - the enforcement is on the backend, this is just how to demonstrate it today):
# UPDATE interop_consent_grants SET fields = '["reference", "status"]' WHERE consent_id = '...';
```

Grant it, then request the exchange again:

```bash
curl -s -b cookies.txt -X POST http://localhost:8080/api/v1/interop-gateway/document-exchange \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF" \
  -d '{"application_no":"APP-MH-2026-5501"}'
```

```json
{"status": "failed", "reason": "data_field_not_consented", "denied_fields": ["issued_on"], "transaction_id": "...", "correlation_id": "..."}
```

Nothing was read from Department A - the check runs before the connector is called. The
`InteropTransaction` row for this attempt has `requested_fields: ["reference", "status", "issued_on"]`,
`approved_fields: ["reference", "status"]`, `denied_fields: ["issued_on"]`.
`tests/integration/test_interop_gateway_e2e.py::test_field_level_consent_refuses_an_exchange_missing_an_authorized_field`
exercises this automatically.

## Citizen-controlled consent

Any authenticated citizen who owns a consent grant can act on it directly, without
`INTEROP_MANAGE`:

```bash
curl -s -b citizen_cookies.txt -X POST http://localhost:8080/api/v1/interop-gateway/consents/{consent_id}/grant \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: $CITIZEN_CSRF" -d '{}'
```

A different citizen gets `403 permission_denied`. `GET /interop-gateway/my-consents` is the
citizen's own view of every grant attributed to them - no `INTEROP_READ` permission required.
`tests/integration/test_interop_gateway_e2e.py::test_citizen_can_grant_their_own_consent_but_not_someone_elses`
exercises this with two independent citizen accounts.

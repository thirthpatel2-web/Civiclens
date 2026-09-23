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

## Federated identity (mock Government IdP)

**DEMO / MOCK IDENTITY PROVIDER** - not a real government identity federation. This is the OAuth2
client_credentials grant every connector performs before it's used (`GovernmentConnector.authenticate()`);
here it is directly, the same way a real department's system would call it. No CivicLens login
needed - the client authenticates itself:

```bash
curl -s http://localhost:8080/api/v1/federation/issuer
```

```json
{"issuer": "CivicLens Government Identity Federation (demo)", "label": "DEMO / MOCK IDENTITY PROVIDER - not a real government identity federation", "grant_types_supported": ["client_credentials"], "token_endpoint": "/api/v1/federation/token", "introspection_endpoint": "/api/v1/federation/introspect", "revocation_endpoint": "/api/v1/federation/revoke"}
```

```bash
curl -s -X POST http://localhost:8080/api/v1/federation/token \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"dept_a","client_secret":"dept_a-demo-secret-not-for-production"}'
```

```json
{"access_token": "eUCHaN5GILFaBhA4EwcYzICOR-hDmTfsolNmzU1n4qQ", "token_type": "Bearer", "expires_in": 3600, "scope": "interop:read interop:write", "system": "dept_a"}
```

The wrong secret is refused with `401 authentication_failed` - never a token. Introspect and
revoke:

```bash
curl -s -X POST http://localhost:8080/api/v1/federation/introspect -H 'Content-Type: application/json' -d '{"token":"<access_token>"}'
# {"active": true, "client_id": "dept_a", "system": "dept_a", "scope": [...], "iss": "...", "exp": ...}

curl -s -X POST http://localhost:8080/api/v1/federation/revoke -H 'Content-Type: application/json' -d '{"token":"<access_token>"}'
# {"revoked": true}

curl -s -X POST http://localhost:8080/api/v1/federation/introspect -H 'Content-Type: application/json' -d '{"token":"<access_token>"}'
# {"active": false} - RFC 7662's own rule: never explain *why* a token is invalid
```

This is genuinely load-bearing, not a side demo: disable `dept_a`'s federation client (distinct
from disabling the connector in the registry) and every gateway call touching Department A starts
failing with `AUTHENTICATION_FAILURE` -
`tests/integration/test_connectors.py::test_runtime_refuses_a_connector_whose_federation_client_is_disabled`
exercises exactly this.

## Event bus: watching a real exchange publish, and a subscriber react

Every successful exchange (steps 1-5 above) publishes a real sequence of events to a Redis stream
(`civiclens:interop:events`) - `IdentityResolved`, `DocumentRequested`, `DocumentVerified`,
`DocumentTransferred`, `ExchangeCompleted`. Read them back directly, independent of the app:

```bash
python -c "
import redis, json
from app.core.config import Settings
r = redis.from_url(Settings.load().redis_url)
for eid, fields in r.xrange('civiclens:interop:events', count=20):
    e = json.loads(fields[b'data'])
    print(e['event_type'], e['source_system'], '->', e['destination'], e['correlation_id'][:8])
"
```

`NotificationSubscriber` is a real, separate consumer of this same stream - it never talks to the
gateway directly. Drain it and it turns `ExchangeCompleted` events into real in-app notifications
for the citizens named in their payload:

```bash
python -c "
import redis
from app.container import build_container
from app.core.config import Settings
from app.interop.events.bus import RedisInteropEventBus
from app.interop.events.subscribers import NotificationSubscriber
from app.services.notification_service import NotificationService

settings = Settings.load()
c = build_container(settings)
bus = RedisInteropEventBus(redis.from_url(settings.redis_url))
subscriber = NotificationSubscriber(c.uow_factory, NotificationService())
handled = subscriber.drain(bus, count=1000)
print('notifications created:', handled)
"
```

`tests/integration/test_interop_event_subscriber_e2e.py` runs exactly this - a real exchange, a
real Redis stream, a real notification row created by a subscriber that has no other coupling to
the gateway than the event it read - on every test run. (The snippet above drains the *entire*
stream history, not just your latest exchange; on a dev database that's accumulated a lot of
throwaway test citizens, that can hit a foreign-key error for a citizen who no longer exists - the
test file passes `start_id` to scope a drain to only the events one specific run just published,
which is the pattern a real background consumer would use too.)

## Data quality + central exception management

Both seeded demo applications' documents are already `verified`, so neither triggers a quality
failure through the UI as-is - `tests/integration/test_interop_gateway_e2e.py::test_data_quality_failure_blocks_the_write_and_is_recorded_honestly`
is the live, repeatable demonstration of this path: it seeds a resident whose document `status` is
`"pending"` instead of `"verified"`, runs the real exchange through `InteropGatewayService`, and
asserts both that Department B's record is never written and that a real `InteropException` row
was created with `error_code == "DATA_QUALITY_FAILURE"`. Run it directly to see it end to end:

```bash
DATABASE_URL=postgresql+psycopg://postgres:PASSWORD@localhost:5432/civiclens \
  .venv/Scripts/python.exe -m pytest tests/integration/test_interop_gateway_e2e.py::DocumentExchangeEndToEndTests::test_data_quality_failure_blocks_the_write_and_is_recorded_honestly -v
```

The same failure, reproduced over plain HTTP, returns:

```json
{"status": "failed", "reason": "data_quality_failed", "issues": ["source document status is not verified"], "transaction_id": "...", "correlation_id": "<uuid>"}
```

and is queryable through the exception center with the canonical taxonomy code
(`DATA_QUALITY_FAILURE`, not the gateway's lowercase reason string) and the same `correlation_id`:

```bash
curl -s -b cookies.txt "http://localhost:8080/api/v1/interop-gateway/exceptions?correlation_id=<uuid>" | python -m json.tool
```

```json
{"items": [{"exception_id": "<uuid>", "error_code": "DATA_QUALITY_FAILURE", "message": "source document status is not verified", "source_system": "dept_a", "target_system": "dept_b", "correlation_id": "<uuid>", "retryable": false, "retry_count": 0, "max_retries": 3, "next_action": "manual review required", "resolution_state": "open", "created_at": "...", "resolved_at": null}]}
```

`DATA_QUALITY_FAILURE` is not retryable (retrying against the exact same bad source data would
just fail again) - `POST .../exceptions/{id}/retry` refuses it and returns `null`. A
`CONNECTOR_UNAVAILABLE`/`CONNECTOR_TIMEOUT` exception, by contrast, is retryable: each
`POST .../exceptions/{id}/retry` moves it `open → retrying`, and once `retry_count` reaches
`max_retries` it moves to `dead` (the dead-letter state) automatically - or an operator can
dead-letter one directly with `POST .../exceptions/{id}/mark-dead`. Acting on an unknown or
malformed exception id is a safe 404, never a 500.

## SLA, alerts, and distributed transaction tracing

Every real connector call now carries a live SLA status:

```bash
curl -s -b cookies.txt http://localhost:8080/api/v1/interop-gateway/connectors | python -m json.tool
```

```json
{"connector_id": "dept_a", "health_state": "healthy", "total_calls": 407, "total_failures": 0, "avg_response_ms": 52.24, "sla_max_avg_response_ms": null, "sla_min_success_rate": null, "sla_status": "met"}
```

`sla_max_avg_response_ms`/`sla_min_success_rate` are `null` here — this connector was never given
its own thresholds, so it's evaluated against `app.interop.monitoring.sla`'s defaults (1000ms /
95% success rate). A connector that's never been called shows `sla_status: "unknown"`, not `"met"`
by default.

Driving a connector into an actual breach and back out again (enough repeated failures, then
enough recoveries to see exactly one alert per real transition, never one per failed call) needs
more calls than a short curl walkthrough can usefully show — that's exactly what
`tests/integration/test_monitoring_live.py::MonitoringLiveTests` does against a real, disposable
test connector row: 10 real failures breach the SLA and raise exactly one `SLA_BREACHED` alert and
one `CONNECTOR_UNAVAILABLE` alert (not two of each), 300 real successes recover it, and 10 more
failures after that raise a genuinely new alert. Run it directly:

```bash
DATABASE_URL=postgresql+psycopg://postgres:PASSWORD@localhost:5432/civiclens \
  .venv/Scripts/python.exe -m pytest tests/integration/test_monitoring_live.py -v
```

The alert log and acknowledge action are real HTTP endpoints regardless:

```bash
curl -s -b cookies.txt http://localhost:8080/api/v1/interop-gateway/alerts | python -m json.tool
curl -s -b cookies.txt -X POST http://localhost:8080/api/v1/interop-gateway/alerts/<alert_id>/acknowledge \
  -H "X-CSRF-Token: $CSRF"
```

Distributed transaction tracing pulls every row across the platform's tables sharing one
`correlation_id` back together — the same id already returned on every exchange result, failure,
and audit entry:

```bash
curl -s -b cookies.txt http://localhost:8080/api/v1/interop-gateway/trace/<correlation_id> | python -m json.tool
```

```json
{"correlation_id": "<uuid>", "transactions": [...], "exceptions": [...], "events": [...], "audit_entries": [...]}
```

An unknown correlation id is a clean 404 ("No activity recorded for this correlation id"), not an
empty 200 pretending there was something to show.

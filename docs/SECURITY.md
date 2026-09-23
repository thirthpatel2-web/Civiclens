# Security — interoperability platform

Scoped to the interop platform added in migration `0010` and `app/services/interop_gateway_service.py`.
For the rest of CivicLens's security model (passwords, sessions, rate limiting, upload validation,
SSRF guard, prompt-injection defence), see `ARCHITECTURE.md`'s "Security model" section — this
document only covers what's specific to cross-department data exchange.

## Authorization

Two permissions gate every endpoint (`app/core/authorization.py`): `INTEROP_READ` on every read,
`INTEROP_MANAGE` on every action that changes state. Five roles now exist; only three can reach
this subsystem at all:

| Role | `INTEROP_READ` | `INTEROP_MANAGE` | Can touch `admin.users`/`departments`/`*_rules` |
|---|---|---|---|
| CITIZEN, OFFICER | no | no | no |
| **AUDITOR** | yes | **no** | no |
| **INTEGRATION_ADMIN** | yes | yes | no |
| ADMIN, SUPER_ADMIN | yes | yes | yes |

AUDITOR is read-only by construction — it is never granted `INTEROP_MANAGE` anywhere in
`ROLE_PERMISSIONS`, not merely discouraged by convention. This is verified directly:
`test_authorization.py::test_auditor_reads_but_never_manages_interop` (pure permission matrix) and
`test_interop_gateway_e2e.py::test_auditor_can_read_but_never_manage_the_gateway` (a live database,
the actual service methods an auditor would call in production — confirmed a real `connector_health`
and `set_connector_enabled` call are both refused).

Both new roles are **privileged**: `is_privileged_role()` puts them alongside ADMIN/SUPER_ADMIN,
which means — enforced by the same single function everywhere, not three separately-maintained
checks —

- a session must have completed two-factor authentication this session (`require_mfa_for_privileged`,
  checked on every `INTEROP_READ`/`INTEROP_MANAGE` route via `guard(..., mfa_for_privileged=True)`,
  the default);
- only a super-admin can assign either role to an account (`can_assign_role`);
- only a super-admin can reset an INTEGRATION_ADMIN's or AUDITOR's password or deactivate their
  account (`admin_service.py::issue_password_reset`, `auth_service.py::set_active`).

`can_assign_role`'s "who may manage non-privileged accounts at all" check deliberately does **not**
widen to `is_privileged_role()` — it stays the narrower `_STAFF_MANAGERS = {ADMIN, SUPER_ADMIN}`.
An AUDITOR is privileged (MFA-gated) but was never given `ADMIN_USERS`; if that check had been
widened carelessly, an auditor could have used it to manage other accounts' roles despite never
holding the permission that's supposed to gate that. Covered by
`test_integration_admin_and_auditor_cannot_assign_roles_themselves`.

## Consent before any cross-system read

No data is read from a providing system until an `InteropConsentGrant` exists in `granted` status
for that exact (master identity, requesting system, providing system, data category) tuple.
`request_document_exchange` checks this *before* calling the connector, and returns
`consent_required` — with nothing else having happened — if it's missing. A consent expires 30
days after being granted and can be revoked at any time with a reason recorded. See
`docs/INTEROPERABILITY.md`'s "Consent" section for the full state machine.

## Identity resolution never silently merges

Two independent systems' records only link to the same identity automatically at ≥0.90 confidence,
with the matching evidence recorded (`MasterIdentifier.matched_on`). Between 0.55 and 0.90, nothing
is linked — the match is queued as an `IdentityMatchCandidate` and the exchange stops
(`identity_ambiguous`) until a human with `INTEROP_MANAGE` explicitly confirms or rejects it. A
reject doesn't leave the identifier dangling; it creates a distinct identity, attributed to the
officer who made that call, never to the algorithm. This is the concrete answer to "two different
citizens must never be merged into one record by an automated match."

## Audit trail

Every consent decision, every resolved identity candidate, and every completed or failed exchange
calls `AuditService.record(...)` — the same generic, redacting audit service the rest of CivicLens
uses (`app/services/audit_service.py`), not a separate, unaudited path. Every audit row, every
`InteropTransaction`, and every `UnifiedApplicationEvent` from one exchange share one
`correlation_id` (set via `app/core/logging.py`'s context variable for the duration of the call),
so a reviewer can reconstruct exactly what happened for one exchange without cross-referencing
timestamps.

## Federated connector authentication (mock Government IdP)

`GovernmentConnector.authenticate()` is a real OAuth2 client_credentials grant against the mock
Government IdP (`app/interop/federation/idp.py`), not a `return True` stub — and it's enforced:
`ConnectorRuntime.resolve()` calls it before handing back a connector, refusing with
`AUTHENTICATION_FAILURE` if the grant fails. Disabling a connector's federation client (distinct
from the connector-registry `enabled` flag) genuinely blocks every gateway call that would touch
it, verified by `test_runtime_refuses_a_connector_whose_federation_client_is_disabled`. Tokens are
opaque, hashed at rest (never a JWT the server would need to verify a signature on), expire after
1 hour, and revocation is immediate — checked before expiry, not instead of it. Every response from
`/api/v1/federation/*` and its own docs are labelled **DEMO / MOCK IDENTITY PROVIDER**; see
`docs/INTEROPERABILITY.md`'s "Federated identity / SSO" section.

## What's mock, so nothing here is a real exposure today

The three government systems this platform connects to are demo data (see
`docs/INTEROPERABILITY.md`'s "What's real, what's a demo" table) — no real citizen's real
government records pass through this code path yet. The security properties above (consent
gating, confidence-scored resolution, least-privilege RBAC, audit trail) are the real mechanism
that would apply unchanged the day a real department connector is added; only
`app/interop/mock_systems.py`'s query functions would be replaced with real calls.

## Field-level consent enforcement

`InteropGatewayService._execute_exchange` checks `REQUIRED_DOCUMENT_FIELDS` (the canonical fields
this exchange needs - `reference`, `status`, `issued_on`) against `consent.fields` **before**
calling the Department A connector at all - not after, and not just hiding denied fields from the
UI. A consent narrower than what the operation needs refuses the exchange with
`data_field_not_consented` and the exact denied field names, recorded on the `InteropTransaction`
row (`requested_fields`/`approved_fields`/`denied_fields` columns, migration `0011`) alongside
everything else about that attempt. Verified live:
`test_field_level_consent_refuses_an_exchange_missing_an_authorized_field`.

## Citizen-controlled consent

`InteropGatewayService.grant_consent`/`deny_consent`/`revoke_consent` accept the citizen a grant is
attributed to (`InteropConsentGrant.citizen_user_id == ctx.user_id`) as well as an
`INTEROP_MANAGE`-holding integration admin - checked in the service layer
(`_require_consent_actor`), since real authorization here is a data-dependent question ("is this
your consent?"), not a static role permission. The three routes accept any authenticated caller at
the API layer and rely on the service to refuse the wrong citizen; `GET /my-consents` is the
citizen-facing list, gated on `PROFILE_MANAGE` (every role holds it) rather than `INTEROP_READ`.
Every decision's audit record notes whether it was `self_service` or made on the citizen's behalf.
Verified live: `test_citizen_can_grant_their_own_consent_but_not_someone_elses` (two independent
CITIZEN-role accounts, neither holding any interop permission at all).

**Known limitation**: today's demo flow sets `citizen_user_id` to whoever calls
`request_document_exchange` (an `INTEROP_MANAGE` holder), since the mock demo personas (Priya
Deshmukh, Arjun Patil) aren't linked to real CivicLens accounts. The self-service *mechanism* above
is real and independently tested; end-to-end "a real citizen requests data sharing about
themselves" would need that identity linkage - the existing Golden Record feature
(`app.services.interop_service.MasterDataService`) is the natural place to build it, not yet done.

## Known gaps (named, not hidden)

- Connector-level rate limiting / abuse protection isn't implemented separately for this
  subsystem — it inherits whatever the surrounding request goes through
  (`app/core/rate_limit.py`), not a per-connector budget.
- `INTEGRATION_ADMIN` and `AUDITOR` currently authenticate through the same `/auth/login` /
  `/auth/admin/login` endpoints as every other role; no separate, more restricted login surface
  (e.g. IP allowlisting) exists for these two data-sensitive roles specifically.

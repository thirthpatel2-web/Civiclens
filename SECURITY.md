# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private reporting
instead: go to this repository's **Security** tab → **Report a vulnerability**. We aim to reply
within a few working days.

Useful details to include: the affected route, page or file, steps to reproduce, and what an
attacker could achieve.

## Scope

CivicLens is a Smart India Hackathon 2026 prototype. The three government department systems and
the federated identity provider it connects to are **demo systems with synthetic data** — no real
citizen's government records flow through it. Reports about the gateway's consent, identity
resolution, authorization and audit mechanisms are especially welcome, because those are designed
to apply unchanged once real departments are connected.

## How the platform protects data

A summary — the full model, including known gaps, is in [`docs/SECURITY.md`](docs/SECURITY.md)
and [`docs/DPDP_COMPLIANCE_CHECKLIST.md`](docs/DPDP_COMPLIANCE_CHECKLIST.md).

- **Consent before any cross-department read** — field-level, purpose-bound, 30-day expiry,
  revocable; checked before a connector is ever called.
- **Identity resolution never silently merges** — automatic links only at ≥ 0.90 confidence;
  ambiguous matches go to a human.
- **Role-based access control** — 6 roles; the `AUDITOR` role is read-only by construction; only a
  super-admin can grant integration roles.
- **Authentication** — Argon2 password hashing, server-side sessions revoked on logout and password
  change, CSRF protection, throttled logins with a single generic error (no account enumeration).
  Two-factor authentication (TOTP) is available but currently optional.
- **Audit and tracing** — every consent decision and data exchange is recorded, sharing one
  correlation ID per exchange.
- **Input hardening** — upload validation (extension, magic bytes, size), an SSRF guard on outbound
  calls, and prompt-injection defences on everything that reaches the AI.
- **Secrets** — never committed. `.env` is git-ignored; `.env.example` contains only empty
  placeholders.

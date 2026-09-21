# DPDP Act 2023 - engineering self-assessment

**This is not legal advice and is not a compliance certification.** It is an engineering-level
mapping of what this codebase actually does today against the publicly known principles of
India's Digital Personal Data Protection Act, 2023, written so a real review (a lawyer, and
whoever the deploying organization designates as its data protection contact) has a concrete
starting point instead of a blank page. Every "implemented" line below was checked against the
actual code, not assumed - the file/line references let you verify them yourself.

| Principle | Status | Where |
|---|---|---|
| Purpose-specific, granular consent | **Implemented** | `app/services/profile_service.py` - 4 named purposes (`ai_processing`, `data_sharing_government`, `document_storage`, `notifications_email`), each independently grantable/revocable via `PUT /api/v1/consent/{purpose}` |
| Consent is withdrawable | **Implemented** | Same endpoint, `granted: false` |
| Consent history is auditable (not just current state) | **Implemented** | `consent_records` is append-only; every change is also written to `audit_logs` via `AuditService` |
| Reasonable security safeguards - encryption at rest for sensitive fields | **Implemented** | MFA secrets encrypted (`cryptography`), passwords hashed (Argon2id), session tokens hashed before storage |
| Reasonable security safeguards - access control | **Implemented** | Role/permission system (`app/core/authorization.py`), department-scoped officer access, citizen-only-sees-own-data enforced in repositories, not just at the API layer |
| Reasonable security safeguards - audit trail of who accessed/changed what | **Implemented** | `audit_logs` table, `AuditService`, correlation IDs in structured logs |
| Breach readiness - error tracking that never leaks personal data | **Implemented** | `app/core/error_tracking.py`: `send_default_pii=False` is hardcoded, not configurable |
| **Right to erasure / account deletion** | **NOT implemented** | No endpoint exists to delete a citizen's account and associated personal data. This is a real gap, not a design choice - the schema (soft-deletable rows, audit-log retention vs. personal-data erasure) has not been designed for it. |
| **Right to access a full personal-data export** | **Partial** | A citizen can already read all their own complaints/documents/RTI applications/legal analyses through existing endpoints, but there is no single "export everything about me" endpoint. |
| **Grievance Officer designation** | **NOT implemented** | The Act requires a named grievance officer and contact method for data-protection complaints (distinct from the app's own civic-complaint grievance system). Nothing in the app or its documentation designates one - this is an organizational decision, not something to hardcode. |
| **Data retention / storage limitation policy** | **NOT implemented** | No automatic purge of old audit logs, resolved complaints, or stale documents. Everything is retained indefinitely today. |
| **Cross-border transfer restrictions** | **Depends on deployment** | The app itself makes no cross-border calls other than to whichever LLM/embedding/OCR provider is configured. If a cloud (non-self-hosted) Ollama-compatible provider is ever used instead of a local one, or Google Drive storage is enabled, verify hosting region against the Act's cross-border rules. |
| **Children's data / parental consent** | **Not applicable by design, unverified in practice** | Registration collects no age/date-of-birth, so the app cannot currently distinguish a child user from an adult. If citizen self-registration is ever opened to minors, this needs explicit handling. |
| **Data Protection Impact Assessment / Significant Data Fiduciary obligations** | **Not assessed** | Whether this classifies as a "Significant Data Fiduciary" depends on citizen volume and data sensitivity at actual deployment scale - a legal/business determination, not a code one. |

## What to do with this before a real deployment
1. Have an actual lawyer review this table against the final Act rules/regulations (subordinate rules were still being notified in stages as of this writing) and the specific deployment's scale.
2. Decide who the organization's Grievance Officer is and add their contact details to the privacy policy and app.
3. Build the erasure and full-export endpoints before onboarding real citizens, if legal review says they're required (they very likely are).
4. Define and implement an actual retention schedule (e.g. "resolved complaints kept N years, then anonymized").

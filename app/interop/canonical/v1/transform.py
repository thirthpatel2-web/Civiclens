"""Real transformation functions between each mock government system's native shape and the
canonical v1 schema. This is the layer Section 1 of the completion spec asks for made concrete:

    Department A format -> Connector -> External-to-Canonical Transformer -> Canonical Record
    Canonical Record -> Canonical-to-External Transformer -> Department B format

``app.services.interop_gateway_service`` calls these functions rather than passing raw ORM rows
or dicts between departments - a Department A document is fetched, transformed into a canonical
``Document``, and only the canonical record (or fields explicitly re-derived from it) crosses into
Department B's write path.

Only Document and Application are wired into the live no-reupload flow today. Adding a transform
for another canonical entity (Citizen, Consent, Grievance, ...) means writing the two functions
here, not touching orchestration logic.
"""

from __future__ import annotations

from typing import Any

from app.interop.canonical.v1.models import Application, Document

# ---------------------------------------------------------------------------------------------
# Department A: Maharashtra Revenue Records System (demo) - MockDeptADocument
# ---------------------------------------------------------------------------------------------


def dept_a_document_to_canonical(doc: Any) -> Document:
    """External (Dept A's own document row) -> canonical."""
    return Document(
        document_id=doc.document_id,
        document_type=doc.document_type,
        reference=doc.reference_no,
        status=doc.status,
        source_system="dept_a",
        owner_master_id=None,  # the caller attaches this once identity resolution has run
        issued_on=doc.issued_on.date() if doc.issued_on else None,
        raw={"resident_id": doc.resident_id},
    )


def canonical_document_to_dept_b_fields(doc: Document) -> dict[str, str]:
    """Canonical -> external: exactly what Department B's application needs written. This is the
    destination-side transform - Department B never sees Dept A's resident_id, issue date, or any
    field outside what it actually needs (data minimization, Section 27)."""
    return {"document_reference": doc.reference, "document_status": "verified" if doc.status == "verified" else doc.status}


# ---------------------------------------------------------------------------------------------
# Department B: Seva Setu Service Application System (demo) - MockDeptBApplication
# ---------------------------------------------------------------------------------------------

_DEPT_B_STATUS_TO_CANONICAL = {
    "pending_document": "WAITING_FOR_EXTERNAL_SYSTEM",
    "processing": "IN_PROGRESS",
    "approved": "APPROVED",
    "rejected": "REJECTED",
}
_CANONICAL_TO_DEPT_B_STATUS = {v: k for k, v in _DEPT_B_STATUS_TO_CANONICAL.items()}


def dept_b_application_to_canonical(app_row: Any, *, master_id: str | None) -> Application:
    """External (Dept B's own application row) -> canonical. Dept B's ``pending_document`` /
    ``processing`` / ``approved`` / ``rejected`` vocabulary maps onto the shared canonical state
    set (Section 22) so a citizen viewing their unified timeline sees one consistent vocabulary
    across departments, not each department's raw internal words."""
    return Application(
        application_id=app_row.application_no,
        reference=app_row.application_no,
        service_id=app_row.service_type,
        master_id=master_id,
        primary_system="dept_b",
        status=_DEPT_B_STATUS_TO_CANONICAL.get(app_row.status, "IN_PROGRESS"),
        raw={"beneficiary_code": app_row.beneficiary_code, "document_status": app_row.document_status},
    )


def canonical_status_to_dept_b_status(canonical_status: str) -> str:
    """Canonical -> external, the inverse map - used if a workflow step ever needs to push a
    canonical-level decision back into Dept B's own vocabulary."""
    return _CANONICAL_TO_DEPT_B_STATUS.get(canonical_status, "processing")

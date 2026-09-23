"""Three independently-schemad demonstration government systems for local SIH interoperability
demos - real, queryable, persisted rows (not static fixtures), each with its own identifier
vocabulary that the other two systems know nothing about. No department has given CivicLens a
live feed, so this is intentionally a demo environment: every row is clearly labelled MOCK/DEMO
wherever it surfaces in the UI, never presented as a real government connection.

  Department A - "Maharashtra Revenue Records System" (demo)   identifier: resident_id
  Department B - "Seva Setu Service Application System" (demo) identifier: beneficiary_code / application_no
  Department C - "Nagrik Grievance Cell" (demo)                 identifier: grievance_ref

The point these three make concrete: the same real person is "RES-MH-..." in one system, has no
representation at all in another until they interact with it, and the two would never spontaneously
agree on how to describe her - exactly the fragmentation SIH26129 describes. CivicLens's identity
resolution (identity_resolution.py) is what lets a request in system B end up correctly matched to
that person's record in system A, without either system changing anything about how it operates.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.interop_platform import (
    MockDeptADocument,
    MockDeptAResident,
    MockDeptBApplication,
    MockDeptBBeneficiary,
    MockDeptCGrievance,
)

__all__ = [
    "DEPT_A_NAME",
    "DEPT_B_NAME",
    "DEPT_C_NAME",
    "dept_a_find_document",
    "dept_a_get_resident",
    "dept_a_search_residents",
    "dept_b_applications_for_beneficiary",
    "dept_b_get_application",
    "dept_b_get_beneficiary",
    "dept_b_receive_document",
    "dept_b_search_beneficiaries",
    "dept_c_get_grievance",
    "dept_c_search_grievances",
    "seed_if_empty",
]

DEPT_A_NAME = "Maharashtra Revenue Records System (demo)"
DEPT_B_NAME = "Seva Setu Service Application System (demo)"
DEPT_C_NAME = "Nagrik Grievance Cell (demo)"


# ---------------------------------------------------------------------------------------------
# Deterministic demo data. Same citizen, three different shapes - this is the whole point.
# ---------------------------------------------------------------------------------------------


def seed_if_empty(session: Session) -> bool:
    """Idempotent: only inserts if Department A's demo resident table is empty. Safe to call on
    every app start. Returns True if it actually seeded anything."""
    if session.execute(select(MockDeptAResident).limit(1)).first() is not None:
        return False
    now = datetime.now(UTC)

    residents = [
        MockDeptAResident(resident_id="RES-MH-00101", full_name="Priya Deshmukh", mobile="9876543210", address="Flat 12, Shivaji Nagar", city="Pune", state="Maharashtra", created_at=now),
        MockDeptAResident(resident_id="RES-MH-00102", full_name="Arjun Patil", mobile="9822011223", address="204 Andheri West", city="Mumbai", state="Maharashtra", created_at=now),
        MockDeptAResident(resident_id="RES-MH-00103", full_name="Sunita Joshi", mobile="9765432109", address="Plot 8 Ramdaspeth", city="Nagpur", state="Maharashtra", created_at=now),
    ]
    for r in residents:
        session.add(r)
    session.flush()  # residents must exist before documents' FK references them

    documents = [
        MockDeptADocument(document_id=str(uuid.uuid4()), resident_id="RES-MH-00101", document_type="residence_certificate", status="verified", reference_no="RC-MH-2026-7701", issued_on=now, created_at=now),
        MockDeptADocument(document_id=str(uuid.uuid4()), resident_id="RES-MH-00102", document_type="residence_certificate", status="verified", reference_no="RC-MH-2026-7702", issued_on=now, created_at=now),
        MockDeptADocument(document_id=str(uuid.uuid4()), resident_id="RES-MH-00103", document_type="residence_certificate", status="pending", reference_no="RC-MH-2026-7703", issued_on=now, created_at=now),
    ]
    for d in documents:
        session.add(d)

    # Same real people as above, but Department B has never heard of "RES-MH-00101" - it only
    # knows its own beneficiary_code, and (deliberately) a slightly different phone formatting.
    beneficiaries = [
        MockDeptBBeneficiary(beneficiary_code="BEN-MH-90011", full_name="Priya S. Deshmukh", mobile_number="+91-9876543210", created_at=now),
        MockDeptBBeneficiary(beneficiary_code="BEN-MH-90012", full_name="Arjun R Patil", mobile_number="09822011223", created_at=now),
    ]
    for b in beneficiaries:
        session.add(b)
    session.flush()  # beneficiaries must exist before applications' FK references them

    applications = [
        MockDeptBApplication(application_no="APP-MH-2026-5501", beneficiary_code="BEN-MH-90011", service_type="Small Business Registration", status="pending_document", required_document_type="residence_certificate", document_status="missing", created_at=now, updated_at=now),
        MockDeptBApplication(application_no="APP-MH-2026-5502", beneficiary_code="BEN-MH-90012", service_type="Small Business Registration", status="pending_document", required_document_type="residence_certificate", document_status="missing", created_at=now, updated_at=now),
    ]
    for a in applications:
        session.add(a)

    grievances = [
        MockDeptCGrievance(grievance_ref="GRV-MH-3301", citizen_ref="CITZ-Priya-D", subject="Streetlight not working near Shivaji Nagar", status="open", department="Public Works", created_at=now),
    ]
    for g in grievances:
        session.add(g)

    return True


# ---------------------------------------------------------------------------------------------
# Department A connector surface (used by the interop gateway - see app/interop/connector_registry.py)
# ---------------------------------------------------------------------------------------------


def dept_a_get_resident(session: Session, resident_id: str) -> MockDeptAResident | None:
    return session.get(MockDeptAResident, resident_id)


def dept_a_find_document(session: Session, resident_id: str, document_type: str) -> MockDeptADocument | None:
    return session.execute(
        select(MockDeptADocument).where(MockDeptADocument.resident_id == resident_id, MockDeptADocument.document_type == document_type).order_by(MockDeptADocument.created_at.desc())
    ).scalars().first()  # fmt: skip


def dept_a_search_residents(session: Session, *, name_contains: str | None = None, mobile: str | None = None) -> list[MockDeptAResident]:
    q = select(MockDeptAResident)
    if mobile:
        digits = "".join(ch for ch in mobile if ch.isdigit())[-10:]
        q = q.where(MockDeptAResident.mobile.like(f"%{digits}"))
    rows = list(session.execute(q).scalars().all())
    if name_contains:
        needle = name_contains.strip().lower()
        rows = [r for r in rows if needle in r.full_name.lower() or any(tok in r.full_name.lower() for tok in needle.split())]
    return rows


# ---------------------------------------------------------------------------------------------
# Department B connector surface
# ---------------------------------------------------------------------------------------------


def dept_b_get_beneficiary(session: Session, beneficiary_code: str) -> MockDeptBBeneficiary | None:
    return session.get(MockDeptBBeneficiary, beneficiary_code)


def dept_b_search_beneficiaries(session: Session, *, name_contains: str | None = None, mobile: str | None = None) -> list[MockDeptBBeneficiary]:
    rows = list(session.execute(select(MockDeptBBeneficiary)).scalars().all())
    if mobile:
        digits = "".join(ch for ch in mobile if ch.isdigit())[-10:]
        rows = [r for r in rows if "".join(ch for ch in r.mobile_number if ch.isdigit()).endswith(digits)]
    if name_contains:
        needle = name_contains.strip().lower()
        rows = [r for r in rows if any(tok in r.full_name.lower() for tok in needle.split())]
    return rows


def dept_b_get_application(session: Session, application_no: str) -> MockDeptBApplication | None:
    return session.get(MockDeptBApplication, application_no)


def dept_b_applications_for_beneficiary(session: Session, beneficiary_code: str) -> list[MockDeptBApplication]:
    return list(session.execute(select(MockDeptBApplication).where(MockDeptBApplication.beneficiary_code == beneficiary_code)).scalars().all())


def dept_b_receive_document(session: Session, application_no: str, *, document_reference: str) -> MockDeptBApplication | None:
    """The no-reupload moment: Department B marks its application's document requirement satisfied
    using a reference CivicLens fetched from Department A - the citizen never touched a file."""
    app_row = session.get(MockDeptBApplication, application_no)
    if app_row is None:
        return None
    app_row.document_status = "verified"
    app_row.document_reference = document_reference
    app_row.status = "processing"
    app_row.updated_at = datetime.now(UTC)
    session.add(app_row)
    return app_row


# ---------------------------------------------------------------------------------------------
# Department C connector surface - not used by the headline no-reupload demo, but real and
# queryable, proving "at least three independent systems" is a fact rather than a claim.
# ---------------------------------------------------------------------------------------------


def dept_c_get_grievance(session: Session, grievance_ref: str) -> MockDeptCGrievance | None:
    return session.get(MockDeptCGrievance, grievance_ref)


def dept_c_search_grievances(session: Session, *, citizen_ref: str | None = None) -> list[MockDeptCGrievance]:
    q = select(MockDeptCGrievance)
    if citizen_ref:
        q = q.where(MockDeptCGrievance.citizen_ref == citizen_ref)
    return list(session.execute(q).scalars().all())

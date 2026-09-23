"""Service catalog & field mapping catalog (Section 8/22-23): a queryable directory of the
cross-department services this platform exposes (ServiceCatalogEntry) and the field-level
mappings each one actually performs (FieldMapping) - plain functions taking a session, the same
pattern connector_registry/exceptions.center/monitoring.alerts already use.

The mappings seeded here describe exactly what app.interop.canonical.v1.transform's real
functions do for the one flow currently wired into the live demo (residence certificate
verification) - not a parallel, independently-maintained description that could silently drift.
tests/unit/test_field_mapping_catalog.py cross-checks every seeded row against the real
transform functions' actual behavior on realistic fixture input.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.interop_platform import FieldMapping, ServiceCatalogEntry

DEFAULT_SERVICES: tuple[dict, ...] = (
    {
        "service_id": "residence_certificate_verification",
        "name": "Residence certificate verification",
        "description": "Satisfies a Department B application's residence-document requirement from a resident's existing, already-verified Department A record - the no-reupload scenario.",
        "source_system": "dept_a",
        "target_system": "dept_b",
        "data_category": "residence_certificate",
        "workflow_id": "residence_certificate_verification",
    },
)

DEFAULT_FIELD_MAPPINGS: tuple[dict, ...] = (
    {"mapping_id": "dept_a_document_to_canonical:document_id", "service_id": "residence_certificate_verification", "direction": "external_to_canonical", "system_id": "dept_a", "entity": "Document", "source_field": "document_id", "target_field": "document_id", "transform_note": "verbatim"},
    {"mapping_id": "dept_a_document_to_canonical:document_type", "service_id": "residence_certificate_verification", "direction": "external_to_canonical", "system_id": "dept_a", "entity": "Document", "source_field": "document_type", "target_field": "document_type", "transform_note": "verbatim"},
    {"mapping_id": "dept_a_document_to_canonical:reference", "service_id": "residence_certificate_verification", "direction": "external_to_canonical", "system_id": "dept_a", "entity": "Document", "source_field": "reference_no", "target_field": "reference", "transform_note": "renamed (Dept A calls it reference_no)"},
    {"mapping_id": "dept_a_document_to_canonical:status", "service_id": "residence_certificate_verification", "direction": "external_to_canonical", "system_id": "dept_a", "entity": "Document", "source_field": "status", "target_field": "status", "transform_note": "verbatim"},
    {"mapping_id": "dept_a_document_to_canonical:issued_on", "service_id": "residence_certificate_verification", "direction": "external_to_canonical", "system_id": "dept_a", "entity": "Document", "source_field": "issued_on", "target_field": "issued_on", "transform_note": "datetime truncated to date()"},
    {"mapping_id": "canonical_document_to_dept_b_fields:reference", "service_id": "residence_certificate_verification", "direction": "canonical_to_external", "system_id": "dept_b", "entity": "Document", "source_field": "reference", "target_field": "document_reference", "transform_note": "verbatim"},
    {"mapping_id": "canonical_document_to_dept_b_fields:status", "service_id": "residence_certificate_verification", "direction": "canonical_to_external", "system_id": "dept_b", "entity": "Document", "source_field": "status", "target_field": "document_status", "transform_note": "verbatim"},
)


def seed_if_empty(session: Session) -> bool:
    if session.execute(select(ServiceCatalogEntry).limit(1)).first() is not None:
        return False
    now = datetime.now(UTC)
    for svc in DEFAULT_SERVICES:
        session.add(ServiceCatalogEntry(**svc, active=True, created_at=now))
    session.flush()  # FieldMapping.service_id is a real FK into the rows just added above
    for m in DEFAULT_FIELD_MAPPINGS:
        session.add(FieldMapping(**m, created_at=now))
    return True


def list_services(session: Session, *, active: bool | None = None) -> list[ServiceCatalogEntry]:
    q = select(ServiceCatalogEntry).order_by(ServiceCatalogEntry.service_id)
    if active is not None:
        q = q.where(ServiceCatalogEntry.active == active)
    return list(session.execute(q).scalars().all())


def list_field_mappings(session: Session, *, service_id: str | None = None, system_id: str | None = None) -> list[FieldMapping]:
    q = select(FieldMapping).order_by(FieldMapping.mapping_id)
    if service_id:
        q = q.where(FieldMapping.service_id == service_id)
    if system_id:
        q = q.where(FieldMapping.system_id == system_id)
    return list(session.execute(q).scalars().all())

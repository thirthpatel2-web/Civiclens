"""GovernmentConnector implementation for Department B (Seva Setu Service Application System,
demo). Wraps app.interop.mock_systems' dept_b_* functions - including the actual no-reupload
write, ``update("application", ...)`` -> ``dept_b_receive_document``."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.interop import mock_systems
from app.interop.connectors.base import ConnectorResult, GovernmentConnector, authenticate_via_federation


class DeptBConnector(GovernmentConnector):
    connector_id = "dept_b"

    def __init__(self, session: Session) -> None:
        self._s = session

    def authenticate(self) -> bool:
        return authenticate_via_federation(self._s, self.connector_id)

    def health_check(self) -> ConnectorResult:
        try:
            mock_systems.dept_b_search_beneficiaries(self._s, name_contains=None)
            return ConnectorResult(ok=True, data={"state": "healthy"})
        except Exception as exc:  # noqa: BLE001
            return self.handle_error(exc)

    def get_entity(self, entity_type: str, entity_id: str) -> ConnectorResult:
        if entity_type == "beneficiary":
            row = mock_systems.dept_b_get_beneficiary(self._s, entity_id)
            return ConnectorResult(ok=row is not None, data=row, error_code=None if row is not None else "IDENTITY_NOT_FOUND")
        if entity_type == "application":
            row = mock_systems.dept_b_get_application(self._s, entity_id)
            return ConnectorResult(ok=row is not None, data=row, error_code=None if row is not None else "IDENTITY_NOT_FOUND")
        return ConnectorResult(ok=False, error_code="SCHEMA_VALIDATION_FAILURE", error_message=f"Department B has no entity type {entity_type!r}.")

    def query(self, entity_type: str, **filters) -> ConnectorResult:
        if entity_type == "beneficiary":
            rows = mock_systems.dept_b_search_beneficiaries(self._s, name_contains=filters.get("name_contains"), mobile=filters.get("mobile"))
            return ConnectorResult(ok=True, data=rows)
        if entity_type == "application":
            code = filters.get("beneficiary_code")
            if not code:
                return ConnectorResult(ok=False, error_code="SCHEMA_VALIDATION_FAILURE", error_message="query('application', ...) needs beneficiary_code.")
            return ConnectorResult(ok=True, data=mock_systems.dept_b_applications_for_beneficiary(self._s, code))
        return ConnectorResult(ok=False, error_code="SCHEMA_VALIDATION_FAILURE", error_message=f"Department B has no entity type {entity_type!r}.")

    def submit(self, entity_type: str, payload: dict) -> ConnectorResult:
        return ConnectorResult(ok=False, error_code="CONNECTOR_UNAVAILABLE", error_message="Submitting a brand-new application through this demo connector is not implemented - only updates to existing applications are.")

    def update(self, entity_type: str, entity_id: str, payload: dict) -> ConnectorResult:
        if entity_type != "application":
            return ConnectorResult(ok=False, error_code="SCHEMA_VALIDATION_FAILURE", error_message=f"Department B cannot update entity type {entity_type!r}.")
        document_reference = payload.get("document_reference")
        if not document_reference:
            return ConnectorResult(ok=False, error_code="SCHEMA_VALIDATION_FAILURE", error_message="update('application', ...) needs document_reference.")
        row = mock_systems.dept_b_receive_document(self._s, entity_id, document_reference=document_reference)
        return ConnectorResult(ok=row is not None, data=row, error_code=None if row is not None else "IDENTITY_NOT_FOUND")

    def fetch_document(self, owner_id: str, document_type: str) -> ConnectorResult:
        return ConnectorResult(ok=False, error_code="CONNECTOR_UNAVAILABLE", error_message="Department B does not hold source documents - it receives them from Department A.")

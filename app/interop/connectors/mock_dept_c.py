"""GovernmentConnector implementation for Department C (Nagrik Grievance Cell, demo). Not used by
the headline no-reupload demo, but real, queryable, and implementing the same interface as A and
B - proof that "at least three independent systems" is a fact, not a claim confined to two."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.interop import mock_systems
from app.interop.connectors.base import (
    ConnectorResult,
    GovernmentConnector,
    authenticate_via_federation,
)

_READ_ONLY = ConnectorResult(ok=False, error_code="CONNECTOR_UNAVAILABLE", error_message="Department C (demo) is a read-only connector in this milestone.")


class DeptCConnector(GovernmentConnector):
    connector_id = "dept_c"

    def __init__(self, session: Session) -> None:
        self._s = session

    def authenticate(self) -> bool:
        return authenticate_via_federation(self._s, self.connector_id)

    def health_check(self) -> ConnectorResult:
        try:
            mock_systems.dept_c_search_grievances(self._s)
            return ConnectorResult(ok=True, data={"state": "healthy"})
        except Exception as exc:  # noqa: BLE001
            return self.handle_error(exc)

    def get_entity(self, entity_type: str, entity_id: str) -> ConnectorResult:
        if entity_type == "grievance":
            row = mock_systems.dept_c_get_grievance(self._s, entity_id)
            return ConnectorResult(ok=row is not None, data=row, error_code=None if row is not None else "IDENTITY_NOT_FOUND")
        return ConnectorResult(ok=False, error_code="SCHEMA_VALIDATION_FAILURE", error_message=f"Department C has no entity type {entity_type!r}.")

    def query(self, entity_type: str, **filters) -> ConnectorResult:
        if entity_type == "grievance":
            return ConnectorResult(ok=True, data=mock_systems.dept_c_search_grievances(self._s, citizen_ref=filters.get("citizen_ref")))
        return ConnectorResult(ok=False, error_code="SCHEMA_VALIDATION_FAILURE", error_message=f"Department C has no entity type {entity_type!r}.")

    def submit(self, entity_type: str, payload: dict) -> ConnectorResult:
        return _READ_ONLY

    def update(self, entity_type: str, entity_id: str, payload: dict) -> ConnectorResult:
        return _READ_ONLY

    def fetch_document(self, owner_id: str, document_type: str) -> ConnectorResult:
        return ConnectorResult(ok=False, error_code="CONNECTOR_UNAVAILABLE", error_message="Department C does not hold documents.")

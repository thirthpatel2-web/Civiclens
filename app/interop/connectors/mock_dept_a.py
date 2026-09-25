"""GovernmentConnector implementation for Department A (Maharashtra Revenue Records System, demo).
Wraps app.interop.mock_systems' dept_a_* functions behind the standard interface - the gateway
never imports mock_systems directly (see app.interop.connectors.runtime)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.interop import mock_systems
from app.interop.connectors.base import (
    ConnectorResult,
    GovernmentConnector,
    authenticate_via_federation,
)

_READ_ONLY = ConnectorResult(ok=False, error_code="CONNECTOR_UNAVAILABLE", error_message="Department A (demo) is a read-only connector - it holds records, it does not accept new ones.")


class DeptAConnector(GovernmentConnector):
    connector_id = "dept_a"

    def __init__(self, session: Session) -> None:
        self._s = session

    def authenticate(self) -> bool:
        return authenticate_via_federation(self._s, self.connector_id)

    def health_check(self) -> ConnectorResult:
        try:
            mock_systems.dept_a_search_residents(self._s, name_contains=None)
            return ConnectorResult(ok=True, data={"state": "healthy"})
        except Exception as exc:  # noqa: BLE001 - a health check must never raise into the caller
            return self.handle_error(exc)

    def get_entity(self, entity_type: str, entity_id: str) -> ConnectorResult:
        if entity_type == "resident":
            row = mock_systems.dept_a_get_resident(self._s, entity_id)
            return ConnectorResult(ok=row is not None, data=row, error_code=None if row is not None else "IDENTITY_NOT_FOUND")
        return ConnectorResult(ok=False, error_code="SCHEMA_VALIDATION_FAILURE", error_message=f"Department A has no entity type {entity_type!r}.")

    def query(self, entity_type: str, **filters) -> ConnectorResult:
        if entity_type == "resident":
            rows = mock_systems.dept_a_search_residents(self._s, name_contains=filters.get("name_contains"), mobile=filters.get("mobile"))
            return ConnectorResult(ok=True, data=rows)
        return ConnectorResult(ok=False, error_code="SCHEMA_VALIDATION_FAILURE", error_message=f"Department A has no entity type {entity_type!r}.")

    def submit(self, entity_type: str, payload: dict) -> ConnectorResult:
        return _READ_ONLY

    def update(self, entity_type: str, entity_id: str, payload: dict) -> ConnectorResult:
        return _READ_ONLY

    def fetch_document(self, owner_id: str, document_type: str) -> ConnectorResult:
        doc = mock_systems.dept_a_find_document(self._s, owner_id, document_type)
        return ConnectorResult(ok=doc is not None, data=doc, error_code=None if doc is not None else "IDENTITY_NOT_FOUND")

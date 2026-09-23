"""GovernmentConnector: the interface every connector - mock demo system today, a real department
tomorrow - must implement. The gateway calls connectors ONLY through this interface, resolved by
``app.interop.connectors.runtime``, never by importing a mock-system module's functions directly.

Adding a new government system means: implement this interface, register it
(``app.interop.connector_registry``), define its field mappings (``app.interop.canonical.v1.transform``).
It never requires changing ``app.services.interop_gateway_service``'s orchestration logic.

``ConnectorResult.error_code`` uses the connector-level slice of the exception taxonomy
(CONNECTOR_TIMEOUT, CONNECTOR_UNAVAILABLE, REMOTE_SYSTEM_ERROR, SCHEMA_VALIDATION_FAILURE,
IDENTITY_NOT_FOUND) - see docs/INTEROPERABILITY.md's "Exception taxonomy" section for the full
list and which layer raises each one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConnectorResult:
    ok: bool
    data: Any = None
    error_code: str | None = None
    error_message: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class GovernmentConnector(ABC):
    """One instance per connector_id, constructed with whatever it needs to reach its system (for
    the demo connectors, a SQLAlchemy session over the mock tables; for a real connector, an HTTP
    client / SOAP client / SFTP client / DB pool - the interface is identical either way)."""

    connector_id: str

    @abstractmethod
    def authenticate(self) -> bool:
        """True if this connector can currently reach its system with valid credentials. Demo
        connectors always return True (there is nothing to authenticate against); a real connector
        would exchange/refresh a token here."""

    @abstractmethod
    def health_check(self) -> ConnectorResult:
        """A real check - for the demo connectors, an actual query against their own tables, not a
        hardcoded status string. Called through ``app.interop.connectors.runtime.call`` (see
        ``InteropGatewayService.connector_health``), which records the result against the
        connector registry's live stats and, via ``resolve()``, has already required this
        connector to pass its federation ``authenticate()`` first."""

    @abstractmethod
    def get_entity(self, entity_type: str, entity_id: str) -> ConnectorResult:
        """Fetch one record by its native id, e.g. ("resident", "RES-MH-00101")."""

    @abstractmethod
    def query(self, entity_type: str, **filters: Any) -> ConnectorResult:
        """Search records, e.g. query("resident", mobile="9876543210")."""

    @abstractmethod
    def submit(self, entity_type: str, payload: dict[str, Any]) -> ConnectorResult:
        """Create a new record in the remote system. Read-only demo connectors refuse this
        honestly (CONNECTOR_UNAVAILABLE), never fabricate a created record."""

    @abstractmethod
    def update(self, entity_type: str, entity_id: str, payload: dict[str, Any]) -> ConnectorResult:
        """Update an existing record - the real operation behind the no-reupload write
        (Dept B's application.document_status/document_reference)."""

    @abstractmethod
    def fetch_document(self, owner_id: str, document_type: str) -> ConnectorResult:
        """The operation the no-reupload flow calls on the providing system."""

    def send_event(self, event_type: str, payload: dict[str, Any]) -> ConnectorResult:
        """Optional: push an event *to* this connector's system (most demo connectors have nothing
        to push to - default is a truthful no-op, not a fabricated delivery)."""
        return ConnectorResult(ok=True, data={"skipped": "no outbound event sink configured for this connector"})

    def transform_request(self, entity_type: str, canonical_payload: dict[str, Any]) -> dict[str, Any]:
        """Canonical -> this system's native shape, for write operations. Default: identity (a
        connector overrides this when its field names differ from the canonical ones)."""
        return canonical_payload

    def transform_response(self, entity_type: str, native_payload: dict[str, Any]) -> dict[str, Any]:
        """This system's native shape -> canonical, for read operations. Default: identity."""
        return native_payload

    def handle_error(self, exc: Exception) -> ConnectorResult:
        return ConnectorResult(ok=False, error_code="REMOTE_SYSTEM_ERROR", error_message=str(exc))


def authenticate_via_federation(session: Any, connector_id: str) -> bool:
    """Shared authenticate() implementation for the demo connectors: a real client_credentials
    grant (RFC 6749 s4.4) against the mock Government IdP (app.interop.federation.idp) - not a
    stub. Each demo connector's federation client secret is a fixed, publicly-documented demo
    value (idp.demo_client_secret); a real connector would hold its own real secret instead."""
    from app.interop.federation import idp

    try:
        idp.issue_token(session, client_id=connector_id, client_secret=idp.demo_client_secret(connector_id))
        return True
    except idp.InvalidClient:
        return False

# Connector guide — adding a government system to the interoperability platform

How to add a new connector to CivicLens's interop platform: the interface every connector
implements, what registering one actually touches, and the honesty rule for anything that isn't a
demo system. See `docs/INTEROPERABILITY.md` for the architecture this sits inside, and
`docs/DATA_MODEL.md` for the exact schema of every table named below.

## The interface

Every connector — a mock demo system today, a real department tomorrow — implements
`GovernmentConnector` (`app/interop/connectors/base.py`). The gateway never talks to a connector
directly or imports a mock-system module's functions itself; it always goes through
`app.interop.connectors.runtime.call(session, connector_id, operation, *args, **kwargs)`, which
resolves the connector, requires it to pass `authenticate()` first, times the call, and records the
result against the connector registry's live stats — so a new connector gets health tracking, SLA
evaluation, and alerting (`docs/INTEROPERABILITY.md`'s "SLA thresholds & alerting" section) for
free, without writing any of that itself.

```python
class GovernmentConnector(ABC):
    connector_id: str

    def authenticate(self) -> bool: ...          # can this connector currently reach its system?
    def health_check(self) -> ConnectorResult: ... # a REAL check, not a hardcoded status
    def get_entity(self, entity_type: str, entity_id: str) -> ConnectorResult: ...
    def query(self, entity_type: str, **filters: Any) -> ConnectorResult: ...
    def submit(self, entity_type: str, payload: dict) -> ConnectorResult: ...
    def update(self, entity_type: str, entity_id: str, payload: dict) -> ConnectorResult: ...
    def fetch_document(self, owner_id: str, document_type: str) -> ConnectorResult: ...

    # optional, with honest defaults - override only what your system actually needs:
    def send_event(self, event_type: str, payload: dict) -> ConnectorResult: ...       # default: truthful no-op
    def transform_request(self, entity_type: str, canonical_payload: dict) -> dict: ... # default: identity
    def transform_response(self, entity_type: str, native_payload: dict) -> dict: ...   # default: identity
    def handle_error(self, exc: Exception) -> ConnectorResult: ...                      # default: REMOTE_SYSTEM_ERROR
```

Every method returns a `ConnectorResult(ok, data, error_code, error_message, meta)` — never raises
for an expected failure (an unknown entity type, a read-only connector refusing a write). A method
that genuinely can't do what's asked returns `ok=False` with a real `error_code` from
`app.interop.exceptions.taxonomy.EXCEPTION_TYPES`'s connector-level slice
(`CONNECTOR_TIMEOUT`, `CONNECTOR_UNAVAILABLE`, `REMOTE_SYSTEM_ERROR`, `SCHEMA_VALIDATION_FAILURE`,
`IDENTITY_NOT_FOUND`) — never fabricates success.

## Steps to add a connector

1. **Implement the interface** — `app/interop/connectors/mock_dept_<x>.py` (or, for a real system,
   wherever it makes sense — an HTTP client, a SOAP client, an SFTP poller, a direct DB pool behind
   the same four read/write methods). `DeptCConnector` (`mock_dept_c.py`) is the shortest real
   example: a read-only connector that answers `submit`/`update`/`fetch_document` honestly with
   `CONNECTOR_UNAVAILABLE` rather than a write it can't perform.

2. **Wire authentication** — for a demo connector, call the shared
   `app.interop.connectors.base.authenticate_via_federation(session, self.connector_id)`, which
   performs a real OAuth2 `client_credentials` grant (RFC 6749 §4.4) against the mock Government
   IdP (`docs/INTEROPERABILITY.md`'s "Federated identity / SSO" section — **DEMO / MOCK IDENTITY
   PROVIDER**, never claimed as a real government IdP integration). A real connector authenticates
   however that system actually requires and holds its own real credential, never the demo secret.

3. **Register it in the connector registry**
   (`app.interop.connector_registry.DEFAULT_CONNECTORS`) — `connector_id`, `name`, `department`,
   `supported_operations`. This is what makes it show up in `GET /interop-gateway/connectors`, gets
   it health/SLA tracking, and lets an integration admin enable/disable it independently of the
   business logic that calls it.

4. **Register it in the connector runtime**
   (`app.interop.connectors.runtime._CONNECTOR_CLASSES`) — one line mapping `connector_id` to the
   class from step 1. This is the only place that knows which concrete class backs which id;
   `InteropGatewayService`'s orchestration logic never changes when a connector is added.

5. **If it has a federation client** — add a `FederationClient` row (migration-seeded like the
   existing three, or created directly for a real system with its own real secret hash) so
   `authenticate()` has something to authenticate against.

6. **Write its field mappings** — `app.interop.canonical.v1.transform` gets the two functions that
   convert this system's native shape to/from the canonical model (see
   `docs/INTEROPERABILITY.md`'s "Canonical data model" section for the full 16-dataclass shape;
   only `Document`/`Application` are wired into the live demo today). Then add the real mappings as
   data to `app.interop.catalog.DEFAULT_FIELD_MAPPINGS` (`docs/DATA_MODEL.md`'s "Service catalog &
   field mapping catalog" section) so they're queryable via `GET /interop-gateway/field-mappings` —
   and add a test asserting the catalog rows match the transform functions' real output, the same
   way `tests/unit/test_field_mapping_catalog.py` does for the existing ones, so the catalog can't
   silently drift from the code it describes.

7. **Add it to the service catalog** if it's the source or target of a real cross-department
   service (`app.interop.catalog.DEFAULT_SERVICES`), optionally linked to a `workflow_id`
   (`docs/WORKFLOW_GUIDE.md`) if the exchange needs more than the primary gateway's own steps.

8. **Test it** the way `tests/integration/test_connectors.py` tests the three existing connectors:
   interface conformance (every abstract method is really implemented, not stubbed), runtime
   resolution (a disabled connector or one whose federation client is disabled is genuinely
   refused, not silently allowed through), and that a real call updates the registry's live stats.

## Real government systems: never faked

CPGRAMS, UMANG, Swachhata, BBMP Sahaaya, MyGov and similar real government platforms must **never**
be implemented as if they were live and working when they aren't. Per this project's standing rule
against fabricating integrations: a connector for a real system that doesn't have working
credentials yet is registered with an honest status —
**ADAPTER READY / NOT CONFIGURED / OFFICIAL API OR CREDENTIAL REQUIRED** — not a class whose
`health_check()` always returns `ok=True`. The connector registry's `health_state` already has a
`not_configured` value for exactly this case; a `health_check()` that can't reach the real system
should return it honestly rather than fabricate `healthy`. When real credentials do arrive, the
same interface, the same registration steps, and the same field-mapping-catalog discipline apply —
nothing about the architecture changes, only which concrete class backs the connector_id.

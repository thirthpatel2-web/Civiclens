# Architecture diagrams — interoperability platform

Ten diagrams covering the interop platform built across Phases 1-9. Mermaid, so they render
inline on GitHub and most Markdown viewers — no separate image files to keep in sync with the code
they describe. Each one names the real file(s) it corresponds to; none of these are aspirational —
every box and arrow here is something that exists and is tested. See `docs/INTEROPERABILITY.md`
for the prose explanation each diagram accompanies.

## 1. System context

```mermaid
flowchart LR
    Citizen((Citizen)) -->|classic-app / web| API[CivicLens API\napp/api/v1]
    Officer((Integration admin\n/ Auditor)) -->|classic-app| API
    API --> Gateway[InteropGatewayService\napp/services/interop_gateway_service.py]
    Gateway --> Runtime[Connector Runtime\napp/interop/connectors/runtime.py]
    Runtime --> DeptA[(Dept A\nMaharashtra Revenue\nRecords System - demo)]
    Runtime --> DeptB[(Dept B\nSeva Setu Applications - demo)]
    Runtime --> DeptC[(Dept C\nNagrik Grievance Cell - demo)]
    Runtime --> IdP[Mock Government IdP\nDEMO / MOCK IDENTITY PROVIDER]
    Gateway --> DB[(PostgreSQL\ninterop_* tables)]
    Gateway --> Bus[[Redis Stream\ncivic:interop:events]]
    Bus --> Sub[NotificationSubscriber]
    Sub --> DB
```

## 2. Canonical data model & connector abstraction (Section 1)

`app/interop/canonical/v1/transform.py`, `app/interop/connectors/`

```mermaid
flowchart LR
    subgraph Dept A native shape
        A1[MockDeptADocument\nresident_id, reference_no, status]
    end
    A1 -->|dept_a_document_to_canonical| C1[Canonical Document\ndocument_id, reference, status, issued_on]
    C1 -->|canonical_document_to_dept_b_fields| B1[Dept B native shape\ndocument_reference, document_status]
    subgraph Dept B native shape
        B1
    end
```

## 3. Identity resolution / MDM (Section 3-4)

`app/interop/identity_resolution.py`

```mermaid
flowchart TD
    Start[New identifier from a system] --> Score[Score against existing MasterEntity\nname + mobile similarity]
    Score -->|confidence >= 0.90| Auto[Auto-link to existing master]
    Score -->|0.55 <= confidence < 0.90| Queue[IdentityMatchCandidate\nqueued, status=pending]
    Score -->|confidence < 0.55| New[Create a new MasterEntity]
    Queue -->|officer approves| Auto
    Queue -->|officer rejects| New
```

## 4. Consent lifecycle (Section 7-8)

`InteropConsentGrant`, `InteropGatewayService`

```mermaid
stateDiagram-v2
    [*] --> pending: request_document_exchange creates it\n(nothing read from the source system yet)
    pending --> granted: POST /consents/{id}/grant\n(citizen or INTEROP_MANAGE)
    pending --> denied: POST /consents/{id}/deny
    granted --> revoked: POST /consents/{id}/revoke
    granted --> expired: 30 days elapse
    granted --> [*]: exchange proceeds,\nfield-level check still enforced
```

## 5. Federated identity — DEMO / MOCK IDENTITY PROVIDER (Section 6)

`app/interop/federation/idp.py` — OAuth2 `client_credentials` (RFC 6749 §4.4)

```mermaid
sequenceDiagram
    participant Connector as GovernmentConnector
    participant IdP as Mock Government IdP (DEMO)
    Connector->>IdP: POST /federation/token\n(client_id, client_secret)
    IdP-->>Connector: bearer token (scoped, expiring)
    Connector->>Runtime: authenticate() = true
    Runtime->>Connector: call(operation, ...)
    Note over IdP: A disabled FederationClient\nrefuses the grant -> AUTHENTICATION_FAILURE,\nConnectorRuntime.resolve() refuses the connector
```

## 6. Event-driven pub/sub (Section 10-11)

`app/interop/events/`

```mermaid
flowchart LR
    Gateway[InteropGatewayService] -->|publish after commit, never before| Bus[[InteropEventBus\nRedis Streams / in-memory]]
    Bus --> Sub1[NotificationSubscriber\ndrain]
    Sub1 -->|ExchangeCompleted| Notif[(notifications table)]
    Note1[21 canonical event types\nIdentityResolved, ConsentRequested,\nDocumentRequested, ExchangeCompleted, ...]
```

## 7. Configurable workflow engine (Section 12-13)

`app/interop/workflow/engine.py`

```mermaid
flowchart TD
    Start([start / resume]) --> Step{Run next StepSpec}
    Step -->|condition_key falsy| Skip[Skip - not recorded as run]
    Step -->|requires_approval| Pause[status = waiting_approval]
    Pause -->|resume with approval| Step
    Step -->|success| Next[Merge context, advance]
    Step -->|failure, retries left| Retry[Retry - new WorkflowStepExecution row]
    Retry --> Step
    Step -->|failure, on_failure=skip| Next
    Step -->|failure, on_failure=branch:X| Jump[Jump to step X]
    Step -->|failure, on_failure=fail| Failed([status = failed])
    Next --> More{More steps?}
    More -->|yes| Step
    More -->|no| Done([status = completed])
```

## 8. Data quality engine & central exception management (Section 14-18)

`app/interop/quality/engine.py`, `app/interop/exceptions/`

```mermaid
flowchart LR
    Record[Any record - a dict] --> Engine[DataQualityEngine.evaluate]
    Rules[QualityRule list\nrequired/min_length/max_length/\nregex/in_set/not_in_future/\nstale_after_days/cross_field_equals] --> Engine
    Engine --> Result{status}
    Result -->|VALID| Pass[Proceed]
    Result -->|VALID_WITH_WARNINGS| PassWarn[Proceed, warnings logged]
    Result -->|REJECTED| Log[exceptions.center.log_exception\nclassify() -> canonical taxonomy code]
    Log --> Exc[(InteropException\nresolution_state)]
```

```mermaid
stateDiagram-v2
    [*] --> open: log_exception
    open --> retrying: retry() [retryable]
    retrying --> retrying: retry() again
    retrying --> dead: retry_count >= max_retries
    open --> dead: mark_dead() [operator gives up directly]
    open --> resolved: mark_resolved()
    retrying --> resolved: mark_resolved()
    dead --> [*]
    resolved --> [*]
```

## 9. Connector SLA & alerting (Section 19-20)

`app/interop/monitoring/`

```mermaid
flowchart TD
    Call[Real connector call\nvia ConnectorRuntime.call] --> Record[connector_registry.record_call]
    Record --> Counters[Update total_calls/total_failures/\navg_response_ms/health_state]
    Counters --> SLA[sla.evaluate_sla -> met / breached / unknown]
    SLA --> Transition{State changed\nsince last call?}
    Transition -->|SLA just breached| AlertSLA[ConnectorAlert: SLA_BREACHED]
    Transition -->|just became unavailable| AlertUn[ConnectorAlert: CONNECTOR_UNAVAILABLE]
    Transition -->|no change| NoAlert[No new alert -\nnever one per failed call]
```

## 10. Distributed transaction tracing & the interop schema (Section 21-23)

`InteropGatewayService.get_trace`

```mermaid
erDiagram
    InteropTransaction ||--o{ CORRELATION_ID : shares
    InteropException ||--o{ CORRELATION_ID : shares
    UnifiedApplicationEvent ||--o{ CORRELATION_ID : shares
    AuditLogModel ||--o{ CORRELATION_ID : shares
    ServiceCatalogEntry ||--o{ FieldMapping : describes
    ServiceCatalogEntry }o--|| ConnectorRegistration : source_system
    ServiceCatalogEntry }o--|| ConnectorRegistration : target_system
    ServiceCatalogEntry }o--o| WorkflowDefinition : workflow_id
    ConnectorRegistration ||--o{ ConnectorAlert : raises
```

`correlation_id_var` (`app/core/logging.py`) is set once per gateway call and threads through every
row above without any per-table plumbing added for tracing itself — `GET /trace/{correlation_id}`
is a read over data that already existed before Phase 7.

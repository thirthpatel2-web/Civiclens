"""Query routing: database question vs document question vs small talk.

**The model never writes SQL.** Database questions map to a fixed registry of typed,
parameterised handlers (``QuerySpec``). A handler is looked up by name in the
allowlist, its parameters are validated against a declared schema, and the caller's
permission is checked *before* it runs; handlers receive the authenticated
``AuthContext`` so they can scope results server-side. An LLM may *suggest* a name
(``validate_llm_route``) but the suggestion is only honoured if it is allowlisted.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from app.core.authorization import AuthContext, Permission, require
from app.core.exceptions import PermissionDenied, ValidationFailed

ParamType = Literal["str", "int", "date"]


@dataclass(frozen=True)
class ParamSpec:
    type: ParamType
    required: bool = False
    max_len: int = 80
    minimum: int | None = None
    maximum: int | None = None


@dataclass(frozen=True)
class QuerySpec:
    name: str
    description: str
    params: dict[str, ParamSpec]
    handler: Callable[[AuthContext, dict[str, Any]], Any]
    permission: Permission
    triggers: tuple[re.Pattern[str], ...] = ()
    extractor: Callable[[str], dict[str, Any]] | None = None


@dataclass(frozen=True)
class QueryResult:
    name: str
    params: dict[str, Any]
    data: Any


class QueryRegistry:
    def __init__(self, specs: list[QuerySpec] | None = None) -> None:
        self._specs: dict[str, QuerySpec] = {}
        for s in specs or []:
            self.register(s)

    def register(self, spec: QuerySpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"duplicate query name {spec.name!r}")
        self._specs[spec.name] = spec

    def names(self) -> list[str]:
        return sorted(self._specs)

    def get(self, name: str) -> QuerySpec | None:
        return self._specs.get(name)

    @staticmethod
    def _validate(spec: QuerySpec, params: dict[str, Any]) -> dict[str, Any]:
        unknown = set(params) - set(spec.params)
        if unknown:
            raise ValidationFailed(f"Unknown parameter(s): {', '.join(sorted(unknown))}")
        clean: dict[str, Any] = {}
        for pname, ps in spec.params.items():
            value = params.get(pname)
            if value is None or value == "":
                if ps.required:
                    raise ValidationFailed(f"Parameter {pname!r} is required.")
                continue
            if ps.type == "str":
                if not isinstance(value, str) or len(value) > ps.max_len or re.search(r"[\x00-\x1f]", value):
                    raise ValidationFailed(f"Parameter {pname!r} is invalid.")
                clean[pname] = value.strip()
            elif ps.type == "int":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValidationFailed(f"Parameter {pname!r} must be an integer.")
                if (ps.minimum is not None and value < ps.minimum) or (ps.maximum is not None and value > ps.maximum):
                    raise ValidationFailed(f"Parameter {pname!r} is out of range.")
                clean[pname] = value
            else:
                try:
                    clean[pname] = value if isinstance(value, date) else date.fromisoformat(str(value))
                except ValueError as exc:
                    raise ValidationFailed(f"Parameter {pname!r} must be an ISO date.") from exc
        return clean

    def execute(self, name: str, params: dict[str, Any], ctx: AuthContext) -> QueryResult:
        spec = self._specs.get(name)
        if spec is None:
            raise PermissionDenied("Requested query is not in the allowlist.")
        require(ctx, spec.permission)
        clean = self._validate(spec, params or {})
        return QueryResult(name, clean, spec.handler(ctx, clean))


@dataclass
class RoutePlan:
    needs_db: bool = False
    query_name: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    needs_docs: bool = True
    smalltalk: bool = False
    reasons: list[str] = field(default_factory=list)


_SMALLTALK = re.compile(r"^\s*(?:hi|hello|hey|namaste|thanks?|thank you|good (?:morning|afternoon|evening))\b[\s!.?]*$", re.I)
_DOC_WORDS = re.compile(r"\b(?:why|explain|policy|policies|rule|rules|procedure|circular|document|report|according|says?|mention)\b", re.I)


class QueryRouter:
    def __init__(self, registry: QueryRegistry) -> None:
        self._registry = registry

    def route(self, question: str) -> RoutePlan:
        if _SMALLTALK.match(question or ""):
            return RoutePlan(needs_docs=False, smalltalk=True, reasons=["greeting/small talk"])
        plan = RoutePlan()
        for name in self._registry.names():
            spec = self._registry.get(name)
            assert spec is not None
            if any(t.search(question) for t in spec.triggers):
                plan.needs_db, plan.query_name = True, name
                plan.params = spec.extractor(question) if spec.extractor else {}
                plan.reasons.append(f"matched allowlisted query {name!r}")
                break
        plan.needs_docs = (not plan.needs_db) or bool(_DOC_WORDS.search(question))
        if plan.needs_docs and not plan.reasons:
            plan.reasons.append("default: document retrieval")
        return plan

    def validate_llm_route(self, suggestion: dict[str, Any]) -> RoutePlan:
        """Sanitise an LLM-proposed plan: anything not allowlisted degrades to documents."""
        name = suggestion.get("sqlFunction")
        if isinstance(name, str) and self._registry.get(name) is not None:
            params = suggestion.get("sqlParams")
            return RoutePlan(
                needs_db=True, query_name=name, params=params if isinstance(params, dict) else {},
                needs_docs=bool(suggestion.get("needsRag", False)), reasons=["llm suggestion (allowlisted)"],
            )  # fmt: skip
        return RoutePlan(reasons=["llm suggestion rejected: not allowlisted; using documents"])

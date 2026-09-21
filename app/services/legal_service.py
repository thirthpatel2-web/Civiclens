"""Legal Analyzer application service: analyse -> persist -> audit -> retrieve.

Only what the analyzer actually produced is stored: verified-index precedent records, keyword-detected statute hints, the
coverage limitations, and model text *only if* it passed citation verification. No judgment text or holding is ever invented
(the indexed data is metadata-only)."""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.core.authorization import AuthContext, Permission, require
from app.core.exceptions import NotFound, ValidationFailed
from app.legal.analysis import LegalAnalysis, LegalAnalysisService
from app.services.audit_service import AuditService
from app.services.ports import LegalAnalysisRecord
from app.services.uow import UowFactory


def analysis_to_dict(a: LegalAnalysis) -> dict[str, Any]:
    return dataclasses.asdict(a)


class LegalApplicationService:
    def __init__(self, uow_factory: UowFactory, analyzer: LegalAnalysisService, clock: Callable[[], datetime] | None = None) -> None:
        self._uow, self._analyzer, self._clock = uow_factory, analyzer, clock or (lambda: datetime.now(UTC))

    def analyze(self, ctx: AuthContext, problem: str, *, disposal: str | None = None, year: int | None = None, source: str = "text") -> LegalAnalysisRecord:
        require(ctx, Permission.LEGAL_ANALYZE)
        problem = (problem or "").strip()
        if not 5 <= len(problem) <= 8000:
            raise ValidationFailed("Describe the matter in 5-8000 characters.", details={"field": "problem"})
        result = self._analyzer.analyze(problem, disposal=disposal, year=year)  # may call the model; outside any transaction
        rec = LegalAnalysisRecord(str(uuid.uuid4()), ctx.user_id, problem, result.status, analysis_to_dict(result), self._clock())
        with self._uow() as uow:
            uow.legal.add(rec)
            AuditService(uow.audit, self._clock).record("legal.analysis", actor_id=ctx.user_id, resource_type="legal_analysis", resource_id=rec.id, metadata={"source": source, "chars": len(problem), "status": rec.status, "precedents": len(result.precedents)})
            uow.commit()
        return rec

    def list_mine(self, ctx: AuthContext, limit: int = 50) -> list[LegalAnalysisRecord]:
        require(ctx, Permission.LEGAL_ANALYZE)
        with self._uow() as uow:
            return uow.legal.list_for_user(ctx.user_id, limit)

    def get_mine(self, ctx: AuthContext, analysis_id: str) -> LegalAnalysisRecord:
        require(ctx, Permission.LEGAL_ANALYZE)
        with self._uow() as uow:
            r = uow.legal.get(analysis_id)
            if r is None or r.user_id != ctx.user_id:
                raise NotFound("Analysis not found.")
            AuditService(uow.audit, self._clock).record("legal.analysis_viewed", actor_id=ctx.user_id, resource_type="legal_analysis", resource_id=r.id)
            uow.commit()
        return r

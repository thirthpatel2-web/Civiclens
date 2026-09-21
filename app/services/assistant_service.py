"""AI Copilot: allow-listed database queries + the RAG pipeline, with persisted conversations."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.core.authorization import AuthContext, Permission, Role, can_access_complaint, require
from app.core.exceptions import NotFound, ValidationFailed
from app.i18n.languages import language_name
from app.rag.query_router import ParamSpec, QueryRegistry, QuerySpec
from app.rag.rag_service import RagResponse, RagService
from app.services.complaint_status import FINISHED
from app.services.ports import ConversationMessage, ConversationRecord
from app.services.uow import UowFactory

_REF = re.compile(r"\b([A-Z]{2,5}-\d{8}-[A-Z0-9]{8})\b", re.I)
MAX_QUESTION = 2000


def build_query_registry(uow_factory: UowFactory) -> QueryRegistry:
    """Typed, permission-checked handlers. Each receives the authenticated context and scopes its
    own data; the model can only *name* one of these, never write SQL."""

    def status_of(ctx: AuthContext, p: dict[str, Any]) -> Any:
        with uow_factory() as uow:
            c = uow.complaints.get_by_reference(p["reference"].upper())
            if c is None or not can_access_complaint(ctx, owner_id=c.citizen_id, department_id=c.department_code):
                return {"found": False}
            return {"found": True, "reference": c.reference, "status": str(c.status), "category": c.category, "department": c.department_code, "priority": c.priority,
                    "sla_due_at": c.sla_due_at.isoformat() if c.sla_due_at else None, "escalation_level": c.escalation_level}  # fmt: skip

    def my_counts(ctx: AuthContext, p: dict[str, Any]) -> Any:
        with uow_factory() as uow:
            rows = uow.complaints.rows(citizen_id=ctx.user_id) if ctx.role is Role.CITIZEN else uow.complaints.rows(department_code=ctx.department_id)
        return {"total": len(rows), "open": sum(1 for r in rows if r.status not in FINISHED), "by_status": {str(k): v for k, v in Counter(r.status for r in rows).items()}}

    def rti_deadlines(ctx: AuthContext, p: dict[str, Any]) -> Any:
        with uow_factory() as uow:
            apps = [a for a in uow.rti.list_for_owner(ctx.user_id) if getattr(a.status, "value", a.status) == "filed"]
        return [{"reference": a.reference, "due_at": a.due_at.isoformat() if a.due_at else None, "estimated": a.deadline_is_estimate} for a in apps]

    def dept_sla(ctx: AuthContext, p: dict[str, Any]) -> Any:
        with uow_factory() as uow:
            rows = [r for r in uow.complaints.rows(department_code=ctx.department_id) if r.status not in FINISHED]
        now = datetime.now(UTC)
        return {"open": len(rows), "overdue": sum(1 for r in rows if r.sla_due_at and r.sla_due_at < now), "escalated": sum(1 for r in rows if r.escalation_level > 0)}

    ref_extract = lambda q: ({"reference": m.group(1)} if (m := _REF.search(q)) else {})  # noqa: E731
    return QueryRegistry([
        QuerySpec("complaintStatus", "Status of one complaint by reference", {"reference": ParamSpec("str", required=True, max_len=24)}, status_of, Permission.ASSISTANT_USE,
                  (re.compile(r"\b[A-Z]{2,5}-\d{8}-[A-Z0-9]{8}\b", re.I),), ref_extract),
        QuerySpec("myComplaintCounts", "Counts of the caller's complaints (or department's, for staff)", {}, my_counts, Permission.ASSISTANT_USE,
                  (re.compile(r"\bhow many\b.*\bcomplaints?\b|\bnumber of (my )?complaints\b|\bcount of (my )?complaints\b", re.I),)),
        QuerySpec("myRtiDeadlines", "Deadlines of the caller's filed RTI applications", {}, rti_deadlines, Permission.RTI_MANAGE_OWN, (re.compile(r"\brti\b.*\b(deadline|due|when|days left)\b|\b(deadline|due)\b.*\brti\b", re.I),)),
        QuerySpec("departmentSlaSummary", "Open/overdue/escalated counts for the staff member's department", {}, dept_sla, Permission.SLA_VIEW, (re.compile(r"\b(sla|overdue|escalat\w*)\b.*\b(summary|how many|count|status)\b|\bhow many\b.*\b(overdue|escalated)\b", re.I),)),
    ])  # fmt: skip


class AssistantService:
    def __init__(self, uow_factory: UowFactory, rag: RagService, clock: Callable[[], datetime] | None = None) -> None:
        self._uow, self._rag, self._clock = uow_factory, rag, clock or (lambda: datetime.now(UTC))

    def ask(self, ctx: AuthContext, question: str, *, conversation_id: str | None = None, language: str = "en") -> dict[str, Any]:
        require(ctx, Permission.ASSISTANT_USE)
        q = (question or "").strip()
        if not q or len(q) > MAX_QUESTION:
            raise ValidationFailed(f"Ask a question of 1-{MAX_QUESTION} characters.", details={"field": "question"})
        with self._uow() as uow:
            if conversation_id:
                conv = uow.conversations.get_conversation(conversation_id)
                if conv is None or conv.user_id != ctx.user_id:
                    raise NotFound("Conversation not found.")
            else:
                conv = ConversationRecord(str(uuid.uuid4()), ctx.user_id, q[:60], self._clock())
                uow.conversations.add_conversation(conv)
            uow.conversations.add_message(ConversationMessage(str(uuid.uuid4()), conv.id, "user", q, self._clock()))
            uow.commit()
        resp: RagResponse = self._rag.ask(q, ctx, language=language_name(language))
        with self._uow() as uow:
            uow.conversations.add_message(ConversationMessage(str(uuid.uuid4()), conv.id, "assistant", resp.answer or "", self._clock(), resp.status, resp.citations, resp.database_facts, resp.warnings))
            uow.commit()
        return {"conversation_id": conv.id, "status": resp.status, "answer": resp.answer, "citations": resp.citations, "database_facts": resp.database_facts, "database_query": resp.database_query,
                "warnings": resp.warnings, "insufficient_evidence": resp.insufficient_evidence, "route": resp.route}  # fmt: skip

    def history(self, ctx: AuthContext, conversation_id: str) -> list[ConversationMessage]:
        require(ctx, Permission.ASSISTANT_USE)
        with self._uow() as uow:
            conv = uow.conversations.get_conversation(conversation_id)
            if conv is None or conv.user_id != ctx.user_id:
                raise NotFound("Conversation not found.")
            return uow.conversations.list_messages(conv.id)

    def conversations(self, ctx: AuthContext) -> list[ConversationRecord]:
        require(ctx, Permission.ASSISTANT_USE)
        with self._uow() as uow:
            return uow.conversations.list_conversations(ctx.user_id)

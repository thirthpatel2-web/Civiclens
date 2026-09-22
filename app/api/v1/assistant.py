"""/api/v1/assistant: AI Copilot. All RAG operations are POST-only (no GET endpoints)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.serialize import to_jsonable
from app.container import AppContainer
from app.core.authorization import AuthContext, Permission
from app.core.dependencies import get_container, guard, limited
from app.schemas.api import AskBody, RouteBody

router = APIRouter(prefix="/assistant", tags=["assistant"])
USE = Depends(guard(Permission.ASSISTANT_USE))


@router.post("/route")
def route(body: RouteBody, ctx: AuthContext = USE, c: AppContainer = Depends(get_container)) -> dict:
    """Speak or type an issue in any language; get told which screen it belongs to and, for a civic
    complaint, which department. Deterministic and rules-only (IntentRouter + the same classifier
    real intake uses) - this is what mobile was missing: the web UI calls these services in-process
    (NiceGUI pages run server-side), but a REST client had no route to reach them at all.
    """
    intent = c.intent_router.route(body.text)
    result: dict[str, Any] = {
        "destination": intent.destination, "confidence": intent.confidence, "certain": intent.certain,
        "matched": intent.matched, "explanation": intent.explanation, "alternatives": c.intent_router.alternatives(body.text),
    }  # fmt: skip
    if intent.destination == "complaint":
        result["classification"] = c.complaints.preview_classification(ctx, "", body.text, body.ward)
    return result


@router.post("/ask")
def ask(body: AskBody, ctx: AuthContext = USE, c: AppContainer = Depends(get_container), _: None = Depends(limited("expensive"))) -> dict:
    return c.assistant.ask(ctx, body.question, conversation_id=body.conversation_id, language=body.language)


@router.post("/chat")
def chat(body: AskBody, ctx: AuthContext = USE, c: AppContainer = Depends(get_container), _: None = Depends(limited("expensive"))) -> dict:
    return c.assistant.ask(ctx, body.question, conversation_id=body.conversation_id, language=body.language)


@router.post("/conversations")
def conversations(ctx: AuthContext = USE, c: AppContainer = Depends(get_container)) -> dict:
    """POST (not GET): conversation content is part of the RAG surface, which exposes no GET routes."""
    return {"items": to_jsonable(c.assistant.conversations(ctx))}


@router.post("/conversations/{conversation_id}/messages")
def messages(conversation_id: str, ctx: AuthContext = USE, c: AppContainer = Depends(get_container)) -> dict:
    return {"items": to_jsonable(c.assistant.history(ctx, conversation_id))}

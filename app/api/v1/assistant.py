"""/api/v1/assistant: AI Copilot. All RAG operations are POST-only (no GET endpoints)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.serialize import to_jsonable
from app.container import AppContainer
from app.core.authorization import AuthContext, Permission
from app.core.dependencies import get_container, guard, limited
from app.schemas.api import AskBody

router = APIRouter(prefix="/assistant", tags=["assistant"])
USE = Depends(guard(Permission.ASSISTANT_USE))


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

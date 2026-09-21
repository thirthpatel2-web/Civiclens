"""/api/v1/voice: speech-to-text (Bhashini when configured) and translation. Never fabricates output."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.serialize import to_jsonable
from app.container import AppContainer
from app.core.authorization import AuthContext, Permission
from app.core.dependencies import get_container, guard, limited
from app.schemas.api import TranslateBody

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str = Form("auto"), ctx: AuthContext = Depends(guard(Permission.COMPLAINT_CREATE)), c: AppContainer = Depends(get_container), _: None = Depends(limited("upload"))) -> dict:  # type: ignore[type-arg]
    data = await audio.read(10 * 1024 * 1024 + 1)
    return to_jsonable(c.voice.transcribe(ctx, data, audio.content_type, language))  # type: ignore[no-any-return]


@router.post("/translate")
def translate(body: TranslateBody, ctx: AuthContext = Depends(guard(Permission.ASSISTANT_USE)), c: AppContainer = Depends(get_container), _: None = Depends(limited("expensive"))) -> dict:  # type: ignore[type-arg]
    """Explicit, user-requested translation - a *derived* result; it never touches stored originals."""
    return {"text": c.translation.translate(body.text, body.source, body.target), "provider": c.translation.provider_name, "derived": True}


@router.get("/languages")
def languages(ctx: AuthContext = Depends(guard(Permission.COMPLAINT_CREATE)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    """What the configured speech engine really supports: drives the language picker (and whether "auto-detect" is offered)."""
    return c.voice.capabilities()


@router.get("/status")
def status(ctx: AuthContext = Depends(guard(Permission.COMPLAINT_CREATE)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"speech_to_text": c.voice.capabilities()["state"], "translation": "CONFIGURED" if c.translation.available else "NOT_CONFIGURED", "image_analysis": "CONFIGURED" if c.vision else "IMAGE_ANALYSIS_UNAVAILABLE"}

"""Aggregates every v1 router under /api/v1."""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    assistant,
    auth,
    complaints,
    documents,
    federation,
    interop,
    interop_gateway,
    legal,
    misc,
    officer,
    rag,
    rti,
    voice,
)

api_router = APIRouter(prefix="/api/v1")
for r in (auth.router, complaints.router, rti.router, legal.router, assistant.router, rag.router, documents.router, voice.router, officer.router, admin.router, interop.router, interop_gateway.router, federation.router,
          misc.notifications, misc.profiles, misc.consent, misc.gis, misc.location, misc.dashboards, misc.analytics, misc.integrations, misc.monitoring, misc.emergency, misc.directory):  # fmt: skip
    api_router.include_router(r)

"""Wired application-service environment on in-memory doubles (test-only)."""

from __future__ import annotations

from app.core.authorization import AuthContext, Role
from app.services.complaint_common import ComplaintEffects
from app.services.complaint_service import ComplaintInput, ComplaintService
from app.services.notification_service import NotificationService
from app.services.officer_service import OfficerService
from app.services.sla_workflow import SlaWorkflowService
from app.workers.queue import JobService
from tests.support import FakeClock
from tests.support_mem import (
    MemoryUow,
    MemQueueBackend,
    MemStorage,
    RecordingBus,
    Stores,
    uow_factory,
)

CIT = AuthContext("cit-1", Role.CITIZEN)
CIT2 = AuthContext("cit-2", Role.CITIZEN)
OFF_R1 = AuthContext("off-roads-1", Role.OFFICER, "roads")
OFF_R2 = AuthContext("off-roads-2", Role.OFFICER, "roads")
OFF_W1 = AuthContext("off-water-1", Role.OFFICER, "water")
ADMIN = AuthContext("admin-1", Role.ADMIN, None, True)
ADMIN_ROADS = AuthContext("admin-2", Role.ADMIN, "roads", True)
SUPER = AuthContext("super-1", Role.SUPER_ADMIN, None, True)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64

POTHOLE = dict(title="Large pothole on MG Road", description="A very large pothole on the main road near the bus stop is causing accidents", lat=12.9716, lng=77.5946, ward="12")
VAGUE = dict(title="Something is wrong here", description="Something strange has been happening around my house since yesterday")


def complaint_input(**kw):
    return ComplaintInput(**{**POTHOLE, **kw})


class Env:
    def __init__(self, llm=None, vision=False) -> None:
        self.clock = FakeClock()
        self.stores = Stores()
        self.stores.labels = {"off-roads-1": "Officer R1", "off-roads-2": "Officer R2", "off-water-1": "Officer W1", "admin-1": "Admin"}
        self.bus, self.backend, self.storage = RecordingBus(), MemQueueBackend(), MemStorage()
        self.factory = uow_factory(self.stores)
        self.notifications = NotificationService(self.clock)
        self.jobs = JobService(self.factory, self.backend, clock=self.clock)
        self.fx = ComplaintEffects(self.notifications, self.jobs, self.bus, self.clock)
        self.complaints = ComplaintService(self.factory, self.fx, self.storage, ai_enrichment_enabled=llm is not None, vision_enabled=vision)
        self.officer = OfficerService(self.factory, self.fx)
        self.sla = SlaWorkflowService(self.factory, self.fx)

    def uow(self) -> MemoryUow:
        return MemoryUow(self.stores)

    def create(self, ctx=CIT, **kw):
        return self.complaints.create(ctx, complaint_input(**kw)).complaint

    def actions(self):
        return [e.action for e in self.stores.audit]

"""Composition root: builds every service from settings (or from injected test doubles).

Nothing here contains business logic; it only wires the tested services to their infrastructure
and degrades honestly when an optional dependency is not configured (no Redis -> jobs stay
``pending``; no Ollama -> no model; no Bhashini -> voice/translation report NOT_CONFIGURED).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn

from app.core.config import Settings
from app.core.exceptions import DependencyUnavailable
from app.core.rate_limit import FailureThrottle, SlidingWindowLimiter
from app.core.security import PasswordHasher, SecretBox, SessionPolicy
from app.i18n.translator import Translator
from app.integrations.adapters import build_adapters
from app.integrations.health import IntegrationHealthService
from app.legal.analysis import LegalAnalysisService
from app.legal.precedents import PrecedentIndex
from app.providers.geocoding import NominatimProvider
from app.providers.push import ExpoPushSender
from app.providers.speech import BHASHINI_DEFAULT_LANGUAGES, BhashiniConfig, BhashiniProvider
from app.providers.stt import GroqWhisperProvider, SpeechToTextProvider, TranslationProvider, WhisperProvider
from app.providers.vision import OllamaVisionProvider, VisionProvider
from app.rag.bm25 import BM25Index
from app.rag.grounded_generation import GroundedGenerator
from app.rag.hybrid_retrieval import HybridRetriever, RetrievalConfig
from app.rag.index import RagIndex
from app.rag.groq import GroqChatProvider
from app.rag.ollama import (
    EmbeddingProvider,
    OllamaChatProvider,
    OllamaClient,
    OllamaEmbeddingProvider,
)
from app.rag.rag_service import RagService
from app.realtime.websocket_manager import EventBus, LocalEventBus, WebSocketManager
from app.services.admin_service import AdminService
from app.services.anomaly_job import AnomalyDetectionJob
from app.services.assistant_service import AssistantService, build_query_registry
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.classification_service import ClassificationService
from app.services.complaint_common import ComplaintEffects
from app.services.complaint_service import ComplaintService
from app.services.dashboard_service import DashboardService
from app.services.document_service import DocumentIngestor, Storage, document_access_filter
from app.services.duplicate_review import DuplicateReviewApp
from app.services.emergency_service import EmergencyHubService
from app.services.gis_service import GisService
from app.services.government_service import GovernmentSubmissionService
from app.services.intent_router import IntentRouter
from app.services.interop_service import (
    ClassificationCorrectionService,
    ExceptionService,
    ExternalLinksService,
    MasterDataService,
)
from app.services.investigation_service import InvestigationService
from app.services.legal_service import LegalApplicationService
from app.services.mfa_service import MFAService, TotpEngine
from app.services.notification_service import NotificationService
from app.services.officer_service import OfficerService
from app.services.profile_service import DraftService, ProfileService
from app.services.rti_service import RtiRules, RtiService
from app.services.rti_workflow import RtiReminderService
from app.services.sla_workflow import SlaWorkflowService
from app.services.uow import UowFactory
from app.services.voice_service import TranslationService, VoiceService
from app.services.workflow_service import WorkflowService
from app.workers.handlers import GrievanceWorker
from app.workers.queue import JobService, QueueBackend
from app.workers.scheduler import LockProvider, SchedulerService, SchedulerState, TaskSpec

logger = logging.getLogger("civiclens.container")


class UnavailableQueueBackend:
    """Used when Redis is not configured: every call reports the dependency as unavailable, so jobs stay
    ``pending`` in PostgreSQL and the admin monitor shows it. Nothing pretends to be queued."""

    def _down(self) -> NoReturn:
        raise DependencyUnavailable("Redis is not configured.")

    def push(self, *a: Any) -> None: self._down()
    def pop_due(self, *a: Any) -> None: self._down()
    def depth(self) -> int: self._down()
    def heartbeat(self, *a: Any) -> None: self._down()
    def workers(self, *a: Any, **k: Any) -> dict[str, Any]: self._down()
    def ping(self) -> bool: return False


class LocalLock:
    def __init__(self) -> None:
        self._held: set[str] = set()

    def acquire(self, name: str, ttl_seconds: int) -> bool:
        if name in self._held:
            return False
        self._held.add(name)
        return True

    def release(self, name: str) -> None:
        self._held.discard(name)


class LocalSchedulerState:
    def __init__(self) -> None:
        self._d: dict[str, datetime] = {}

    def last_run(self, name: str) -> datetime | None: return self._d.get(name)
    def set_last_run(self, name: str, at: datetime) -> None: self._d[name] = at


@dataclass
class AppContainer:
    settings: Settings
    uow_factory: UowFactory
    hasher: PasswordHasher
    secret_box: SecretBox
    totp: TotpEngine
    storage: Storage
    queue_backend: QueueBackend
    bus: EventBus
    ws: WebSocketManager
    llm: Any | None = None
    embedder: EmbeddingProvider | None = None
    vision: VisionProvider | None = None
    speech: SpeechToTextProvider | None = None
    translator_provider: TranslationProvider | None = None
    ocr: Any | None = None
    ollama: OllamaClient | None = None
    vector_index: Any | None = None
    precedents: PrecedentIndex = field(default_factory=PrecedentIndex)
    scheduler_state: SchedulerState = field(default_factory=LocalSchedulerState)
    lock: LockProvider = field(default_factory=LocalLock)
    health_repo: Any | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731
    session_policy: SessionPolicy = field(default_factory=SessionPolicy)
    ingestor_factory: Callable[[Any], DocumentIngestor] | None = None
    index_sync: Any | None = None
    qr_renderer: Callable[[str], bytes] | None = None
    mailer: Any | None = None
    admin_setup_token: str = ""
    public_base_url: str = ""
    judgment_search: Any | None = None  # JudgmentSearchPort; real full-text case-law semantic search when configured
    geocoding: Any = None  # always constructed in __post_init__ (NominatimProvider by default); injectable for tests

    def __post_init__(self) -> None:
        s = self.settings
        self.login_throttle, self.mfa_throttle = FailureThrottle(), FailureThrottle()
        self.limiters = {"expensive": SlidingWindowLimiter(30, 60), "upload": SlidingWindowLimiter(20, 60)}
        self.translator = Translator.from_files()
        if self.geocoding is None:
            self.geocoding = NominatimProvider()
        from app.i18n.ui_text import UiText

        self.ui_text = UiText.load()
        self.notifications = NotificationService(self.clock, self.mailer)
        self.jobs = JobService(self.uow_factory, self.queue_backend, clock=self.clock)
        self.effects = ComplaintEffects(self.notifications, self.jobs, self.bus, self.clock)
        self.complaints = ComplaintService(self.uow_factory, self.effects, self.storage, ai_enrichment_enabled=self.llm is not None, vision_enabled=self.vision is not None, max_upload_bytes=s.max_upload_bytes)
        self.workflow = WorkflowService(self.uow_factory, self.effects)
        self.effects.workflow = self.workflow
        self.officer = OfficerService(self.uow_factory, self.effects)
        self.duplicate_reviews = DuplicateReviewApp(self.uow_factory, self.effects)
        self.sla = SlaWorkflowService(self.uow_factory, self.effects)
        self.profiles = ProfileService(self.uow_factory, self.clock)
        self.master_data = MasterDataService(self.uow_factory, s.app_secret_key, self.clock)
        self.exceptions = ExceptionService(self.uow_factory, self.clock)
        self.external_links = ExternalLinksService(self.uow_factory, self.clock)
        self.classification_corrections = ClassificationCorrectionService(self.uow_factory, self.clock)
        self.drafts = DraftService(self.uow_factory, self.complaints, self.clock)
        self.rti_rules = RtiRules(s.rti_response_days, s.rti_life_liberty_hours)
        self.gis = GisService(self.uow_factory, self.clock)
        self.emergency = EmergencyHubService(self.translator, self.uow_factory)
        self.voice = VoiceService(self.uow_factory, self.speech, self.clock)
        self.translation = TranslationService(self.translator_provider)
        self.adapters = build_adapters(dict(_env_for_adapters(s)), audit=self._adapter_audit)
        self.government = GovernmentSubmissionService(self.uow_factory, self.effects, self.adapters)
        self.push_sender = ExpoPushSender() if s.expo_push_enabled else None
        self.health = IntegrationHealthService(self.health_repo, self._on_integration_change) if self.health_repo is not None else None
        self.legal_analyzer = LegalAnalysisService(self.precedents, self.llm, self.judgment_search)
        self.legal = LegalApplicationService(self.uow_factory, self.legal_analyzer, self.clock)
        self.rag_index = RagIndex(BM25Index(s.bm25_k1, s.bm25_b), self.vector_index if hasattr(self.vector_index, "add") else None)  # pgvector is queried, not mirrored in memory
        retr = HybridRetriever(self.rag_index.chunks, self.rag_index.bm25, self.vector_index, self.embedder, config=RetrievalConfig(rrf_k=s.rrf_k, rerank_top_k=s.rerank_top_k, final_top_k=s.rag_top_k, min_relevance=s.rag_min_relevance))
        self.rag = RagService(retr, GroundedGenerator(self.llm), build_query_registry(self.uow_factory), access_filter=document_access_filter)
        self.assistant = AssistantService(self.uow_factory, self.rag, self.clock)
        self.dashboards = DashboardService(self.uow_factory, self.clock, self.system_status)
        self.investigations = InvestigationService(self.uow_factory, self.clock, self._rag_lookup, self._legal_lookup)
        self.admin = AdminService(self.uow_factory, self.auth_for, self.clock)
        self.anomaly_job = AnomalyDetectionJob(self.uow_factory)
        self.rti_reminders = RtiReminderService(self.uow_factory, self.notifications, self.rti_rules, self.bus)
        # One instance, two uses: the worker still gets None when no model is configured (its AI
        # enrichment stays off), while the UI always has the rules-only classifier available - it
        # reports ai_status="not_configured" rather than pretending a model answered.
        self.classifier = ClassificationService(self.llm)
        self.intent_router = IntentRouter()
        ai = self.classifier if self.llm is not None else None
        self.worker = GrievanceWorker(self.uow_factory, self.complaints, ai, self.vision, self.storage, self.effects, self.notifications, self.ingestor_factory, self.profiles.has_consent, self.translation, self.push_sender, self.government)
        self.jobs.handlers.update(self.worker.handlers())
        self.scheduler = SchedulerService(self._tasks(), self.scheduler_state, self.lock, self.clock)

    # ------------------------------------------------------------- per-request factories
    def mfa_for(self, uow: Any) -> MFAService:
        return MFAService(uow.mfa, self.secret_box, self.totp, AuditService(uow.audit, self.clock), throttle=self.mfa_throttle, clock=lambda: self.clock().timestamp())

    def auth_for(self, uow: Any) -> AuthService:
        return AuthService(uow.users, uow.sessions, uow.resets, self.hasher, self.mfa_for(uow), AuditService(uow.audit, self.clock), throttle=self.login_throttle, policy=self.session_policy, clock=self.clock)

    def rti_for(self, uow: Any) -> RtiService:
        return RtiService(uow.rti, self.rti_rules, self.clock)

    # ------------------------------------------------------------- integration glue
    def _adapter_audit(self, action: str, meta: dict[str, Any]) -> None:
        with self.uow_factory() as uow:
            AuditService(uow.audit, self.clock).record(action, actor_id=None, resource_type="integration", resource_id=meta.get("platform"), metadata=meta)
            uow.commit()

    def _on_integration_change(self, platform: str, old: str | None, new: str) -> None:
        from app.realtime.events import INTEGRATION_STATUS_CHANGED, DomainEvent

        self.bus.publish(DomainEvent(INTEGRATION_STATUS_CHANGED, {"platform": platform, "from": old, "to": new}))

    def _rag_lookup(self, ctx: Any, text: str) -> dict[str, Any]:
        r = self.rag.ask(text, ctx)
        return {"status": r.status, "answer": r.answer, "citations": r.citations, "warnings": r.warnings}

    def _legal_lookup(self, text: str) -> dict[str, Any]:
        a = self.legal_analyzer.analyze(text, top_k=5)
        return {"status": a.status, "precedents": a.precedents, "concepts": a.concepts, "coverage": a.bias_and_coverage, "full_text_excerpts": a.full_text_excerpts}

    def system_status(self) -> dict[str, Any]:
        out: dict[str, Any] = {"queue": self.jobs.stats(), "websocket_connections": self.ws.connection_count(), "adapters": {p: a.state.value for p, a in self.adapters.items()}}
        out["storage"] = self.storage.health() if hasattr(self.storage, "health") else {"provider": type(self.storage).__name__, "state": "UNKNOWN"}
        out["ollama"] = "not_configured" if self.ollama is None else "configured"
        out["rag"] = {"chunks": len(self.rag_index), "semantic_search": self.vector_index is not None and self.embedder is not None, "model": self.llm is not None}
        from app.core.error_tracking import error_tracking_status

        out["error_tracking"] = error_tracking_status()
        return out

    # ------------------------------------------------------------- scheduled work
    def _tasks(self) -> list[TaskSpec]:
        return [
            TaskSpec("sla.scan", timedelta(minutes=5), self.sla.scan),
            TaskSpec("rti.deadlines", timedelta(hours=1), self.rti_reminders.run),
            TaskSpec("anomaly.detect", timedelta(hours=1), self.anomaly_job.run),
            TaskSpec("queue.requeue_orphans", timedelta(minutes=1), lambda now: {"requeued": self.jobs.requeue_orphans()}),
            TaskSpec("integrations.health", timedelta(minutes=10), lambda now: {"checked": len(self.health.check_all(self.adapters)) if self.health else 0}),
            TaskSpec("rag.index_refresh", timedelta(seconds=30), lambda now: self.index_sync.refresh() if self.index_sync else {}),
            TaskSpec("analytics.refresh", timedelta(hours=1), self._analytics_snapshot),
            TaskSpec("workflow.sweep", timedelta(minutes=15), self.workflow.sweep),
        ]

    def _analytics_snapshot(self, now: datetime) -> dict[str, Any]:
        from app.services.dashboard_service import summarize
        from app.services.sla_service import SlaCalculator

        with self.uow_factory() as uow:
            summary = summarize(uow.complaints.rows(), now, SlaCalculator(list(uow.config.sla_policies())))
            uow.analytics.add_snapshot("all", now, {k: v for k, v in summary.items() if k != "trend_daily"})
            uow.commit()
        return {"snapshot": "all", "total": summary["total"]}


def _env_for_adapters(s: Settings) -> dict[str, str]:
    import os

    env = dict(os.environ)
    env["GOV_ADAPTER_TIMEOUT_SECONDS"], env["GOV_ADAPTER_MAX_RETRIES"] = str(s.gov_adapter_timeout_seconds), str(s.gov_adapter_max_retries)
    return env


def build_container(settings: Settings) -> AppContainer:
    """Production wiring. Every optional dependency is attached only if it is configured."""
    from app.core.security import Argon2Hasher
    from app.db.session import make_engine, make_session_factory
    from app.db.uow import SqlUnitOfWork
    from app.services.mfa_service import PyOtpEngine, render_qr_png
    from app.storage.providers import build_storage

    engine = make_engine(settings)
    sf = make_session_factory(engine)
    ws = WebSocketManager()
    bus: EventBus = LocalEventBus(ws)
    backend: QueueBackend = UnavailableQueueBackend()
    lock: LockProvider = LocalLock()
    state: SchedulerState = LocalSchedulerState()
    redis_client = None
    if settings.redis_url:
        import redis

        from app.workers.redis_backend import (
            RedisEventBus,
            RedisLock,
            RedisQueueBackend,
            RedisSchedulerState,
        )

        redis_client = redis.Redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3)
        backend, lock, state = RedisQueueBackend(redis_client), RedisLock(redis_client), RedisSchedulerState(redis_client)
        bus = RedisEventBus(redis_client)
    # A cold model load alone measured ~52s for llama3.1:8b on CPU-only inference; 90s left too little
    # room for the load plus even a short generation, so warm-up and first-request calls were degrading
    # to "unavailable" before the model ever finished loading.
    ollama = OllamaClient(settings.ollama_base_url, timeout=180) if settings.ollama_base_url and (settings.ollama_model or settings.ollama_embedding_model or settings.ollama_vision_model) else None
    # Groq (cloud, LPU-hosted) takes over chat/generation when configured - dramatically faster than
    # this machine's CPU-only Ollama inference. Embeddings/OCR vision stay on Ollama either way.
    llm = GroqChatProvider(settings.groq_api_key, settings.groq_model) if settings.groq_api_key and settings.groq_model else (OllamaChatProvider(ollama, settings.ollama_model) if ollama and settings.ollama_model else None)
    embedder = OllamaEmbeddingProvider(ollama, settings.ollama_embedding_model, settings.embedding_dimensions) if ollama and settings.ollama_embedding_model else None
    vision = OllamaVisionProvider(ollama, settings.ollama_vision_model) if ollama and settings.ollama_vision_model else None
    asr_langs = frozenset(x.strip() for x in _env("BHASHINI_ASR_LANGUAGES").split(",") if x.strip()) or BHASHINI_DEFAULT_LANGUAGES
    bhashini = BhashiniProvider(BhashiniConfig(settings.bhashini_user_id, settings.bhashini_api_key, _env("BHASHINI_PIPELINE_ID"), asr_languages=asr_langs)) if settings.bhashini_enabled and _env("BHASHINI_PIPELINE_ID") else None
    speech: SpeechToTextProvider | None = None
    if settings.stt_provider == "groq_whisper" and settings.groq_api_key:
        speech = GroqWhisperProvider(settings.groq_api_key, settings.groq_whisper_model)  # cloud-hosted - doesn't compete with this machine's CPU/RAM
    elif settings.stt_provider == "whisper" and settings.whisper_model:
        speech = WhisperProvider(settings.whisper_model)  # NotConfigured if faster-whisper is not installed: fail loudly at start
    elif settings.stt_provider in ("bhashini", "auto") and bhashini:
        speech = bhashini
    translator_provider = bhashini
    from app.db.repositories.content import PgVectorSearcher, SqlChunkStore
    from app.db.repositories.ops import SqlIntegrationHealthRepository, SqlSchedulerState

    def uow() -> SqlUnitOfWork:
        return SqlUnitOfWork(sf)

    vector = PgVectorSearcher(sf, None) if embedder is not None else None
    from app.legal.judgment_search import SqlJudgmentSearch

    judgment_search = SqlJudgmentSearch(sf, embedder) if embedder is not None else None
    storage = build_storage(settings, _env("GOOGLE_DRIVE_FOLDER_ID"))
    mailer = None
    if _env("SMTP_HOST") and _env("SMTP_SENDER"):
        from app.services.notification_service import SmtpEmailSender

        mailer = SmtpEmailSender(_env("SMTP_HOST"), int(_env("SMTP_PORT") or 587), _env("SMTP_SENDER"), _env("SMTP_USERNAME"), _env("SMTP_PASSWORD"))
    container = AppContainer(settings, uow, Argon2Hasher(), SecretBox(settings.app_secret_key or "dev-only-secret-key-not-for-prod"), PyOtpEngine(), storage, backend, bus, ws,  # type: ignore[arg-type]
                             llm=llm, embedder=embedder, vision=vision, speech=speech, translator_provider=translator_provider, ollama=ollama, vector_index=vector,
                             scheduler_state=SqlSchedulerState(sf) if redis_client is None else state, lock=lock, health_repo=SqlIntegrationHealthRepository(sf), qr_renderer=render_qr_png, mailer=mailer,
                             admin_setup_token=_env("ADMIN_SETUP_TOKEN"), public_base_url=_env("PUBLIC_BASE_URL"), judgment_search=judgment_search)  # fmt: skip
    if redis_client is not None:
        from app.core.redis_limits import (
            RedisFailureThrottle,
            RedisFixedWindowLimiter,
            ResilientLimiter,
            ResilientThrottle,
        )

        container.limiters = {n: ResilientLimiter(RedisFixedWindowLimiter(redis_client, n, lim, 60), container.limiters[n]) for n, lim in (("expensive", 30), ("upload", 20))}  # type: ignore[misc]
        container.login_throttle = ResilientThrottle(RedisFailureThrottle(redis_client, "login"), container.login_throttle)  # type: ignore[assignment]
        container.mfa_throttle = ResilientThrottle(RedisFailureThrottle(redis_client, "mfa"), container.mfa_throttle)  # type: ignore[assignment]
    _attach_documents(container, sf, embedder, settings, SqlChunkStore)
    return container


def _env(name: str) -> str:
    import os

    return os.environ.get(name, "").strip()


def _attach_documents(c: AppContainer, sf: Any, embedder: Any, settings: Settings, chunk_store_cls: Any) -> None:
    """Document ingestion writes chunks/embeddings to PostgreSQL and the local BM25 index; other
    processes pick changes up through ``IndexSynchronizer`` (scheduled ``rag.index_refresh``)."""
    from app.rag.index_sync import IndexSynchronizer

    class _PersistingIndex(RagIndex):
        def __init__(self, inner: RagIndex, store: Any) -> None:  # composition: same public API as RagIndex
            self._inner, self._store = inner, store
            self.chunks, self.bm25, self.vectors = inner.chunks, inner.bm25, inner.vectors

        def add_document(self, chunks: Any, vectors: Any) -> None:
            if chunks:
                self._store.replace_document(chunks[0].document_id, list(chunks), [list(v) for v in vectors] if vectors else None)
            self._inner.add_document(chunks, vectors)

        def remove_document(self, document_id: str) -> int:
            return self._inner.remove_document(document_id)

        def __len__(self) -> int:
            return len(self._inner)

    from app.providers.ocr import build_ocr

    c.ocr = build_ocr(
    settings.ocr_provider,
    languages=settings.ocr_languages,
    ollama_client=c.ollama,
    vision_model=settings.ollama_vision_model,
    tesseract_cmd=settings.tesseract_cmd,
    tessdata_dir=settings.tessdata_dir,
)
    def factory(uow: Any) -> DocumentIngestor:
        return DocumentIngestor(uow.documents, c.storage, _PersistingIndex(c.rag_index, chunk_store_cls(uow.session)), embedder=embedder, ocr=c.ocr)

    c.ingestor_factory = factory
    c.worker._ingestor_factory = factory

    class _Source:
        def ready_documents(self) -> dict[str, datetime]:
            with sf() as s:
                return chunk_store_cls(s).ready_documents()

        def load_chunks(self, document_id: str) -> Any:
            with sf() as s:
                return chunk_store_cls(s).load_chunks(document_id)

    c.index_sync = IndexSynchronizer(_Source(), c.rag_index)

"""Small routers: notifications, profiles, consent, gis, dashboards, analytics, integrations, monitoring."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from app.api.serialize import to_jsonable
from app.container import AppContainer
from app.core.authorization import AuthContext, Permission
from app.core.dependencies import get_container, guard
from app.core.transactions import run_in_uow
from app.core.exceptions import NotConfigured
from app.schemas.api import ConsentBody, DeviceBody, PrefsBody, ProfileBody

notifications = APIRouter(prefix="/notifications", tags=["notifications"])
profiles = APIRouter(prefix="/profiles", tags=["profiles"])
consent = APIRouter(prefix="/consent", tags=["consent"])
gis = APIRouter(prefix="/gis", tags=["gis"])
dashboards = APIRouter(prefix="/dashboards", tags=["dashboards"])
analytics = APIRouter(prefix="/analytics", tags=["analytics"])
integrations = APIRouter(prefix="/integrations", tags=["integrations"])
monitoring = APIRouter(prefix="/monitoring", tags=["monitoring"])
emergency = APIRouter(prefix="/emergency", tags=["emergency"])
directory = APIRouter(prefix="/reference", tags=["reference"])

NOTE = Depends(guard(Permission.NOTIFICATION_READ_OWN))
PROF = Depends(guard(Permission.PROFILE_MANAGE))


# ---- notifications
@notifications.get("")
def list_notifications(unread_only: bool = False, limit: int = 50, ctx: AuthContext = NOTE, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    items = run_in_uow(c, lambda uow: (c.notifications.list_for(ctx, uow.notifications, unread_only=unread_only, limit=min(limit, 100)), uow.notifications.unread_count(ctx.user_id)))
    return {"items": to_jsonable(items[0]), "unread": items[1]}


@notifications.post("/{notification_id}/read")
def mark_read(notification_id: str, ctx: AuthContext = NOTE, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(run_in_uow(c, lambda uow: c.notifications.mark_read(ctx, uow.notifications, notification_id)))  # type: ignore[no-any-return]


@notifications.post("/read-all")
def read_all(ctx: AuthContext = NOTE, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"marked": run_in_uow(c, lambda uow: c.notifications.mark_all_read(ctx, uow.notifications))}


@notifications.get("/preferences")
def get_prefs(ctx: AuthContext = NOTE, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(run_in_uow(c, lambda uow: c.notifications.preferences(ctx, uow.notifications)))  # type: ignore[no-any-return]


@notifications.put("/preferences")
def put_prefs(body: PrefsBody, ctx: AuthContext = NOTE, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(run_in_uow(c, lambda uow: c.notifications.save_preferences(ctx, uow.notifications, in_app=body.in_app, email=body.email, muted_kinds=body.muted_kinds)))  # type: ignore[no-any-return]


@notifications.post("/devices", status_code=204)
def register_device(body: DeviceBody, ctx: AuthContext = NOTE, c: AppContainer = Depends(get_container)) -> None:
    """Mobile: register this phone's Expo push token for the signed-in user."""
    run_in_uow(c, lambda uow: c.notifications.register_device(ctx, uow, body.token, body.platform))


@notifications.delete("/devices/{token}", status_code=204)
def unregister_device(token: str, ctx: AuthContext = NOTE, c: AppContainer = Depends(get_container)) -> None:
    run_in_uow(c, lambda uow: uow.push.delete(token, ctx.user_id))


# ---- emergency (public: people must reach it without an account)
@emergency.get("/helplines")
def helplines(lang: str | None = None, city: str | None = None, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return c.emergency.list(lang, city)


# ---- profiles & consent
@profiles.get("/me")
def get_profile(ctx: AuthContext = PROF, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.profiles.get(ctx))  # type: ignore[no-any-return]


@profiles.put("/me")
def put_profile(body: ProfileBody, ctx: AuthContext = PROF, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.profiles.update(ctx, **body.model_dump()))  # type: ignore[no-any-return]


@consent.get("")
def get_consents(ctx: AuthContext = PROF, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.profiles.consents(ctx))  # type: ignore[no-any-return]


@consent.put("/{purpose}")
def put_consent(purpose: str, body: ConsentBody, ctx: AuthContext = PROF, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.profiles.set_consent(ctx, purpose, body.granted))  # type: ignore[no-any-return]


# ---- reference / directory (read-only, non-sensitive: department, city and ward names/codes)
@directory.get("/directory")
def directory_listing(ctx: AuthContext = Depends(guard(Permission.GIS_VIEW)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    def op(uow):  # type: ignore[no-untyped-def]
        return {
            "departments": [{"code": d.code, "name": d.name} for d in uow.config.departments() if d.active],
            "cities": [{"code": x.code, "name": x.name, "state": x.state, "lat": x.lat, "lng": x.lng} for x in uow.config.cities()],
            "wards": [{"code": x.code, "name": x.name, "city_code": x.city_code} for x in uow.config.wards()],
            "services": [{"code": x.code, "name": x.name, "department_code": x.department_code} for x in uow.config.services()],
            "offices": [{"id": x.id, "name": x.name, "department_code": x.department_code, "lat": x.lat, "lng": x.lng, "address": x.address, "city_code": x.city_code} for x in uow.config.offices()],
        }

    return run_in_uow(c, op)


# ---- gis
@gis.get("/radar")
def radar(category: str | None = None, ward: str | None = None, min_severity: str | None = None, days: int = 90, ctx: AuthContext = Depends(guard(Permission.GIS_VIEW)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.gis.radar(ctx, category=category, ward=ward, min_severity=min_severity, days=days))  # type: ignore[no-any-return]


# ---- dashboards / analytics
@dashboards.get("/citizen")
def citizen_dashboard(ctx: AuthContext = Depends(guard(Permission.COMPLAINT_READ_OWN)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.dashboards.citizen(ctx))  # type: ignore[no-any-return]


@dashboards.get("/department")
def department_dashboard(department_code: str | None = None, ctx: AuthContext = Depends(guard(Permission.DASHBOARD_DEPARTMENT)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.dashboards.department(ctx, department_code=department_code))  # type: ignore[no-any-return]


@dashboards.get("/admin")
def admin_dashboard(ctx: AuthContext = Depends(guard(Permission.ADMIN_DASHBOARD)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.dashboards.admin(ctx))  # type: ignore[no-any-return]


@analytics.get("/summary")
def summary(ctx: AuthContext = Depends(guard(Permission.ANALYTICS_VIEW)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.dashboards.admin(ctx))  # type: ignore[no-any-return]


@analytics.get("/forecast")
def forecast(horizon: int = 7, ctx: AuthContext = Depends(guard(Permission.ANALYTICS_VIEW)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    from app.services.analytics_service import InsufficientData, forecast_linear

    d = c.dashboards.admin(ctx)
    series = [x["count"] for x in d["trend_daily"]]
    f = forecast_linear(series, max(1, min(horizon, 30)))
    return {"insufficient_data": True, "needed": f.needed, "have": f.have} if isinstance(f, InsufficientData) else to_jsonable(f)  # type: ignore[no-any-return]


@analytics.get("/history")
def analytics_history(days: int = 30, ctx: AuthContext = Depends(guard(Permission.ANALYTICS_VIEW)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.dashboards.history(ctx, days=days))  # type: ignore[no-any-return]


@analytics.post("/anomalies/run")
def run_anomalies(ctx: AuthContext = Depends(guard(Permission.ADMIN_MONITORING)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return c.anomaly_job.run(c.clock())


# ---- integrations
@integrations.get("")
def integration_status(ctx: AuthContext = Depends(guard(Permission.ADMIN_INTEGRATIONS)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": [to_jsonable(a.health_snapshot("not probed since start" if a.is_configured() else "missing: " + ", ".join(a.config.missing()))) | {"display_name": a.display_name, "configured": a.is_configured()} for a in c.adapters.values()]}


@integrations.post("/check")
def integration_check(ctx: AuthContext = Depends(guard(Permission.ADMIN_INTEGRATIONS)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    if c.health is None:
        raise NotConfigured("Integration health persistence is not configured.")
    return {"items": to_jsonable(c.health.check_all(c.adapters))}


# ---- monitoring
_STARTED = time.time()


@monitoring.get("/health")
def health() -> dict:  # type: ignore[type-arg]
    """Liveness: the process is up (no dependency checks; see /ready)."""
    return {"status": "ok", "uptime_seconds": int(time.time() - _STARTED)}


@monitoring.get("/ready")
def ready(c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    """Readiness: actually probes each configured dependency."""
    checks: dict[str, dict] = {}  # type: ignore[type-arg]
    try:
        run_in_uow(c, lambda uow: uow.config.departments())
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        checks["database"] = {"status": "down", "detail": type(exc).__name__}
    checks["redis"] = {"status": "ok" if c.queue_backend.ping() else "down_or_not_configured"}
    if c.ollama is not None:
        from app.rag.ollama import probe

        ok, detail, _ = probe(c.ollama, [c.settings.ollama_model, c.settings.ollama_embedding_model])
        checks["ollama"] = {"status": "ok" if ok else "down", "detail": detail}
    else:
        checks["ollama"] = {"status": "not_configured"}
    try:
        from app.db.schema_check import check as migrations_check

        checks["migrations"] = run_in_uow(c, lambda uow: migrations_check(uow.session))  # type: ignore[attr-defined]
    except Exception as exc:
        checks["migrations"] = {"status": "unknown", "detail": type(exc).__name__}
    ok_all = checks["database"]["status"] == "ok" and checks["migrations"].get("status") in ("ok", "unknown")
    return {"status": "ready" if ok_all else "not_ready", "checks": checks}


@monitoring.get("/queue")
def queue_status(ctx: AuthContext = Depends(guard(Permission.ADMIN_MONITORING)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return c.jobs.stats()


@monitoring.get("/notifications")
def notification_status(ctx: AuthContext = Depends(guard(Permission.ADMIN_MONITORING)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    """Delivery state counts per channel: queued / sending / delivered / failed / not_configured."""
    return {"by_channel": run_in_uow(c, lambda uow: uow.notifications.status_counts()), "email_configured": c.mailer is not None, "push_configured": c.push_sender is not None}


@monitoring.get("/jobs")
def jobs(status: str | None = None, limit: int = 50, ctx: AuthContext = Depends(guard(Permission.ADMIN_MONITORING)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": to_jsonable(run_in_uow(c, lambda uow: uow.jobs.list_recent(min(limit, 200), status))), "stats": c.jobs.stats()}


@monitoring.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, ctx: AuthContext = Depends(guard(Permission.ADMIN_MONITORING)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.jobs.retry_dead(job_id))  # type: ignore[no-any-return]


@monitoring.get("/government")
def government_status(ctx: AuthContext = Depends(guard(Permission.ADMIN_INTEGRATIONS)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"submissions_by_state": run_in_uow(c, lambda uow: uow.government.counts_by_state()), "adapters": {p: a.state.value for p, a in c.adapters.items()}}


@monitoring.get("/system")
def system(ctx: AuthContext = Depends(guard(Permission.ADMIN_MONITORING)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.system_status())  # type: ignore[no-any-return]

"""/api/v1/auth: registration, login (+2FA), sessions, password reset, MFA enrolment, admin bootstrap."""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, Request, Response

from app.container import AppContainer
from app.core.authorization import AuthContext, Role
from app.core.dependencies import (
    SESSION_COOKIE,
    client_ip,
    csrf_secret,
    get_container,
    get_ctx,
    session_token,
)
from app.core.exceptions import AuthenticationFailed, NotFound
from app.core.security import csrf_token_for, hash_token
from app.core.transactions import run_in_uow
from app.schemas.api import (
    BootstrapBody,
    ChangePasswordBody,
    DisableMfaBody,
    ForgotBody,
    LoginBody,
    OtpBody,
    RegisterBody,
    ResetBody,
)

router = APIRouter(prefix="/auth", tags=["auth"])
PRIVILEGED = (Role.ADMIN, Role.SUPER_ADMIN, Role.INTEGRATION_ADMIN, Role.AUDITOR)


def _set_cookie(resp: Response, token: str, c: AppContainer) -> None:
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", secure=c.settings.is_production, max_age=int(c.session_policy.absolute.total_seconds()), path="/")


def _session_payload(c: AppContainer, token: str, ctx: AuthContext, uow_info: dict) -> dict:
    return {"user": {"id": ctx.user_id, "role": ctx.role.value, "department_code": ctx.department_id, **uow_info}, "mfa_verified": ctx.mfa_verified, "csrf_token": csrf_token_for(hash_token(token), csrf_secret(c))}


def _user_info(c: AppContainer, uow: object, user_id: str) -> dict:
    u = uow.users.get_by_id(user_id)  # type: ignore[attr-defined]
    prof = uow.profiles.get(user_id)  # type: ignore[attr-defined]
    return {"email": u.email if u else None, "full_name": u.full_name if u else None, "mfa_enabled": c.mfa_for(uow).is_enabled(user_id), "language": prof.language if prof else "en", "onboarding_complete": bool(prof and prof.onboarding_complete)}


@router.post("/register", status_code=201)
def register(body: RegisterBody, c: AppContainer = Depends(get_container)) -> dict:
    """Creates a CITIZEN only. The schema forbids extra fields, so a ``role`` in the body is a 422."""
    user = run_in_uow(c, lambda uow: c.auth_for(uow).register(body.email, body.password, body.full_name))
    return {"id": user.id, "email": user.email, "role": user.role.value}


def _login(body: LoginBody, request: Request, c: AppContainer, *, privileged_only: bool, client: str = "web"):
    def op(uow):
        auth = c.auth_for(uow)
        res = auth.login(body.email, body.password, otp=body.otp, client_key=client_ip(request), client=client)
        if privileged_only and res.context.role not in PRIVILEGED:
            auth.logout(res.session_token)  # a citizen/officer credential is not an admin login
            uow.commit()
            raise AuthenticationFailed("Invalid e-mail, password or verification code.")
        return res, _user_info(c, uow, res.context.user_id)

    return run_in_uow(c, op, commit_on_error=True)  # failed-attempt audit rows are kept


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, c: AppContainer = Depends(get_container)) -> dict:
    res, info = _login(body, request, c, privileged_only=False)
    _set_cookie(response, res.session_token, c)  # the raw token only ever travels in the HttpOnly cookie
    return _session_payload(c, res.session_token, res.context, info)


@router.post("/mobile/login")
def mobile_login(body: LoginBody, request: Request, c: AppContainer = Depends(get_container)) -> dict:
    """Mobile sign-in: the session token is returned in the body (no cookie) for the OS secure store, then sent as
    ``Authorization: Bearer <token>``. Same server-side session model: revocable, expiring (14 d idle / 60 d absolute), 2FA-aware."""
    res, info = _login(body, request, c, privileged_only=False, client="mobile")
    return {**_session_payload(c, res.session_token, res.context, info), "session_token": res.session_token, "token_type": "Bearer"}


@router.post("/admin/login")
def admin_login(body: LoginBody, request: Request, response: Response, c: AppContainer = Depends(get_container)) -> dict:
    res, info = _login(body, request, c, privileged_only=True)
    _set_cookie(response, res.session_token, c)
    return _session_payload(c, res.session_token, res.context, info)


@router.get("/me")
def me(request: Request, ctx: AuthContext = Depends(get_ctx), c: AppContainer = Depends(get_container)) -> dict:
    token = session_token(request)[0] or ""
    info = run_in_uow(c, lambda uow: _user_info(c, uow, ctx.user_id))
    return _session_payload(c, token, ctx, info)


@router.post("/logout")
def logout(request: Request, response: Response, ctx: AuthContext = Depends(get_ctx), c: AppContainer = Depends(get_container)) -> dict:
    token = session_token(request)[0]
    run_in_uow(c, lambda uow: c.auth_for(uow).logout(token))
    c.ws.drop_session_threadsafe(hash_token(token or ""))  # close this session's live sockets immediately
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/password/forgot", status_code=202)
def forgot(body: ForgotBody, c: AppContainer = Depends(get_container)) -> dict:
    """Always answers the same way (no account enumeration). The reset link is delivered by e-mail only;
    without SMTP no link can be delivered and the attempt is audited as such."""

    def op(uow):
        token = c.auth_for(uow).request_password_reset(body.email)
        if token is None:
            return
        from app.services.audit_service import AuditService

        if c.mailer is None:
            AuditService(uow.audit, c.clock).record("auth.password_reset_delivery_unavailable", actor_id=None)
            return
        link = f"{c.public_base_url.rstrip('/')}/reset-password?token={token}"
        c.mailer.send(body.email.strip().lower(), "CivicLens password reset", f"Use this link within 1 hour to reset your password:\n{link}\nIf you did not ask for this, ignore this message.")

    run_in_uow(c, op)
    # `email_delivery` describes the SERVER (not the account), so it is truthful without revealing whether an account exists.
    return {"ok": True, "message": "If an account exists for that e-mail, a reset link has been sent.", "email_delivery": "configured" if c.mailer is not None else "not_configured"}


@router.post("/password/reset")
def reset(body: ResetBody, c: AppContainer = Depends(get_container)) -> dict:
    run_in_uow(c, lambda uow: c.auth_for(uow).reset_password(body.token, body.new_password), commit_on_error=True)
    return {"ok": True}


@router.post("/password/change")
def change_password(body: ChangePasswordBody, ctx: AuthContext = Depends(get_ctx), c: AppContainer = Depends(get_container)) -> dict:
    run_in_uow(c, lambda uow: c.auth_for(uow).change_password(ctx, body.current_password, body.new_password), commit_on_error=True)
    return {"ok": True, "message": "Password changed. Please sign in again."}


@router.post("/mfa/enroll")
def mfa_enroll(ctx: AuthContext = Depends(get_ctx), c: AppContainer = Depends(get_container)) -> dict:
    def op(uow):
        u = uow.users.get_by_id(ctx.user_id)
        return c.mfa_for(uow).begin_enrollment(ctx.user_id, u.email)

    e = run_in_uow(c, op)
    qr = base64.b64encode(c.qr_renderer(e.provisioning_uri)).decode() if c.qr_renderer else None
    return {"provisioning_uri": e.provisioning_uri, "manual_entry_secret": e.manual_entry_secret, "qr_png_base64": qr, "qr_available": qr is not None}


@router.post("/mfa/confirm")
def mfa_confirm(body: OtpBody, request: Request, ctx: AuthContext = Depends(get_ctx), c: AppContainer = Depends(get_container)) -> dict:
    token = session_token(request)[0]

    def op(uow):
        codes = c.mfa_for(uow).confirm_enrollment(ctx.user_id, body.otp)
        c.auth_for(uow).mark_session_mfa_verified(token)
        return codes

    return {"backup_codes": run_in_uow(c, op, commit_on_error=True), "note": "Store these backup codes now; they are shown only once."}


@router.post("/mfa/disable")
def mfa_disable(body: DisableMfaBody, ctx: AuthContext = Depends(get_ctx), c: AppContainer = Depends(get_container)) -> dict:
    def op(uow):
        ok = c.auth_for(uow).verify_password(ctx.user_id, body.password)
        c.mfa_for(uow).disable(ctx.user_id, body.otp, reauthenticated=ok)

    run_in_uow(c, op, commit_on_error=True)
    return {"ok": True}


@router.post("/admin/bootstrap", status_code=201)
def bootstrap(body: BootstrapBody, c: AppContainer = Depends(get_container)) -> dict:
    """Creates the first super-admin exactly once, guarded by ADMIN_SETUP_TOKEN (out-of-band)."""
    if not c.admin_setup_token:
        raise NotFound("Not found.")
    user = run_in_uow(c, lambda uow: c.auth_for(uow).bootstrap_first_admin(body.email, body.password, body.full_name, provided_token=body.setup_token, expected_token=c.admin_setup_token), commit_on_error=True)
    return {"id": user.id, "role": user.role.value, "next": "Sign in and enrol two-factor authentication."}



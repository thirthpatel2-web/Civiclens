"""/api/v1/federation: the mock Government Identity Provider's OAuth2-style surface.

**DEMO / MOCK IDENTITY PROVIDER** - not connected to any real government identity federation. See
app/interop/federation/idp.py for what's real underneath this (a genuine client_credentials grant,
opaque bearer tokens hashed at rest, expiry, revocation) and docs/INTEROPERABILITY.md's
"Reusable connector abstraction" / federation sections.

These routes are intentionally NOT gated by a CivicLens session (no ``guard(...)``/``get_ctx``) -
an OAuth2 token endpoint authenticates the *client* via its own client_id/client_secret in the
request body, exactly like a real authorization server's /token endpoint does; requiring a citizen
or admin to be logged into CivicLens first would defeat the point of a department's own system
authenticating as itself. tests/api/test_static_audit.py's PUBLIC allowlist names this
deliberately, not as an oversight.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.container import AppContainer
from app.core.dependencies import get_container
from app.core.exceptions import AuthenticationFailed
from app.interop.federation import idp
from app.schemas.api import FederationTokenActionBody, FederationTokenBody

router = APIRouter(prefix="/federation", tags=["federation"])


@router.get("/issuer")
def issuer_metadata() -> dict:
    return {
        "issuer": idp.ISSUER,
        "label": "DEMO / MOCK IDENTITY PROVIDER - not a real government identity federation",
        "grant_types_supported": ["client_credentials"],
        "token_endpoint": "/api/v1/federation/token",
        "introspection_endpoint": "/api/v1/federation/introspect",
        "revocation_endpoint": "/api/v1/federation/revoke",
    }


@router.post("/token")
def token(body: FederationTokenBody, c: AppContainer = Depends(get_container)) -> dict:
    if body.grant_type != "client_credentials":
        raise AuthenticationFailed("Only the client_credentials grant is supported by this mock IdP.")
    scope = body.scope.split() if body.scope else None
    with c.uow_factory() as uow:
        try:
            raw, claims = idp.issue_token(uow.session, client_id=body.client_id, client_secret=body.client_secret, scope=scope)
        except idp.InvalidClient:
            raise AuthenticationFailed("Unknown client, disabled client, or wrong client_secret.") from None
        uow.commit()
    return {
        "access_token": raw, "token_type": "Bearer", "expires_in": int(idp.TOKEN_TTL.total_seconds()),
        "scope": " ".join(claims.scope), "system": claims.system,
    }


@router.post("/introspect")
def introspect(body: FederationTokenActionBody, c: AppContainer = Depends(get_container)) -> dict:
    with c.uow_factory() as uow:
        return idp.introspect(uow.session, body.token)


@router.post("/revoke")
def revoke(body: FederationTokenActionBody, c: AppContainer = Depends(get_container)) -> dict:
    with c.uow_factory() as uow:
        revoked = idp.revoke_token(uow.session, body.token)
        uow.commit()
    return {"revoked": revoked}

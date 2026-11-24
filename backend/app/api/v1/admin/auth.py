"""Admin login / refresh / logout.

The refresh token never reaches JavaScript: it lives in an ``HttpOnly`` cookie scoped
to this router's path, ``SameSite=Strict`` and ``Secure`` in production. The admin
panel keeps only the short-lived access token in memory.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import AdminDep, RateLimiterDep, SessionDep, SettingsDep, client_ip
from app.core.config import Settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError, error_body
from app.schemas.admin import AdminMeOut, LoginIn, TokenOut
from app.services.auth import AuthService, TokenPair

REFRESH_COOKIE = "os_refresh"
AUTH_PATH = "/api/v1/admin/auth"

router = APIRouter(prefix="/admin/auth", tags=["admin: auth"])

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def _set_refresh_cookie(response: Response, pair: TokenPair, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        pair.refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        path=AUTH_PATH,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=AUTH_PATH,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
    )


def check_origin(request: Request, settings: Settings) -> None:
    """Defence in depth for the cookie-authenticated endpoints (refresh, logout).

    SameSite=Strict already stops cross-site requests; additionally, when the browser
    states an Origin, it must be our own host or an allowed CORS origin.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return
    own = f"{request.url.scheme}://{request.headers.get('host', '')}"
    if origin != own and origin not in settings.cors_origins:
        raise PermissionDeniedError("So‘rov manbasi ruxsat etilmagan.", code="bad_origin")


def _token_out(pair: TokenPair) -> TokenOut:
    return TokenOut(
        access_token=pair.access_token,
        expires_at=pair.access_expires_at,
        admin=AdminMeOut.build(pair.admin),
    )


@router.post("/login", response_model=TokenOut)
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    limiter: RateLimiterDep,
) -> TokenOut:
    ip = client_ip(request) or "unknown"
    limit = settings.rate_limit_login_per_minute
    await limiter.hit(f"login:ip:{ip}", limit=limit, window_seconds=60)
    await limiter.hit(f"login:email:{body.email.lower()}", limit=limit, window_seconds=60)
    pair = await AuthService(session, settings).login(
        body.email, body.password, user_agent=request.headers.get("user-agent"), ip=ip
    )
    await limiter.reset(f"login:email:{body.email.lower()}")
    _set_refresh_cookie(response, pair, settings)
    return _token_out(pair)


@router.post("/refresh", response_model=TokenOut, responses={401: {}})
async def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    refresh_token: RefreshCookie = None,
) -> TokenOut | JSONResponse:
    check_origin(request, settings)
    try:
        if not refresh_token:
            raise AuthenticationError("Sessiya topilmadi. Qayta kiring.", code="invalid_refresh")
        pair = await AuthService(session, settings).refresh(
            refresh_token,
            user_agent=request.headers.get("user-agent"),
            ip=client_ip(request),
        )
    except AuthenticationError as exc:
        # Return the error ourselves so the stale cookie is removed in the same response.
        failure = JSONResponse(error_body(exc.code, exc.message), status_code=exc.status_code)
        _clear_refresh_cookie(failure, settings)
        return failure
    _set_refresh_cookie(response, pair, settings)
    return _token_out(pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    refresh_token: RefreshCookie = None,
) -> Response:
    check_origin(request, settings)
    await AuthService(session, settings).logout(refresh_token)
    response.status_code = status.HTTP_204_NO_CONTENT
    _clear_refresh_cookie(response, settings)
    return response


@router.get("/me", response_model=AdminMeOut)
async def me(ctx: AdminDep) -> AdminMeOut:
    return AdminMeOut.build(ctx.admin)

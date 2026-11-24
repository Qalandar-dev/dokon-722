from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminSession, AdminUser
from tests.api.conftest import PASSWORD, AdminFactory

LOGIN = "/api/v1/admin/auth/login"
REFRESH = "/api/v1/admin/auth/refresh"
LOGOUT = "/api/v1/admin/auth/logout"
ME = "/api/v1/admin/auth/me"


def _refresh_cookie(r: httpx.Response) -> str:
    cookie = r.cookies.get("os_refresh")
    assert cookie, r.headers.get("set-cookie")
    return cookie


async def test_login_sets_httponly_cookie_and_returns_token(
    api: httpx.AsyncClient, make_admin: AdminFactory
) -> None:
    headers = await make_admin("manager")
    email = headers["X-Admin-Email"]
    api.cookies.clear()
    r = await api.post(LOGIN, json={"email": email.upper(), "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["admin"]["role"] == "manager"
    assert "staff.manage" not in body["admin"]["permissions"]
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "path=/api/v1/admin/auth" in set_cookie

    me = await api.get(ME, headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["email"] == email


async def test_wrong_password_and_unknown_email_look_the_same(
    api: httpx.AsyncClient, make_admin: AdminFactory
) -> None:
    email = (await make_admin())["X-Admin-Email"]
    wrong = await api.post(LOGIN, json={"email": email, "password": "notogri-parol"})
    unknown = await api.post(LOGIN, json={"email": "yoq@store.uz", "password": "notogri-parol"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


async def test_login_rate_limited(api: httpx.AsyncClient) -> None:
    statuses = [
        (await api.post(LOGIN, json={"email": "x@store.uz", "password": "p"})).status_code
        for _ in range(12)
    ]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429


async def test_refresh_rotates_and_detects_reuse(
    api: httpx.AsyncClient, make_admin: AdminFactory, db: AsyncSession
) -> None:
    email = (await make_admin())["X-Admin-Email"]
    api.cookies.clear()
    first = _refresh_cookie(await api.post(LOGIN, json={"email": email, "password": PASSWORD}))

    r = await api.post(REFRESH)
    assert r.status_code == 200
    second = _refresh_cookie(r)
    assert second != first

    # An attacker replays the old (already rotated) token…
    api.cookies.clear()
    api.cookies.set("os_refresh", first, path="/api/v1/admin/auth")
    stolen = await api.post(REFRESH)
    assert stolen.status_code == 401
    assert stolen.json()["error"]["code"] == "refresh_reused"
    assert (
        'os_refresh=""' in stolen.headers["set-cookie"]
        or "max-age=0" in stolen.headers["set-cookie"].lower()
    )

    # …which also ends the legitimate session of that login.
    api.cookies.clear()
    api.cookies.set("os_refresh", second, path="/api/v1/admin/auth")
    assert (await api.post(REFRESH)).status_code == 401


async def test_logout_revokes_refresh(api: httpx.AsyncClient, make_admin: AdminFactory) -> None:
    email = (await make_admin())["X-Admin-Email"]
    api.cookies.clear()
    token = _refresh_cookie(await api.post(LOGIN, json={"email": email, "password": PASSWORD}))
    assert (await api.post(LOGOUT)).status_code == 204
    api.cookies.set("os_refresh", token, path="/api/v1/admin/auth")
    assert (await api.post(REFRESH)).status_code == 401
    api.cookies.clear()
    assert (await api.post(REFRESH)).status_code == 401  # no cookie at all


async def test_deactivated_admin_is_locked_out_immediately(
    api: httpx.AsyncClient, make_admin: AdminFactory, db: AsyncSession
) -> None:
    headers = await make_admin("operator")
    assert (await api.get(ME, headers=headers)).status_code == 200
    await db.execute(
        update(AdminUser).where(AdminUser.email == headers["X-Admin-Email"]).values(is_active=False)
    )
    await db.commit()
    r = await api.get(ME, headers=headers)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "account_disabled"
    login = await api.post(LOGIN, json={"email": headers["X-Admin-Email"], "password": PASSWORD})
    assert login.status_code == 401


async def test_missing_or_garbage_token(api: httpx.AsyncClient) -> None:
    assert (await api.get(ME)).status_code == 401
    r = await api.get(ME, headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("role", "method", "path", "expected"),
    [
        ("operator", "GET", "/api/v1/admin/orders", 200),
        ("operator", "GET", "/api/v1/admin/products", 200),
        ("operator", "POST", "/api/v1/admin/categories", 403),
        ("operator", "GET", "/api/v1/admin/dashboard", 403),
        ("operator", "GET", "/api/v1/admin/promo-codes", 403),
        (
            "operator",
            "POST",
            "/api/v1/admin/inventory/00000000-0000-0000-0000-000000000000/adjust",
            403,
        ),
        ("manager", "GET", "/api/v1/admin/dashboard", 200),
        ("manager", "GET", "/api/v1/admin/reports/sales", 200),
        ("manager", "GET", "/api/v1/admin/staff", 403),
        ("manager", "GET", "/api/v1/admin/settings", 403),
        ("manager", "GET", "/api/v1/admin/audit-logs", 403),
        ("super_admin", "GET", "/api/v1/admin/staff", 200),
        ("super_admin", "GET", "/api/v1/admin/settings", 200),
        ("super_admin", "GET", "/api/v1/admin/audit-logs", 200),
    ],
)
async def test_permission_matrix(
    api: httpx.AsyncClient,
    make_admin: AdminFactory,
    role: str,
    method: str,
    path: str,
    expected: int,
) -> None:
    headers = await make_admin(role)
    body = {"name": "X"} if method == "POST" else None
    if path.endswith("/adjust"):
        body = {"delta": 1, "reason": "test"}
    r = await api.request(method, path, headers=headers, json=body)
    assert r.status_code == expected, r.text
    if expected == 403:
        assert r.json()["error"]["details"]["missing_permissions"]


async def test_sessions_are_stored_hashed(
    api: httpx.AsyncClient, make_admin: AdminFactory, db: AsyncSession
) -> None:
    email = (await make_admin())["X-Admin-Email"]
    api.cookies.clear()
    token = _refresh_cookie(await api.post(LOGIN, json={"email": email, "password": PASSWORD}))
    stored = list(await db.scalars(select(AdminSession.token_hash)))
    assert token not in stored
    assert all(len(h) == 64 for h in stored)


async def test_refresh_rejects_foreign_origin(
    api: httpx.AsyncClient, make_admin: AdminFactory
) -> None:
    email = (await make_admin())["X-Admin-Email"]
    api.cookies.clear()
    await api.post(LOGIN, json={"email": email, "password": PASSWORD})
    evil = await api.post(REFRESH, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    assert evil.json()["error"]["code"] == "bad_origin"
    own = await api.post(REFRESH, headers={"Origin": "http://testserver"})
    assert own.status_code == 200
    assert (await api.post(LOGOUT, headers={"Origin": "https://evil.example"})).status_code == 403

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, text, update

from app.models import AdminUser, RuleAuditLog
from tests.support import ADMIN_PASSWORD, ADMIN_USER, login, make_client


async def audit_actions(app: object) -> list[str]:
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        return list(await session.scalars(select(RuleAuditLog.action).order_by(RuleAuditLog.id)))


async def test_login_sets_httponly_session_and_readable_csrf_cookie(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("tlmn_admin_session="))
    csrf_cookie = next(c for c in cookies if c.startswith("tlmn_admin_csrf="))
    assert "HttpOnly" in session_cookie and "SameSite=strict" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    me = await client.get("/api/admin/me")
    assert me.json()["admin"] == {"username": ADMIN_USER, "role": "SYSTEM_ADMIN"}


async def test_username_is_case_insensitive(client: httpx.AsyncClient) -> None:
    await login(client, username="ADMIN")


async def test_wrong_password_is_401_and_audited(app: object, client: httpx.AsyncClient) -> None:
    response = await client.post("/api/admin/login", json={"username": ADMIN_USER, "password": "sai"})
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "INVALID_LOGIN"
    assert (await audit_actions(app))[-1] == "LOGIN_FAILED"


async def test_unknown_user_gets_same_error_as_wrong_password(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/admin/login", json={"username": "khong-co", "password": "x"})
    assert (response.status_code, response.json()["code"]) == (401, "INVALID_LOGIN")


async def test_account_locks_after_10_failures_then_unlocks(app: object, client: httpx.AsyncClient) -> None:
    for _ in range(10):
        await client.post("/api/admin/login", json={"username": ADMIN_USER, "password": "sai"})
    locked = await client.post("/api/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    assert locked.status_code == 401  # đúng mật khẩu nhưng đang bị khóa
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        await session.execute(update(AdminUser).values(locked_until=datetime.now(UTC) - timedelta(seconds=1)))
        await session.commit()
    await login(client)


async def test_login_rate_limit_per_ip(app: object, client: httpx.AsyncClient) -> None:
    app.state.login_limiter.limit = 5  # type: ignore[attr-defined]
    for _ in range(5):
        await client.post("/api/admin/login", json={"username": ADMIN_USER, "password": "sai"})
    response = await client.post(
        "/api/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 429


async def test_write_without_csrf_header_is_403(admin_client: httpx.AsyncClient) -> None:
    del admin_client.headers["X-CSRF-Token"]
    response = await admin_client.post("/api/admin/rules/draft", json={})
    assert (response.status_code, response.json()["code"]) == (403, "CSRF_FAILED")


async def test_logout_revokes_session(app: object, admin_client: httpx.AsyncClient) -> None:
    assert (await admin_client.post("/api/admin/logout")).status_code == 204
    # Cookie bị xóa phía client; thử lại bằng cookie cũ cũng phải bị từ chối.
    assert (await admin_client.get("/api/admin/me")).status_code == 401
    assert (await audit_actions(app))[-1] == "LOGOUT"


async def test_revoked_session_cookie_cannot_be_reused(app: object) -> None:
    async with make_client(app) as c:
        await login(c)
        cookie = c.cookies.get("tlmn_admin_session")
        await c.post("/api/admin/logout")
    async with make_client(app) as attacker:
        attacker.cookies.set("tlmn_admin_session", cookie or "")
        assert (await attacker.get("/api/admin/me")).status_code == 401


async def test_audit_log_is_append_only_in_database(app: object, admin_client: httpx.AsyncClient) -> None:
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        with pytest.raises(Exception, match="append-only"):
            await session.execute(text("UPDATE rule_audit_logs SET action = 'X'"))
        await session.rollback()
        with pytest.raises(Exception, match="append-only"):
            await session.execute(text("DELETE FROM rule_audit_logs"))

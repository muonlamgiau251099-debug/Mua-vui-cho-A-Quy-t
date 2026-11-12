"""Fixture test backend với PostgreSQL thật.

DB test: TEST_DATABASE_URL (mặc định postgresql+asyncpg://tlmn:tlmn@localhost:5432/tlmn_test).
Nếu không kết nối được PostgreSQL: test cần DB bị SKIP (local), hoặc FAIL khi đặt REQUIRE_DB=1 (CI).
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.db import make_engine, make_sessionmaker
from app.main import create_app
from app.services.admin_auth import create_admin
from app.services.rules import ensure_seeded
from tests.support import ADMIN_PASSWORD, ADMIN_USER, login, make_client

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://tlmn:tlmn@localhost:5432/tlmn_test")
TABLES = (
    "command_dedup, game_events, games, game_sessions, room_seats, rooms, guest_players, "
    "rule_audit_logs, global_rule_versions, admin_sessions, admin_users"
)


async def _ensure_database(url: str) -> None:
    plain = url.replace("postgresql+asyncpg://", "postgresql://")
    base, name = plain.rsplit("/", 1)
    conn = await asyncpg.connect(f"{base}/postgres", timeout=3)
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def database_url() -> str:
    try:
        asyncio.run(_ensure_database(TEST_DB_URL))
    except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
        message = f"PostgreSQL chưa chạy ({exc.__class__.__name__}): {TEST_DB_URL}"
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail(message)
        pytest.skip(message)
    env = {**os.environ, "DATABASE_URL": TEST_DB_URL}
    for args in (["downgrade", "base"], ["upgrade", "head"]):
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
            capture_output=True,
        )
    return TEST_DB_URL


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        cookie_secure=False,
        login_rate_limit_per_minute=1000,
        room_lookup_per_minute=1000,
        room_create_per_hour=1000,
        ws_auth_timeout_seconds=1.0,
        seat_sweep_interval_seconds=3600,  # test tự gọi sweep_once
    )


async def reset_database(engine: AsyncEngine) -> None:
    """Xóa dữ liệu, tạo luật v1 và tài khoản Admin mặc định."""
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    async with make_sessionmaker(engine)() as session:
        await ensure_seeded(session)
        await create_admin(session, ADMIN_USER, ADMIN_PASSWORD)
        await session.commit()


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    await reset_database(application.state.engine)
    yield application
    await application.state.engine.dispose()


@pytest.fixture
def ws_app(settings: Settings) -> Iterator[FastAPI]:
    """App cho test WebSocket (Starlette TestClient chạy app trong event loop riêng).

    DB được reset bằng engine riêng rồi dispose, để pool của app chỉ tạo kết nối trong loop của TestClient.
    """

    async def _reset() -> None:
        engine = make_engine(settings.database_url)
        try:
            await reset_database(engine)
        finally:
            await engine.dispose()

    asyncio.run(_reset())
    yield create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with make_client(app) as c:
        yield c


@pytest.fixture
async def admin_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with make_client(app) as c:
        await login(c)
        yield c


@pytest.fixture
def no_db_settings() -> Iterator[Settings]:
    # Cổng 1 không có PostgreSQL → dùng cho test không cần DB.
    yield Settings(database_url="postgresql+asyncpg://x:x@127.0.0.1:1/none")

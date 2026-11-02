from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import AdminSession, AdminUser, GuestPlayer
from app.services import admin_auth, guests
from app.services.audit import RequestMeta

SESSION_COOKIE = "tlmn_admin_session"
CSRF_COOKIE = "tlmn_admin_csrf"
CSRF_HEADER = "X-CSRF-Token"


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def request_meta(request: Request) -> RequestMeta:
    agent = request.headers.get("user-agent")
    return RequestMeta(request.client.host if request.client else None, agent[:400] if agent else None)


@dataclass(frozen=True, slots=True)
class AdminContext:
    admin: AdminUser
    session: AdminSession


async def current_admin(request: Request, db: Annotated[AsyncSession, Depends(get_session)]) -> AdminContext:
    admin, admin_session = await admin_auth.authenticate(db, request.cookies.get(SESSION_COOKIE))
    return AdminContext(admin, admin_session)


async def admin_write(
    ctx: Annotated[AdminContext, Depends(current_admin)],
    csrf: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> AdminContext:
    """Admin + kiểm tra CSRF; dùng cho mọi endpoint ghi."""
    admin_auth.check_csrf(ctx.session, csrf)
    return ctx


async def current_guest(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> GuestPlayer:
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    return await guests.authenticate_guest(db, request.app.state.settings, token)


def parse_if_match(value: str | None) -> int | None:
    """If-Match nhận dạng ETag `"3"`, `W/"3"` hoặc `3`."""
    if value is None:
        return None
    cleaned = value.strip().removeprefix("W/").strip('"')
    return int(cleaned) if cleaned.isdigit() else -1


DbSession = Annotated[AsyncSession, Depends(get_session)]
Meta = Annotated[RequestMeta, Depends(request_meta)]
AdminRead = Annotated[AdminContext, Depends(current_admin)]
AdminWrite = Annotated[AdminContext, Depends(admin_write)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]
Guest = Annotated[GuestPlayer, Depends(current_guest)]

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import CSRF_COOKIE, SESSION_COOKIE, AdminRead, AdminWrite, AppSettings, DbSession, Meta
from app.errors import AppError
from app.services import admin_auth

router = APIRouter(prefix="/api/admin", tags=["admin-auth"])


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


def _admin_json(username: str) -> dict[str, object]:
    return {"username": username, "role": "SYSTEM_ADMIN"}


@router.post("/login")
async def login(
    body: LoginBody, request: Request, response: Response, db: DbSession, meta: Meta, settings: AppSettings
) -> dict[str, object]:
    if not request.app.state.login_limiter.allow(meta.ip or "unknown"):
        raise AppError(429, "RATE_LIMITED", "Thử đăng nhập quá nhiều lần, hãy đợi 1 phút")
    result = await admin_auth.login(db, settings, meta, body.username, body.password)
    max_age = settings.admin_session_hours * 3600
    for name, value, httponly in (
        (SESSION_COOKIE, result.session_token, True),
        (CSRF_COOKIE, result.csrf_token, False),  # JS đọc cookie này để gửi header X-CSRF-Token
    ):
        response.set_cookie(
            name, value, max_age=max_age, httponly=httponly, secure=settings.cookie_secure, samesite="strict"
        )
    return {
        "admin": _admin_json(result.admin.username),
        "csrfToken": result.csrf_token,
        "expiresAt": result.expires_at.isoformat(),
    }


@router.post("/logout", status_code=204)
async def logout(ctx: AdminWrite, response: Response, db: DbSession, meta: Meta) -> None:
    await admin_auth.logout(db, meta, ctx.admin, ctx.session)
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(CSRF_COOKIE)


@router.get("/me")
async def me(ctx: AdminRead) -> dict[str, object]:
    return {"admin": _admin_json(ctx.admin.username)}

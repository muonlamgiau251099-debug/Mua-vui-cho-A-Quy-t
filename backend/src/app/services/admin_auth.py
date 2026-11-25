"""Đăng nhập / phiên làm việc của Admin hệ thống (ID 134: chỉ Admin được sửa luật)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import AppError
from app.models import AdminSession, AdminUser
from app.security import MIN_PASSWORD_LENGTH, hash_password, new_token, token_hash, verify_password
from app.services.audit import RequestMeta, add_audit

INVALID_LOGIN = "Sai tên đăng nhập hoặc mật khẩu, hoặc tài khoản đang tạm khóa"


@dataclass(frozen=True, slots=True)
class LoginResult:
    admin: AdminUser
    session_token: str
    csrf_token: str
    expires_at: datetime


async def create_admin(session: AsyncSession, username: str, password: str) -> AdminUser:
    username = username.strip()
    if not 3 <= len(username) <= 50:
        raise ValueError("Tên đăng nhập phải dài 3–50 ký tự")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự")
    exists = await session.scalar(
        select(AdminUser.id).where(func.lower(AdminUser.username) == username.lower())
    )
    if exists:
        raise ValueError(f"Admin '{username}' đã tồn tại")
    admin = AdminUser(username=username, password_hash=hash_password(password))
    session.add(admin)
    await session.flush()
    return admin


async def login(
    session: AsyncSession, settings: Settings, meta: RequestMeta, username: str, password: str
) -> LoginResult:
    now = datetime.now(UTC)
    admin = await session.scalar(
        select(AdminUser).where(func.lower(AdminUser.username) == username.strip().lower()).with_for_update()
    )
    password_ok = verify_password(admin.password_hash if admin else None, password)
    locked = admin is not None and admin.locked_until is not None and admin.locked_until > now

    if admin is None or not admin.is_active or locked or not password_ok:
        if admin is not None and admin.is_active and not locked:
            admin.failed_attempts += 1
            if admin.failed_attempts >= settings.admin_max_failed_logins:
                admin.locked_until = now + timedelta(minutes=settings.admin_lock_minutes)
                admin.failed_attempts = 0
        add_audit(
            session,
            meta,
            "LOGIN_FAILED",
            admin_id=admin.id if admin else None,
            detail={
                "username": username[:50],
                "locked": bool(admin and admin.locked_until and admin.locked_until > now),
            },
        )
        await session.commit()
        raise AppError(401, "INVALID_LOGIN", INVALID_LOGIN)

    admin.failed_attempts = 0
    admin.locked_until = None
    admin.last_login_at = now
    session_token, csrf_token = new_token(), new_token()
    expires_at = now + timedelta(hours=settings.admin_session_hours)
    session.add(
        AdminSession(
            admin_id=admin.id,
            token_hash=token_hash(session_token),
            csrf_hash=token_hash(csrf_token),
            expires_at=expires_at,
            ip=meta.ip,
            user_agent=meta.user_agent,
        )
    )
    add_audit(session, meta, "LOGIN", admin_id=admin.id)
    await session.commit()
    return LoginResult(admin, session_token, csrf_token, expires_at)


async def authenticate(session: AsyncSession, session_token: str | None) -> tuple[AdminUser, AdminSession]:
    if not session_token:
        raise AppError(401, "UNAUTHORIZED", "Cần đăng nhập Admin")
    row = await session.execute(
        select(AdminSession, AdminUser)
        .join(AdminUser, AdminUser.id == AdminSession.admin_id)
        .where(AdminSession.token_hash == token_hash(session_token))
    )
    found = row.first()
    now = datetime.now(UTC)
    if found is None:
        raise AppError(401, "UNAUTHORIZED", "Cần đăng nhập Admin")
    admin_session, admin = found
    if admin_session.revoked_at is not None or admin_session.expires_at <= now or not admin.is_active:
        raise AppError(401, "UNAUTHORIZED", "Phiên đăng nhập đã hết hạn")
    return admin, admin_session


def check_csrf(admin_session: AdminSession, csrf_header: str | None) -> None:
    if not csrf_header or token_hash(csrf_header) != admin_session.csrf_hash:
        raise AppError(403, "CSRF_FAILED", "Thiếu hoặc sai mã chống giả mạo yêu cầu (CSRF)")


async def logout(
    session: AsyncSession, meta: RequestMeta, admin: AdminUser, admin_session: AdminSession
) -> None:
    admin_session.revoked_at = datetime.now(UTC)
    add_audit(session, meta, "LOGOUT", admin_id=admin.id)
    await session.commit()

"""Người chơi khách: nickname + token reconnect (ADR-013). Không lưu token gốc, chỉ lưu sha256."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import AppError
from app.models import GuestPlayer
from app.security import new_token, token_hash

NICKNAME_MIN, NICKNAME_MAX = 2, 20
_ALLOWED_PUNCT = " ._-"
# Chỉ cập nhật hạn token tối đa 1 lần/giờ để không ghi DB ở mọi request.
_TOUCH_EVERY = timedelta(hours=1)


def normalize_nickname(raw: str) -> str:
    nickname = " ".join(raw.split())
    if not NICKNAME_MIN <= len(nickname) <= NICKNAME_MAX:
        raise AppError(422, "NICKNAME_INVALID", f"Tên phải dài {NICKNAME_MIN}–{NICKNAME_MAX} ký tự")
    if not all(ch.isalnum() or ch in _ALLOWED_PUNCT for ch in nickname) or not any(
        ch.isalnum() for ch in nickname
    ):
        raise AppError(422, "NICKNAME_INVALID", "Tên chỉ gồm chữ, số, khoảng trắng và . _ -")
    return nickname


async def create_guest(session: AsyncSession, settings: Settings, nickname: str) -> tuple[GuestPlayer, str]:
    token = new_token()
    guest = GuestPlayer(
        nickname=normalize_nickname(nickname),
        token_hash=token_hash(token),
        expires_at=datetime.now(UTC) + timedelta(days=settings.guest_token_days),
    )
    session.add(guest)
    await session.commit()
    return guest, token


async def authenticate_guest(session: AsyncSession, settings: Settings, token: str | None) -> GuestPlayer:
    if not token:
        raise AppError(401, "GUEST_UNAUTHORIZED", "Cần nhập tên để chơi")
    guest = await session.scalar(select(GuestPlayer).where(GuestPlayer.token_hash == token_hash(token)))
    now = datetime.now(UTC)
    if guest is None or guest.expires_at <= now:
        raise AppError(401, "GUEST_UNAUTHORIZED", "Phiên chơi đã hết hạn, hãy nhập tên lại")
    if now - guest.last_seen_at >= _TOUCH_EVERY:
        guest.last_seen_at = now
        guest.expires_at = now + timedelta(days=settings.guest_token_days)
        await session.commit()
    return guest


async def rename(session: AsyncSession, guest: GuestPlayer, nickname: str) -> GuestPlayer:
    guest.nickname = normalize_nickname(nickname)
    await session.commit()
    return guest

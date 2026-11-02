import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GameSession(Base):
    """Phiên chơi: chuỗi ván với cùng 4 người (đổi người = phiên mới — Q-P1-10)."""

    __tablename__ = "game_sessions"
    __table_args__ = (
        UniqueConstraint("room_id", "session_no", name="uq_game_sessions_room_no"),
        Index(
            "ux_game_sessions_one_active", "room_id", unique=True, postgresql_where=text("status = 'ACTIVE'")
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"))
    session_no: Mapped[int]
    roster: Mapped[list[Any]]  # guestId (str) theo ghế 0–3
    status: Mapped[str] = mapped_column(String(10), server_default=text("'ACTIVE'"))
    end_reason: Mapped[str | None] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        UniqueConstraint("session_id", "game_no", name="uq_games_session_no"),
        Index(
            "ux_games_one_in_progress",
            "room_id",
            unique=True,
            postgresql_where=text("status = 'IN_PROGRESS'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("game_sessions.id"))
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"))
    game_no: Mapped[int]
    rule_version: Mapped[int]
    rules_snapshot: Mapped[dict[str, Any]]
    rules_hash: Mapped[str] = mapped_column(String(64))
    opening_mode: Mapped[str] = mapped_column(String(16))
    deck: Mapped[list[Any]]  # chỉ server đọc; client nhận sau khi ván kết thúc
    deck_salt: Mapped[str] = mapped_column(String(64))
    deck_commitment: Mapped[str] = mapped_column(String(64))
    redeal_count: Mapped[int] = mapped_column(server_default=text("0"))
    status: Mapped[str] = mapped_column(String(12), server_default=text("'IN_PROGRESS'"))
    end_type: Mapped[str | None] = mapped_column(String(20))
    cancel_reason: Mapped[str | None] = mapped_column(String(30))
    winner_seat: Mapped[int | None] = mapped_column(SmallInteger)
    last_seq: Mapped[int] = mapped_column(server_default=text("0"))
    state_hash: Mapped[str | None] = mapped_column(String(64))  # hash trạng thái sau action cuối
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GameEvent(Base):
    """Mỗi dòng = 1 action đã áp dụng (input + now) kèm các event engine sinh ra. Append-only."""

    __tablename__ = "game_events"
    __table_args__ = (UniqueConstraint("game_id", "seq", name="uq_game_events_seq"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id"))
    seq: Mapped[int]
    type: Mapped[str] = mapped_column(String(20))
    actor_seat: Mapped[int | None] = mapped_column(SmallInteger)
    request_id: Mapped[uuid.UUID | None]
    payload: Mapped[dict[str, Any]]  # {"now", "action", "events"} — đủ để replay deterministic
    state_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommandDedup(Base):
    """Phản hồi đã gửi cho (ván, ghế, requestId): gửi lặp → trả lại đúng phản hồi cũ (AC6)."""

    __tablename__ = "command_dedup"

    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    seat: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    outcome: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GameResult(Base):
    """Kết quả ván FINISHED. PK = game_id → không thể ghi/cộng điểm một ván hai lần."""

    __tablename__ = "game_results"

    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("game_sessions.id"), index=True)
    end_type: Mapped[str] = mapped_column(String(20))
    ranks: Mapped[list[Any]]
    statuses: Mapped[list[Any]]
    net: Mapped[list[Any]]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScoreTransfer(Base):
    """Một khoản chuyển điểm (ID 131, 132). Append-only; tổng mỗi ván bằng 0."""

    __tablename__ = "score_transfers"
    __table_args__ = (UniqueConstraint("game_id", "line_no", name="uq_score_transfers_line"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id"))
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("game_sessions.id"), index=True)
    line_no: Mapped[int]
    from_seat: Mapped[int] = mapped_column(SmallInteger)
    to_seat: Mapped[int] = mapped_column(SmallInteger)
    from_guest: Mapped[uuid.UUID] = mapped_column(ForeignKey("guest_players.id"))
    to_guest: Mapped[uuid.UUID] = mapped_column(ForeignKey("guest_players.id"))
    amount: Mapped[int]
    reason: Mapped[str] = mapped_column(String(30))
    detail: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SessionScore(Base):
    """Tổng điểm phiên của từng người (ID 111, 130); chỉ cập nhật cùng transaction với GameResult."""

    __tablename__ = "session_scores"

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("game_sessions.id"), primary_key=True)
    guest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guest_players.id"), primary_key=True)
    seat: Mapped[int] = mapped_column(SmallInteger)
    total: Mapped[int] = mapped_column(server_default=text("0"))
    games_counted: Mapped[int] = mapped_column(server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GameSnapshot(Base):
    """Trạng thái đầy đủ của ván tại seq (luôn có seq 0; thêm mỗi khi đóng vòng hoặc mỗi 20 action)."""

    __tablename__ = "game_snapshots"

    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[dict[str, Any]]
    state_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GuestPlayer(Base):
    """Người chơi khách: chỉ có nickname + token reconnect (DB lưu sha256 của token)."""

    __tablename__ = "guest_players"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    nickname: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        CheckConstraint("status IN ('WAITING', 'PLAYING', 'CLOSED')", name="ck_rooms_status"),
        # Mã phòng chỉ cần duy nhất trong số phòng chưa đóng; phòng đóng thì mã được dùng lại.
        Index("ux_rooms_open_code", "code", unique=True, postgresql_where=text("status <> 'CLOSED'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(String(6))
    owner_guest_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("guest_players.id"))
    status: Mapped[str] = mapped_column(String(10), server_default=text("'WAITING'"))
    state_version: Mapped[int] = mapped_column(server_default=text("0"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("guest_players.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(String(20))


class RoomSeat(Base):
    __tablename__ = "room_seats"
    __table_args__ = (
        CheckConstraint("seat_no BETWEEN 0 AND 3", name="ck_room_seats_seat_no"),
        CheckConstraint("conn_state IN ('EMPTY', 'CONNECTED', 'DISCONNECTED')", name="ck_room_seats_conn"),
        CheckConstraint("(guest_id IS NULL) = (conn_state = 'EMPTY')", name="ck_room_seats_guest"),
        # Một guest chỉ ngồi một ghế trong toàn hệ thống (ghế của phòng đóng được giải phóng).
        Index("ux_room_seats_guest", "guest_id", unique=True, postgresql_where=text("guest_id IS NOT NULL")),
        Index("ix_room_seats_hold", "hold_until", postgresql_where=text("conn_state = 'DISCONNECTED'")),
    )

    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), primary_key=True)
    seat_no: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    guest_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("guest_players.id"))
    conn_state: Mapped[str] = mapped_column(String(12), server_default=text("'EMPTY'"))
    ready: Mapped[bool] = mapped_column(server_default=text("false"))
    hold_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

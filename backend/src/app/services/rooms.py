"""Phòng chơi 3 hoặc 4 ghế (ID 2, 139, 140, 143, 144, 146, 147; D5; yêu cầu mới: chơi được 3 người).

Mọi thay đổi phòng khóa dòng `rooms` (SELECT ... FOR UPDATE) nên REST và WebSocket không ghi chồng nhau.
Mỗi thay đổi tăng `state_version` — client dùng làm `sequence` để bỏ qua trạng thái cũ.
Hàm ghi tự commit; caller broadcast sau khi commit (ADR-006).
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import Game, GuestPlayer, Room, RoomSeat
from app.services import rules, scores

SEAT_COUNT = 4  # số ghế khi tạo phòng; chủ phòng có thể giảm còn 3 (số ghế = số hàng room_seats)
PLAYER_COUNTS = (3, 4)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # bỏ 0/O/1/I để đọc mã không nhầm
CODE_LENGTH = 6
DEFAULT_SEAT_HOLD_SECONDS = 120


def _now() -> datetime:
    return datetime.now(UTC)


def new_room_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


async def seat_hold_seconds(session: AsyncSession) -> int:
    """Thời gian giữ ghế lấy từ luật GLOBAL đang áp dụng (ID 144)."""
    try:
        active = await rules.get_active(session)
    except AppError:
        return DEFAULT_SEAT_HOLD_SECONDS
    return int(active.config.get("room", {}).get("seatHoldSeconds", DEFAULT_SEAT_HOLD_SECONDS))


async def _lock_room(session: AsyncSession, room_id: uuid.UUID) -> Room:
    room = await session.scalar(select(Room).where(Room.id == room_id).with_for_update())
    if room is None:
        raise AppError(404, "ROOM_NOT_FOUND", "Không tìm thấy phòng")
    return room


async def _seats(session: AsyncSession, room_id: uuid.UUID) -> list[RoomSeat]:
    rows = await session.scalars(
        select(RoomSeat).where(RoomSeat.room_id == room_id).order_by(RoomSeat.seat_no)
    )
    return list(rows)


async def seat_of_guest(session: AsyncSession, guest_id: uuid.UUID) -> RoomSeat | None:
    return await session.scalar(select(RoomSeat).where(RoomSeat.guest_id == guest_id))


def _release(seat: RoomSeat) -> None:
    seat.guest_id = None
    seat.conn_state = "EMPTY"
    seat.ready = False
    seat.hold_until = None
    seat.joined_at = None


def _transfer_owner(room: Room, seats: list[RoomSeat], from_seat: int) -> None:
    """Chủ phòng rời → chuyển cho người kế tiếp theo chiều kim đồng hồ."""
    for step in range(1, len(seats)):
        seat = seats[(from_seat + step) % len(seats)]
        if seat.guest_id is not None:
            room.owner_guest_id = seat.guest_id
            return
    room.owner_guest_id = None


def _close(room: Room, seats: list[RoomSeat], reason: str) -> None:
    for seat in seats:
        _release(seat)
    room.status = "CLOSED"
    room.closed_at = _now()
    room.close_reason = reason
    room.owner_guest_id = None


def _occupy(seat: RoomSeat, guest_id: uuid.UUID, hold_seconds: int) -> None:
    # Ghế giữ ở trạng thái DISCONNECTED cho tới khi WebSocket kết nối; quá hạn giữ ghế thì nhả ghế.
    seat.guest_id = guest_id
    seat.conn_state = "DISCONNECTED"
    seat.ready = False
    seat.hold_until = _now() + timedelta(seconds=hold_seconds)
    seat.joined_at = _now()


async def _already_in_room_error(session: AsyncSession, seat: RoomSeat) -> AppError:
    room = await session.get(Room, seat.room_id)
    return AppError(
        409, "ALREADY_IN_ROOM", "Bạn đang ngồi ở một phòng khác", roomCode=room.code if room else None
    )


async def create_room(session: AsyncSession, guest: GuestPlayer) -> Room:
    existing = await seat_of_guest(session, guest.id)
    if existing is not None:
        raise await _already_in_room_error(session, existing)
    hold = await seat_hold_seconds(session)
    for _ in range(10):
        room = Room(code=new_room_code(), owner_guest_id=guest.id, created_by=guest.id, status="WAITING")
        session.add(room)
        try:
            await session.flush()
            seats = [RoomSeat(room_id=room.id, seat_no=n, conn_state="EMPTY") for n in range(SEAT_COUNT)]
            _occupy(seats[0], guest.id, hold)
            session.add_all(seats)
            await session.commit()
            return room
        except IntegrityError:
            await session.rollback()
            existing = await seat_of_guest(session, guest.id)
            if existing is not None:  # tạo phòng song song ở tab khác
                raise await _already_in_room_error(session, existing) from None
    raise AppError(503, "ROOM_CODE_EXHAUSTED", "Không tạo được mã phòng, hãy thử lại")


async def find_open_room(session: AsyncSession, code: str) -> Room:
    room = await session.scalar(
        select(Room).where(Room.code == code.strip().upper(), Room.status != "CLOSED")
    )
    if room is None:
        raise AppError(404, "ROOM_NOT_FOUND", "Không tìm thấy phòng với mã này")
    return room


async def join(
    session: AsyncSession, guest: GuestPlayer, room_id: uuid.UUID, seat_no: int | None
) -> RoomSeat:
    room = await _lock_room(session, room_id)
    if room.status == "CLOSED":
        raise AppError(409, "ROOM_CLOSED", "Phòng đã đóng")
    existing = await seat_of_guest(session, guest.id)
    if existing is not None:
        if existing.room_id == room_id:
            return existing  # vào lại phòng của mình: không làm gì
        raise await _already_in_room_error(session, existing)
    if room.status == "PLAYING":
        raise AppError(
            409, "GAME_IN_PROGRESS", "Phòng đang chơi; chỉ thay người sau khi ván kết thúc"
        )  # ID 146
    seats = await _seats(session, room_id)
    if seat_no is not None:
        if seat_no >= len(seats):
            raise AppError(404, "SEAT_NOT_FOUND", "Phòng không có ghế này")
        seat = seats[seat_no]
        if seat.guest_id is not None:
            raise AppError(409, "SEAT_TAKEN", "Ghế này đã có người")
    else:
        free = [s for s in seats if s.guest_id is None]
        if not free:
            raise AppError(409, "ROOM_FULL", f"Phòng đã đủ {len(seats)} người")
        seat = free[0]
    _occupy(seat, guest.id, await seat_hold_seconds(session))
    if room.owner_guest_id is None:
        room.owner_guest_id = guest.id
    room.state_version += 1
    try:
        await session.commit()
    except IntegrityError:  # cùng guest vào 2 phòng cùng lúc
        await session.rollback()
        raise AppError(409, "ALREADY_IN_ROOM", "Bạn đang ngồi ở một phòng khác") from None
    return seat


@dataclass(frozen=True, slots=True)
class LeaveResult:
    room_closed: bool


async def leave(session: AsyncSession, guest_id: uuid.UUID, room_id: uuid.UUID) -> LeaveResult:
    room = await _lock_room(session, room_id)
    seats = await _seats(session, room_id)
    seat = next((s for s in seats if s.guest_id == guest_id), None)
    if seat is None:
        raise AppError(404, "NOT_IN_ROOM", "Bạn không ngồi trong phòng này")
    # Đang có ván: caller đã xử thua người này (D9) trước khi gọi; ghế được giải phóng ngay.
    _release(seat)
    if room.owner_guest_id == guest_id:
        _transfer_owner(room, seats, seat.seat_no)
    closed = all(s.guest_id is None for s in seats)
    if closed:
        _close(room, seats, "EMPTY")  # D5: mọi người rời → hủy bàn
    room.state_version += 1
    await session.commit()
    return LeaveResult(room_closed=closed)


async def kick_by_owner(
    session: AsyncSession, owner_id: uuid.UUID, room_id: uuid.UUID, seat_no: int
) -> uuid.UUID:
    """Chủ phòng mời người khác ra (chỉ khi chưa vào ván). Trả về guest bị mời ra để ngắt kết nối."""
    room = await _lock_room(session, room_id)
    if room.status == "CLOSED":
        raise AppError(409, "ROOM_CLOSED", "Phòng đã đóng")
    if room.owner_guest_id != owner_id:
        raise AppError(403, "NOT_OWNER", "Chỉ chủ phòng được mời người chơi ra")
    if room.status != "WAITING":
        raise AppError(409, "GAME_IN_PROGRESS", "Chỉ mời người chơi ra khi chưa vào ván")
    seats = await _seats(session, room_id)
    if seat_no >= len(seats):
        raise AppError(404, "SEAT_NOT_FOUND", "Phòng không có ghế này")
    seat = seats[seat_no]
    if seat.guest_id is None:
        raise AppError(404, "SEAT_EMPTY", "Ghế này đang trống")
    if seat.guest_id == owner_id:
        raise AppError(409, "CANNOT_KICK_SELF", "Không thể tự mời mình ra, hãy dùng Rời phòng")
    kicked = seat.guest_id
    _release(seat)
    room.state_version += 1
    await session.commit()
    return kicked


async def set_player_count(session: AsyncSession, guest_id: uuid.UUID, room_id: uuid.UUID, count: int) -> int:
    """Chủ phòng đổi phòng giữa 3 và 4 người (chỉ khi phòng đang chờ). Số ghế = số hàng room_seats.

    4 → 3 chỉ khi ghế cuối (ghế 4) đang trống; 3 → 4 thêm lại ghế cuối. Phiên chơi đang có tự thành phiên mới
    ở ván kế tiếp vì danh sách người chơi đổi (Q-P1-10)."""
    if count not in PLAYER_COUNTS:
        raise AppError(422, "PLAYER_COUNT_INVALID", "Phòng chỉ chơi được 3 hoặc 4 người")
    room = await _lock_room(session, room_id)
    if room.status == "CLOSED":
        raise AppError(409, "ROOM_CLOSED", "Phòng đã đóng")
    if room.owner_guest_id != guest_id:
        raise AppError(403, "NOT_OWNER", "Chỉ chủ phòng được đổi số người chơi")
    if room.status != "WAITING":
        raise AppError(409, "GAME_IN_PROGRESS", "Chỉ đổi số người chơi khi chưa vào ván")
    seats = await _seats(session, room_id)
    if count == len(seats):
        return count
    if count < len(seats):
        last = seats[-1]
        if last.guest_id is not None:
            raise AppError(
                409,
                "SEAT_OCCUPIED",
                f"Ghế {last.seat_no + 1} đang có người, hãy mời người đó ra trước khi giảm số người chơi",
            )
        await session.delete(last)
    else:
        session.add(RoomSeat(room_id=room_id, seat_no=len(seats), conn_state="EMPTY"))
    for seat in seats:
        seat.ready = False  # mọi người xác nhận lại sau khi đổi chế độ
    room.state_version += 1
    await session.commit()
    return count


async def close_by_owner(session: AsyncSession, guest_id: uuid.UUID, room_id: uuid.UUID) -> None:
    room = await _lock_room(session, room_id)
    if room.status == "CLOSED":
        return
    if room.owner_guest_id != guest_id:
        raise AppError(403, "NOT_OWNER", "Chỉ chủ phòng được đóng phòng")  # ID 147
    _close(room, await _seats(session, room_id), "OWNER_CLOSED")
    room.state_version += 1
    await session.commit()


async def set_connected(session: AsyncSession, room_id: uuid.UUID, guest_id: uuid.UUID) -> int:
    """Gắn kết nối WebSocket với ghế. Trả về số ghế; lỗi nếu guest không ngồi phòng này."""
    room = await _lock_room(session, room_id)
    seat = next((s for s in await _seats(session, room_id) if s.guest_id == guest_id), None)
    if room.status == "CLOSED" or seat is None:
        raise AppError(403, "NOT_IN_ROOM", "Bạn không ngồi trong phòng này")
    seat.conn_state = "CONNECTED"
    seat.hold_until = None
    room.state_version += 1
    await session.commit()
    return seat.seat_no


async def set_disconnected(session: AsyncSession, room_id: uuid.UUID, guest_id: uuid.UUID) -> bool:
    """Mất kết nối: giữ ghế seatHoldSeconds (ID 143, 144) và bỏ trạng thái sẵn sàng."""
    room = await _lock_room(session, room_id)
    seat = next((s for s in await _seats(session, room_id) if s.guest_id == guest_id), None)
    if seat is None or seat.conn_state != "CONNECTED":
        await session.rollback()
        return False
    seat.conn_state = "DISCONNECTED"
    seat.ready = False
    seat.hold_until = _now() + timedelta(seconds=await seat_hold_seconds(session))
    room.state_version += 1
    await session.commit()
    return True


async def mark_all_disconnected(session: AsyncSession, room_id: uuid.UUID) -> None:
    """Server vừa khởi động lại: không còn WebSocket nào → mọi ghế mất kết nối, được giữ ghế (ID 143, 144)."""
    room = await _lock_room(session, room_id)
    hold = timedelta(seconds=await seat_hold_seconds(session))
    for seat in await _seats(session, room_id):
        if seat.guest_id is not None:
            seat.conn_state = "DISCONNECTED"
            seat.ready = False
            seat.hold_until = _now() + hold
    room.state_version += 1
    await session.commit()


async def set_ready(session: AsyncSession, room_id: uuid.UUID, guest_id: uuid.UUID, ready: bool) -> bool:
    """ID 139. True nếu mọi ghế của phòng (3 hoặc 4) có người, đã kết nối và cùng sẵn sàng (ID 140)."""
    room = await _lock_room(session, room_id)
    if room.status != "WAITING":
        raise AppError(409, "ROOM_NOT_WAITING", "Phòng không ở trạng thái chờ")
    seats = await _seats(session, room_id)
    seat = next((s for s in seats if s.guest_id == guest_id), None)
    if seat is None or seat.conn_state != "CONNECTED":
        raise AppError(409, "NOT_CONNECTED", "Bạn chưa kết nối vào phòng")
    if seat.ready != ready:
        seat.ready = ready
        room.state_version += 1
    await session.commit()
    return all(s.conn_state == "CONNECTED" and s.ready for s in seats)


@dataclass(frozen=True, slots=True)
class SweepResult:
    changed_rooms: list[uuid.UUID]
    closed_rooms: list[uuid.UUID]
    expired_in_game: list[tuple[uuid.UUID, uuid.UUID]]  # (room_id, guest_id) cần xử thua (D9, R6)


async def sweep_expired_holds(session: AsyncSession, now: datetime | None = None) -> SweepResult:
    """Nhả các ghế mất kết nối quá hạn giữ ghế (ngoài ván). Chạy định kỳ bởi sweeper."""
    now = now or _now()
    room_ids = list(
        await session.scalars(
            select(RoomSeat.room_id)
            .where(RoomSeat.conn_state == "DISCONNECTED", RoomSeat.hold_until <= now)
            .distinct()
        )
    )
    changed: list[uuid.UUID] = []
    closed: list[uuid.UUID] = []
    in_game: list[tuple[uuid.UUID, uuid.UUID]] = []
    for room_id in room_ids:
        room = await _lock_room(session, room_id)
        if room.status != "WAITING":  # đang chơi: chưa nhả ghế, chỉ báo để xử thua; nhả ghế sau khi ván xong
            in_game.extend(
                (room_id, s.guest_id)
                for s in await _seats(session, room_id)
                if s.conn_state == "DISCONNECTED" and s.hold_until and s.hold_until <= now and s.guest_id
            )
            await session.rollback()
            continue
        seats = await _seats(session, room_id)
        expired = [
            s for s in seats if s.conn_state == "DISCONNECTED" and s.hold_until and s.hold_until <= now
        ]
        for seat in expired:
            was_owner = room.owner_guest_id == seat.guest_id
            _release(seat)
            if was_owner:
                _transfer_owner(room, seats, seat.seat_no)
        if expired:
            if all(s.guest_id is None for s in seats):
                _close(room, seats, "EMPTY")
                closed.append(room_id)
            room.state_version += 1
            changed.append(room_id)
        await session.commit()
    return SweepResult(changed, closed, in_game)


async def room_state(session: AsyncSession, room_id: uuid.UUID) -> dict[str, Any]:
    """Trạng thái phòng công khai (không có token, không có guestId của người khác)."""
    room = await session.get(Room, room_id, populate_existing=True)
    if room is None:
        raise AppError(404, "ROOM_NOT_FOUND", "Không tìm thấy phòng")
    rows = await session.execute(
        select(RoomSeat, GuestPlayer.nickname)
        .outerjoin(GuestPlayer, GuestPlayer.id == RoomSeat.guest_id)
        .where(RoomSeat.room_id == room_id)
        .order_by(RoomSeat.seat_no)
        .execution_options(populate_existing=True)
    )
    seats, owner_seat = [], None
    for seat, nickname in rows.all():
        if seat.guest_id is not None and seat.guest_id == room.owner_guest_id:
            owner_seat = seat.seat_no
        seats.append(
            {
                "seatNo": seat.seat_no,
                "occupied": seat.guest_id is not None,
                "nickname": nickname,
                "ready": seat.ready,
                "connected": seat.conn_state == "CONNECTED",
                "holdUntil": seat.hold_until.isoformat() if seat.hold_until else None,
            }
        )
    try:
        active = await rules.get_active(session)
        rules_info: dict[str, Any] | None = {"version": active.version, "configHash": active.config_hash}
    except AppError:
        rules_info = None
    game_id = await session.scalar(
        select(Game.id).where(Game.room_id == room_id, Game.status == "IN_PROGRESS")
    )
    return {
        "roomId": str(room.id),
        "code": room.code,
        "status": room.status,
        "gameId": str(game_id) if game_id else None,
        "version": room.state_version,
        "ownerSeat": owner_seat,
        "seats": seats,
        "playerCount": len(seats),
        "allReady": len(seats) in PLAYER_COUNTS and all(s["ready"] and s["connected"] for s in seats),
        "session": await scores.session_summary(session, room_id),
        "rules": rules_info,
    }

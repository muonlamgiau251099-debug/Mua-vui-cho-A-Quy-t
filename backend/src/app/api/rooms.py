import uuid
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import DbSession, Guest
from app.errors import AppError
from app.realtime.games import GameManager
from app.realtime.hub import CLOSE_LEFT_ROOM, RoomHub
from app.services import rooms

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


class JoinBody(BaseModel):
    seatNo: int | None = Field(default=None, ge=0, le=3)


def _hub(request: Request) -> RoomHub:
    hub: RoomHub = request.app.state.hub
    return hub


def _limit(request: Request, limiter_name: str, key: str, message: str) -> None:
    if not getattr(request.app.state, limiter_name).allow(key):
        raise AppError(429, "RATE_LIMITED", message)


def invite_path(code: str) -> str:
    return f"/r/{code}"


@router.post("", status_code=201)
async def create_room(request: Request, guest: Guest, db: DbSession) -> dict[str, Any]:
    _limit(request, "room_create_limiter", str(guest.id), "Tạo phòng quá nhiều, hãy thử lại sau")
    room = await rooms.create_room(db, guest)
    return {"roomId": str(room.id), "code": room.code, "invitePath": invite_path(room.code), "seatNo": 0}


@router.get("/by-code/{code}")
async def by_code(code: str, request: Request, db: DbSession) -> dict[str, Any]:
    client = request.client.host if request.client else "unknown"
    _limit(request, "room_lookup_limiter", client, "Tra cứu mã phòng quá nhiều, hãy đợi 1 phút")
    room = await rooms.find_open_room(db, code)
    return await rooms.room_state(db, room.id)


@router.post("/{room_id}/join")
async def join(
    room_id: uuid.UUID, body: JoinBody, request: Request, guest: Guest, db: DbSession
) -> dict[str, Any]:
    client = request.client.host if request.client else "unknown"
    _limit(request, "room_lookup_limiter", client, "Vào phòng quá nhiều lần, hãy đợi 1 phút")
    seat = await rooms.join(db, guest, room_id, body.seatNo)
    await _hub(request).broadcast_state(room_id)
    return {"roomId": str(room_id), "seatNo": seat.seat_no}


@router.post("/{room_id}/leave", status_code=204)
async def leave(room_id: uuid.UUID, request: Request, guest: Guest, db: DbSession) -> None:
    games: GameManager = request.app.state.games
    await games.forfeit(room_id, guest.id)  # D9: rời giữa ván = xử thua (không có ván thì không làm gì)
    result = await rooms.leave(db, guest.id, room_id)
    hub = _hub(request)
    await hub.kick(room_id, guest.id, CLOSE_LEFT_ROOM, "Đã rời phòng")
    if result.room_closed:
        await games.cancel(room_id, "ALL_LEFT")
        await hub.close_room(room_id, "EMPTY")
    else:
        await hub.broadcast_state(room_id)


@router.post("/{room_id}/close", status_code=204)
async def close(room_id: uuid.UUID, request: Request, guest: Guest, db: DbSession) -> None:
    await rooms.close_by_owner(db, guest.id, room_id)  # kiểm tra chủ phòng trước (ID 147)
    await request.app.state.games.cancel(room_id, "ROOM_CLOSED")  # Q-P2-3: đóng phòng khi đang chơi → hủy ván
    await _hub(request).close_room(room_id, "OWNER_CLOSED")

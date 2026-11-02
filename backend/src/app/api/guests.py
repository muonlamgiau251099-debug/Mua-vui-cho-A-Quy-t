from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import AppSettings, DbSession, Guest
from app.models import GuestPlayer, Room
from app.services import guests, rooms

router = APIRouter(prefix="/api/guests", tags=["guests"])


class NicknameBody(BaseModel):
    nickname: str = Field(max_length=60)


async def guest_json(db: DbSession, guest: GuestPlayer) -> dict[str, Any]:
    seat = await rooms.seat_of_guest(db, guest.id)
    room = await db.get(Room, seat.room_id) if seat else None
    return {
        "guestId": str(guest.id),
        "nickname": guest.nickname,
        "currentRoom": {"roomId": str(room.id), "code": room.code, "seatNo": seat.seat_no}
        if room and seat
        else None,
    }


@router.post("", status_code=201)
async def create_guest(body: NicknameBody, db: DbSession, settings: AppSettings) -> dict[str, Any]:
    guest, token = await guests.create_guest(db, settings, body.nickname)
    # Token chỉ trả về đúng 1 lần; client lưu để vào lại (reconnect).
    return {**await guest_json(db, guest), "token": token}


@router.get("/me")
async def me(guest: Guest, db: DbSession) -> dict[str, Any]:
    return await guest_json(db, guest)


@router.patch("/me")
async def rename(body: NicknameBody, guest: Guest, db: DbSession) -> dict[str, Any]:
    return await guest_json(db, await guests.rename(db, guest, body.nickname))

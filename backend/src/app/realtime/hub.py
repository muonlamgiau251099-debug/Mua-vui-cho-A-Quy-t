"""Quản lý kết nối WebSocket theo phòng (1 process — ADR-003) và broadcast trạng thái sau khi commit."""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.websockets import WebSocket, WebSocketState

from app.services import rooms

log = logging.getLogger(__name__)

CLOSE_REPLACED = 4409  # guest mở kết nối mới ở tab/thiết bị khác
CLOSE_ROOM_CLOSED = 4000
CLOSE_LEFT_ROOM = 4001


def envelope(
    msg_type: str,
    payload: dict[str, Any],
    *,
    room_id: uuid.UUID | str | None = None,
    sequence: int | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "type": msg_type,
        "requestId": request_id,
        "roomId": str(room_id) if room_id else None,
        "gameId": None,
        "sequence": sequence,
        "payload": payload,
    }


@dataclass(eq=False)
class Connection:
    websocket: WebSocket
    room_id: uuid.UUID
    guest_id: uuid.UUID
    seat_no: int
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, message: dict[str, Any]) -> None:
        async with self.send_lock:
            if self.websocket.application_state == WebSocketState.CONNECTED:
                with contextlib.suppress(Exception):  # client vừa ngắt: bỏ qua, xử lý ở vòng nhận
                    await self.websocket.send_json(message)

    async def close(self, code: int, reason: str = "") -> None:
        if self.websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await self.websocket.close(code=code, reason=reason)


class RoomHub:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._rooms: dict[uuid.UUID, dict[uuid.UUID, Connection]] = {}
        self._background: set[asyncio.Task[None]] = set()

    def spawn(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        """Chạy tác vụ phải hoàn tất kể cả khi task gọi nó bị hủy (giữ tham chiếu để không bị GC)."""
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return task

    def connections(self, room_id: uuid.UUID) -> list[Connection]:
        return list(self._rooms.get(room_id, {}).values())

    async def register(self, conn: Connection) -> None:
        old = self._rooms.setdefault(conn.room_id, {}).get(conn.guest_id)
        self._rooms[conn.room_id][conn.guest_id] = conn
        if old is not None:
            await old.close(CLOSE_REPLACED, "Đã mở phòng ở nơi khác")

    def unregister(self, conn: Connection) -> bool:
        """Gỡ kết nối; trả False nếu kết nối đã bị kết nối mới thay thế."""
        room = self._rooms.get(conn.room_id, {})
        if room.get(conn.guest_id) is not conn:
            return False
        del room[conn.guest_id]
        if not room:
            self._rooms.pop(conn.room_id, None)
        return True

    async def broadcast_state(self, room_id: uuid.UUID) -> None:
        conns = self.connections(room_id)
        if not conns:
            return
        async with self._sessionmaker() as session:
            state = await rooms.room_state(session, room_id)
        for conn in conns:
            payload = {**state, "yourSeat": conn.seat_no}
            await conn.send(envelope("room.state", payload, room_id=room_id, sequence=state["version"]))

    async def send_room_event(self, room_id: uuid.UUID, msg_type: str, payload: dict[str, Any]) -> None:
        for conn in self.connections(room_id):
            await conn.send(envelope(msg_type, payload, room_id=room_id))

    async def close_room(self, room_id: uuid.UUID, reason: str) -> None:
        for conn in self.connections(room_id):
            await conn.send(envelope("room.closed", {"reason": reason}, room_id=room_id))
            await conn.close(CLOSE_ROOM_CLOSED, reason)
        self._rooms.pop(room_id, None)

    async def kick(self, room_id: uuid.UUID, guest_id: uuid.UUID, code: int, reason: str) -> None:
        conn = self._rooms.get(room_id, {}).pop(guest_id, None)
        if conn is not None:
            await conn.close(code, reason)

    async def broadcast_all(self, msg_type: str, payload: dict[str, Any]) -> None:
        for room_id in list(self._rooms):
            await self.send_room_event(room_id, msg_type, payload)

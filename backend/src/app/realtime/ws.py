"""WebSocket /ws/rooms/{roomId} (docs/gd2/04 §2).

- Kiểm tra Origin; message đầu tiên phải là `auth` trong ws_auth_timeout_seconds (đóng 4401 nếu không).
- Token chỉ đi trong message, không nằm trên URL (ADR-013).
- Mỗi lệnh có `requestId`; gửi lại cùng requestId → nhận lại đúng phản hồi cũ.
"""

import asyncio
import contextlib
import json
import logging
import math
import time
import uuid
from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import Settings
from app.errors import AppError
from app.realtime.chat import CHAT_MAX_LENGTH, CHAT_PHRASES, normalize_chat_text
from app.realtime.hub import Connection, RoomHub, envelope
from app.security import SlidingWindowLimiter
from app.services import guests, rooms

log = logging.getLogger(__name__)
router = APIRouter()

CLOSE_UNAUTHORIZED = 4401
CLOSE_AUTH_TIMEOUT = 4408  # không nhận được message auth kịp: client nên tự kết nối lại
CLOSE_FORBIDDEN = 4403
CLOSE_TOO_MANY = 4429
_DEDUP_SIZE = 200
_MAX_RATE_STRIKES = 20


class ProtocolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_message(raw: str, max_bytes: int) -> dict[str, Any]:
    if len(raw.encode("utf-8")) > max_bytes:
        raise ProtocolError("PAYLOAD_TOO_LARGE", "Gói tin quá lớn")
    try:
        data = json.loads(raw)
    except ValueError:
        raise ProtocolError("PAYLOAD_INVALID", "Gói tin không phải JSON") from None
    if not isinstance(data, dict) or not isinstance(data.get("type"), str):
        raise ProtocolError("PAYLOAD_INVALID", "Thiếu trường type")
    request_id = data.get("requestId")
    try:
        uuid.UUID(str(request_id), version=4)
    except ValueError:
        raise ProtocolError("PAYLOAD_INVALID", "requestId phải là UUID v4") from None
    if not isinstance(data.get("payload", {}), dict):
        raise ProtocolError("PAYLOAD_INVALID", "payload phải là object")
    return data


def _origin_allowed(websocket: WebSocket, settings: Settings) -> bool:
    origin = websocket.headers.get("origin")
    return (
        origin is None or origin in settings.allowed_origins
    )  # client không phải trình duyệt: không có Origin


@router.websocket("/ws/rooms/{room_id}")
async def room_socket(websocket: WebSocket, room_id: uuid.UUID) -> None:
    app = websocket.app
    settings: Settings = app.state.settings
    hub: RoomHub = app.state.hub
    if not _origin_allowed(websocket, settings):
        await websocket.close(code=CLOSE_FORBIDDEN)
        return
    await websocket.accept()

    conn = await _authenticate(websocket, room_id, settings, app.state.sessionmaker)
    if conn is None:
        return
    await hub.register(conn)
    await hub.broadcast_state(room_id)
    await app.state.games.send_snapshot(conn)  # ID 143: đang có ván → gửi lại bài của chính người này

    limiter = SlidingWindowLimiter(settings.ws_max_messages_per_second, 1.0, time.monotonic)
    handled: OrderedDict[str, dict[str, Any]] = OrderedDict()
    strikes = 0
    try:
        while True:
            raw = await websocket.receive_text()
            if not limiter.allow("conn"):
                strikes += 1
                await conn.send(envelope("error", {"code": "RATE_LIMITED", "message": "Gửi quá nhanh"}))
                if strikes >= _MAX_RATE_STRIKES:
                    await conn.close(CLOSE_TOO_MANY, "Gửi quá nhanh")
                    break
                continue
            try:
                message = parse_message(raw, settings.ws_max_frame_bytes)
            except ProtocolError as exc:
                await conn.send(envelope("error", {"code": exc.code, "message": exc.message}))
                continue
            request_id = str(message["requestId"])
            if request_id in handled:  # gửi lặp: trả lại đúng phản hồi cũ, không xử lý lại
                await conn.send(handled[request_id])
                continue
            response, sent = await _dispatch(app, conn, message)
            handled[request_id] = response
            if len(handled) > _DEDUP_SIZE:
                handled.popitem(last=False)
            if not sent:
                await conn.send(response)
    except WebSocketDisconnect:
        pass
    finally:
        if hub.unregister(conn):
            # Task WebSocket có thể đang bị hủy (client ngắt, server tắt):
            # việc cập nhật ghế vẫn phải chạy xong.
            await asyncio.shield(hub.spawn(_on_disconnect(app, room_id, conn.guest_id)))


async def _on_disconnect(app: Any, room_id: uuid.UUID, guest_id: uuid.UUID) -> None:
    async with app.state.sessionmaker() as session:
        changed = await rooms.set_disconnected(session, room_id, guest_id)
    if changed:
        await app.state.hub.broadcast_state(room_id)


async def _authenticate(
    websocket: WebSocket, room_id: uuid.UUID, settings: Settings, sessionmaker: Any
) -> Connection | None:
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=settings.ws_auth_timeout_seconds)
        message = parse_message(raw, settings.ws_max_frame_bytes)
        if message["type"] != "auth":
            raise ProtocolError("UNAUTHORIZED", "Message đầu tiên phải là auth")
        async with sessionmaker() as session:
            guest = await guests.authenticate_guest(
                session, settings, message.get("payload", {}).get("token")
            )
            seat_no = await rooms.set_connected(session, room_id, guest.id)
    except (TimeoutError, WebSocketDisconnect):
        await _close_quietly(websocket, CLOSE_AUTH_TIMEOUT)
        return None
    except (ProtocolError, AppError) as exc:
        code = exc.code
        close_code = CLOSE_FORBIDDEN if code == "NOT_IN_ROOM" else CLOSE_UNAUTHORIZED
        await websocket.send_json(envelope("error", {"code": code, "message": exc.message}))
        await _close_quietly(websocket, close_code)
        return None
    conn = Connection(websocket, room_id, guest.id, seat_no)
    await conn.send(
        envelope(
            "ack",
            {"type": "auth", "seatNo": seat_no, "nickname": guest.nickname, "serverTime": time.time()},
            room_id=room_id,
            request_id=str(message["requestId"]),
        )
    )
    return conn


async def _close_quietly(websocket: WebSocket, code: int) -> None:
    with contextlib.suppress(RuntimeError):  # socket đã đóng
        await websocket.close(code=code)


async def _dispatch(app: Any, conn: Connection, message: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    request_id = str(message["requestId"])
    msg_type = message["type"]
    payload = message.get("payload", {})
    hub: RoomHub = app.state.hub
    try:
        if msg_type == "ping":
            return envelope(
                "pong", {"serverTime": time.time()}, room_id=conn.room_id, request_id=request_id
            ), False
        if msg_type == "chat.send":
            # Gửi đúng một trong hai: {"phrase": mã câu có sẵn} hoặc {"text": chữ tự do}.
            chat: dict[str, Any]
            if ("phrase" in payload) == ("text" in payload):
                raise ProtocolError("PAYLOAD_INVALID", "Chat phải gửi phrase hoặc text")
            if "phrase" in payload:
                phrase = payload["phrase"]
                if not isinstance(phrase, str) or phrase not in CHAT_PHRASES:
                    raise ProtocolError("PAYLOAD_INVALID", "Câu chat không hợp lệ")
                chat = {"phrase": phrase}
            else:
                text = normalize_chat_text(payload["text"])
                if text is None:
                    raise ProtocolError("PAYLOAD_INVALID", f"Tin nhắn phải từ 1 đến {CHAT_MAX_LENGTH} ký tự")
                chat = {"text": text}
            wait = app.state.chat_cooldown.check((conn.room_id, conn.guest_id))  # chỉ tính khi tin hợp lệ
            if wait > 0:
                raise ProtocolError("CHAT_COOLDOWN", f"Chờ {math.ceil(wait)} giây nữa mới chat tiếp được")
            await hub.send_room_event(conn.room_id, "chat.message", {"seat": conn.seat_no, **chat})
            return envelope("ack", {"type": msg_type}, room_id=conn.room_id, request_id=request_id), False
        if msg_type in ("game.play", "game.pass"):
            result: tuple[dict[str, Any], bool] = await app.state.games.handle_command(
                conn, msg_type, payload, request_id, message.get("sequence")
            )
            return result
        if msg_type == "room.ready":
            ready = payload.get("ready")
            if not isinstance(ready, bool):
                raise ProtocolError("PAYLOAD_INVALID", "ready phải là true/false")
            async with app.state.sessionmaker() as session:
                all_ready = await rooms.set_ready(session, conn.room_id, conn.guest_id, ready)
            await hub.broadcast_state(conn.room_id)
            ack = envelope("ack", {"type": msg_type}, room_id=conn.room_id, request_id=request_id)
            if all_ready:  # ID 140: đủ 4 người sẵn sàng → server chia bài, bắt đầu ván
                await conn.send(ack)
                await hub.send_room_event(conn.room_id, "room.allReady", {})
                await app.state.games.start_if_ready(conn.room_id)
                return ack, True
            return ack, False
        raise ProtocolError("UNKNOWN_TYPE", f"Không hỗ trợ message {msg_type}")
    except (ProtocolError, AppError) as exc:
        error = envelope(
            "error", {"code": exc.code, "message": exc.message}, room_id=conn.room_id, request_id=request_id
        )
        return error, False

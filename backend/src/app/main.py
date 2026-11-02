"""Render Free entrypoint: one ASGI process, same-origin SPA + REST + WebSocket."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
import uuid
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.errors import AppError, install_error_handlers
from app.http_security import SECURITY_HEADERS
from app.memory import MAX_PLAYERS, MemoryStore, envelope, nickname
from tlmn_engine.catalog import raw_catalog
from tlmn_engine.rules_config import GROUP_LABELS, INVARIANTS, SCHEMA_VERSION, field_specs


class NicknameBody(BaseModel):
    nickname: str = Field(max_length=60)


class JoinBody(BaseModel):
    seatNo: int | None = Field(default=None, ge=0, le=3)


class RateLimits:
    """Bounded IP buckets, no request bodies or credentials in logs."""

    def __init__(self):
        self.hits = OrderedDict()

    def allow(self, key, limit, window=60):
        now = time.monotonic()
        hits = self.hits.setdefault(key, deque())
        self.hits.move_to_end(key)
        while hits and hits[0] < now - window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        while len(self.hits) > 2000:
            self.hits.popitem(last=False)
        return True


def parse_message(raw: str) -> dict:
    if len(raw.encode()) > 4096:
        raise AppError(413, "PAYLOAD_TOO_LARGE", "Gói tin quá lớn")
    try:
        msg = json.loads(raw)
        if not isinstance(msg, dict) or not isinstance(msg.get("type"), str):
            raise ValueError()
        req = uuid.UUID(msg.get("requestId", ""))
        if req.version != 4 or not isinstance(msg.get("payload", {}), dict):
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise AppError(
            422, "PAYLOAD_INVALID", "Gói tin JSON phải có type, UUID v4 requestId và payload object"
        ) from None
    return msg


def origin_allowed(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if origin is None:
        return True  # native clients use the same token authentication
    try:
        parsed = urlsplit(origin)
        return (
            parsed.scheme in ("https", "http")
            and parsed.netloc == ws.headers.get("host")
            and not parsed.username
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False


def create_app(store: MemoryStore | None = None, static_dir: str | Path | None = None) -> FastAPI:
    store = store or MemoryStore()
    limits = RateLimits()

    @asynccontextmanager
    async def lifespan(app):
        async def sweep():
            while True:
                await asyncio.sleep(0.5)
                await store.tick()

        task = asyncio.create_task(sweep())
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        async with store.lock:
            for room in list(store.rooms.values()):
                await store.close_room(room, "SERVER_RESTART")

    app = FastAPI(
        title="Tiến Lên Miền Nam", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.store = store
    install_error_handlers(app)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # Rate-limit before reading JSON bodies, and bound chunked request bodies too.
        client = request.client.host if request.client else "unknown"
        if request.url.path.startswith("/api/"):
            key = ("http", client)
            if not limits.allow(key, 240):
                return JSONResponse({"code": "RATE_LIMITED", "title": "Gửi quá nhanh, hãy đợi 1 phút"}, 429)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 65536:
                    return JSONResponse({"code": "PAYLOAD_TOO_LARGE", "title": "Dữ liệu quá lớn"}, 413)
            request._body = bytes(body)
        async with store.lock:
            await store.reset_if_due()
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def auth(request: Request):
        value = request.headers.get("authorization", "")
        return store.authenticate(value[7:] if value.startswith("Bearer ") else None)

    @app.get("/api/health")
    async def health():
        return dict(
            status="ok",
            storage="memory",
            maxPlayers=MAX_PLAYERS,
            seatedPlayers=sum(s.guest is not None for r in store.rooms.values() for s in r.seats),
            rooms=len(store.rooms),
            liveGames=sum(r.live is not None for r in store.rooms.values()),
            resetTimezone="Asia/Tokyo",
            day=store.day,
            resetPendingRooms=sum(r.pending_reset for r in store.rooms.values()),
        )

    @app.post("/api/guests", status_code=201)
    async def create_guest(body: NicknameBody, request: Request):
        client = request.client.host if request.client else "unknown"
        if not limits.allow(("guests", client), 60):
            raise AppError(429, "RATE_LIMITED", "Tạo quá nhiều phiên, hãy thử lại sau")
        async with store.lock:
            guest, token = store.create_guest(body.nickname)
            return {**store.profile(guest), "token": token}

    @app.get("/api/guests/me")
    async def me(request: Request):
        async with store.lock:
            return store.profile(auth(request))

    @app.patch("/api/guests/me")
    async def rename(body: NicknameBody, request: Request):
        async with store.lock:
            guest = auth(request)
            guest.name = nickname(body.nickname)
            seated = store.seat_of(guest.id)
            if seated:
                seated[0].version += 1
                await store.broadcast_state(seated[0])
            return store.profile(guest)

    @app.post("/api/rooms", status_code=201)
    async def create_room(request: Request):
        async with store.lock:
            guest = auth(request)
            if not limits.allow(("room", guest.id), 10, 3600):
                raise AppError(429, "RATE_LIMITED", "Tạo phòng quá nhiều, hãy thử lại sau")
            room = store.create_room(guest)
            return dict(roomId=room.id, code=room.code, invitePath=f"/r/{room.code}", seatNo=0)

    @app.get("/api/rooms/by-code/{code}")
    async def room_by_code(code: str, request: Request):
        client = request.client.host if request.client else "unknown"
        if not limits.allow(("lookup", client), 60):
            raise AppError(429, "RATE_LIMITED", "Tra cứu quá nhanh, hãy đợi 1 phút")
        async with store.lock:
            room = next((r for r in store.rooms.values() if r.code == code.strip().upper()), None)
            if room is None:
                raise AppError(404, "ROOM_NOT_FOUND", "Không tìm thấy phòng với mã này")
            return store.room_state(room)

    @app.post("/api/rooms/{room_id}/join")
    async def join(room_id: uuid.UUID, body: JoinBody, request: Request):
        async with store.lock:
            guest = auth(request)
            room = store.get_room(str(room_id))
            seat = store.join(room, guest, body.seatNo)
            await store.broadcast_state(room)
            return dict(roomId=room.id, seatNo=seat)

    @app.post("/api/rooms/{room_id}/leave", status_code=204)
    async def leave(room_id: uuid.UUID, request: Request):
        async with store.lock:
            guest = auth(request)
            room = store.get_room(str(room_id))
            await store.release(room, store.member(room, guest))
        return Response(status_code=204)

    @app.post("/api/rooms/{room_id}/close", status_code=204)
    async def close(room_id: uuid.UUID, request: Request):
        async with store.lock:
            guest = auth(request)
            room = store.get_room(str(room_id))
            if room.owner != guest.id:
                raise AppError(403, "NOT_OWNER", "Chỉ chủ phòng được đóng phòng")
            await store.close_room(room, "OWNER_CLOSED")
        return Response(status_code=204)

    @app.post("/api/rooms/{room_id}/sessions/restart", status_code=204)
    async def restart_session(room_id: uuid.UUID, request: Request):
        async with store.lock:
            guest = auth(request)
            room = store.get_room(str(room_id))
            if room.owner != guest.id:
                raise AppError(403, "NOT_OWNER", "Chỉ chủ phòng được khởi động lại phiên")
            if room.live or room.pending_reset:
                raise AppError(409, "GAME_IN_PROGRESS", "Chỉ khởi động lại phiên giữa các ván")
            session = store.sessions.get(room.session_id)
            if session:
                from app.memory import now_iso

                session.update(status="ENDED", endReason="RESTARTED", endedAt=now_iso())
            room.session_id = None
            room.version += 1
            await store.broadcast(room, "session.restarted", {})
            await store.broadcast_state(room)
        return Response(status_code=204)

    @app.get("/api/guests/me/sessions")
    async def sessions(request: Request):
        async with store.lock:
            guest = auth(request)
            return dict(
                items=[
                    store.session_json(s)
                    for s in reversed(store.sessions.values())
                    if guest.id in s["roster"]
                ][:30]
            )

    @app.get("/api/rooms/{room_id}/sessions")
    async def room_sessions(room_id: uuid.UUID, request: Request):
        async with store.lock:
            guest = auth(request)
            return dict(
                items=[
                    store.session_json(s)
                    for s in reversed(store.sessions.values())
                    if s["room"] == str(room_id) and guest.id in s["roster"]
                ][:30]
            )

    @app.get("/api/sessions/{session_id}")
    async def session_detail(session_id: uuid.UUID, request: Request):
        async with store.lock:
            guest = auth(request)
            session = store.sessions.get(str(session_id))
            if session is None or guest.id not in session["roster"]:
                raise AppError(404, "SESSION_NOT_FOUND", "Không tìm thấy phiên chơi")
            return store.session_json(session, detail=True)

    @app.get("/api/games/{game_id}/replay")
    async def replay(game_id: uuid.UUID, request: Request):
        async with store.lock:
            return store.replay(str(game_id), auth(request))

    @app.get("/api/rules/active")
    @app.get("/api/rules/versions/{version}")
    async def active_rules(version: int = 1):
        if version != 1:
            raise AppError(404, "VERSION_NOT_FOUND", "Không có phiên bản luật này")
        return dict(
            version=1,
            configHash=store.rules_hash,
            config=store.rules.model_dump(mode="json"),
            publishedAt=None,
        )

    @app.get("/api/rules/catalog")
    async def catalog():
        return raw_catalog()

    @app.get("/api/rules/schema")
    async def schema():
        return dict(
            schemaVersion=SCHEMA_VERSION,
            groups=[dict(key=k, label=v) for k, v in GROUP_LABELS.items()],
            fields=[s.to_json() for s in field_specs()],
            invariants=INVARIANTS,
        )

    @app.websocket("/ws/rooms/{room_id}")
    async def socket(ws: WebSocket, room_id: uuid.UUID):
        client = ws.client.host if ws.client else "unknown"
        if not origin_allowed(ws):
            await ws.close(code=4403)
            return
        if not limits.allow(("ws", client), 120):
            await ws.close(code=4429)
            return
        await ws.accept()
        room = guest = None
        try:
            msg = parse_message(await asyncio.wait_for(ws.receive_text(), 5))
            if msg["type"] != "auth":
                raise AppError(401, "GUEST_UNAUTHORIZED", "Message đầu tiên phải là auth")
            async with store.lock:
                await store.reset_if_due()
                guest = store.authenticate(msg.get("payload", {}).get("token"))
                room = store.get_room(str(room_id))
                seat = store.member(room, guest)
                old = room.conns.get(guest.id)
                room.conns[guest.id] = ws
                if old is not None:
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(old.close(code=4409), 0.5)
                room.seats[seat].connected = True
                room.seats[seat].hold_until = None
                room.version += 1
                await store.send(
                    ws,
                    envelope(
                        "ack",
                        dict(type="auth", seatNo=seat, nickname=guest.name, serverTime=store.clock()),
                        room.id,
                        request_id=msg["requestId"],
                    ),
                )
                await store.broadcast_state(room)
                if room.live:
                    game = room.live
                    from tlmn_engine.projection import project_private

                    await store.send(
                        ws,
                        envelope(
                            "game.state",
                            {
                                **store.header(game),
                                "events": [],
                                "state": project_private(game["state"], seat),
                            },
                            room.id,
                            game["state"].seq,
                        ),
                    )
            hits = deque()
            strikes = 0
            while True:
                raw = await ws.receive_text()
                now = time.monotonic()
                while hits and hits[0] < now - 1:
                    hits.popleft()
                hits.append(now)
                if len(hits) > 10:
                    strikes += 1
                    await store.send(
                        ws, envelope("error", dict(code="RATE_LIMITED", message="Gửi quá nhanh"))
                    )
                    if strikes >= 20:
                        await ws.close(code=4429)
                        break
                    continue
                try:
                    msg = parse_message(raw)
                    async with store.lock:
                        await store.reset_if_due()
                        if room.id not in store.rooms or room.conns.get(guest.id) is not ws:
                            break
                        guest.last_seen = store.clock()
                        response = await store.dispatch(room, guest, ws, msg)
                        if response is not None:
                            await store.send(ws, response)
                except AppError as exc:
                    await store.send(ws, envelope("error", dict(code=exc.code, message=exc.message)))
        except (TimeoutError, WebSocketDisconnect, RuntimeError):
            pass
        except AppError as exc:
            await store.send(ws, envelope("error", dict(code=exc.code, message=exc.message)))
            with contextlib.suppress(Exception):
                await ws.close(code=4403 if exc.code == "NOT_IN_ROOM" else 4401)
        finally:
            if guest and room:
                async with store.lock:
                    if room.id in store.rooms and room.conns.get(guest.id) is ws:
                        room.conns.pop(guest.id)
                        seat = store.member(room, guest)
                        s = room.seats[seat]
                        s.connected, s.ready = False, False
                        s.hold_until = store.clock() + 120
                        room.version += 1
                        await store.broadcast_state(room)

    root = Path(static_dir or os.getenv("STATIC_DIR", "frontend/dist")).resolve()
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        if path.startswith(("api/", "ws/")):
            raise AppError(404, "NOT_FOUND", "Không tìm thấy đường dẫn")
        # Serve only compiled assets and the SPA, never arbitrary source/.env files.
        if path and "." in path.rsplit("/", 1)[-1]:
            raise AppError(404, "NOT_FOUND", "Không tìm thấy file")
        if not (root / "index.html").is_file():
            raise AppError(503, "FRONTEND_NOT_BUILT", "Frontend chưa build")
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()

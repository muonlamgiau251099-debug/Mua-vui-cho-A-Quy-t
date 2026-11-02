"""Lịch sử phiên và điểm (ID 129–131, 148, 150). Chỉ người chơi trong phiên được xem."""

import uuid
from typing import Any

from fastapi import APIRouter, Request

from app.api.deps import DbSession, Guest
from app.realtime.hub import RoomHub
from app.services import replay, scores

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/guests/me/sessions")
async def my_sessions(guest: Guest, db: DbSession) -> dict[str, Any]:
    return {"items": await scores.list_sessions(db, guest.id)}


@router.get("/rooms/{room_id}/sessions")
async def room_sessions(room_id: uuid.UUID, guest: Guest, db: DbSession) -> dict[str, Any]:
    return {"items": await scores.list_sessions(db, guest.id, room_id)}


@router.get("/sessions/{session_id}")
async def session_detail(session_id: uuid.UUID, guest: Guest, db: DbSession) -> dict[str, Any]:
    return await scores.session_detail(db, guest.id, session_id)


@router.post("/rooms/{room_id}/sessions/restart", status_code=204)
async def restart_session(room_id: uuid.UUID, request: Request, guest: Guest, db: DbSession) -> None:
    await scores.restart_session(db, guest.id, room_id)
    hub: RoomHub = request.app.state.hub
    await hub.send_room_event(room_id, "session.restarted", {})
    await hub.broadcast_state(room_id)


@router.get("/games/{game_id}/replay")
async def game_replay(game_id: uuid.UUID, guest: Guest, db: DbSession) -> dict[str, Any]:
    """ID 154: xem lại từng bước — chỉ người chơi của ván, chỉ sau khi ván kết thúc."""
    return await replay.replay_for_player(db, guest.id, game_id)

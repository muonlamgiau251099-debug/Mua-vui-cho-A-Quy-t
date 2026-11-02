"""Admin hủy ván đang chơi (ID 109, Q-P1-9): điểm của ván bị loại, thao tác được ghi audit."""

import uuid
from typing import Any

from fastapi import APIRouter, Request

from app.api.deps import AdminRead, AdminWrite, DbSession, Meta
from app.errors import AppError
from app.realtime.games import GameManager
from app.services import replay
from app.services.audit import add_audit

router = APIRouter(prefix="/api/admin/games", tags=["admin-games"])


@router.post("/{game_id}/cancel", status_code=204)
async def cancel_game(
    game_id: uuid.UUID, request: Request, ctx: AdminWrite, db: DbSession, meta: Meta
) -> None:
    games: GameManager = request.app.state.games
    room_id = games.room_of_game(game_id)
    if room_id is None or not await games.cancel(room_id, "ADMIN"):
        raise AppError(404, "GAME_NOT_ACTIVE", "Không có ván đang chơi với mã này")
    add_audit(
        db,
        meta,
        "CANCEL_GAME",
        admin_id=ctx.admin.id,
        detail={"gameId": str(game_id), "roomId": str(room_id)},
    )
    await db.commit()


@router.get("/{game_id}/audit")
async def game_audit(game_id: uuid.UUID, ctx: AdminRead, db: DbSession, meta: Meta) -> dict[str, Any]:
    """ID 155: dữ liệu đối soát tranh chấp. Việc Admin xem log ván cũng được ghi audit."""
    data = await replay.audit_for_admin(db, game_id)
    add_audit(db, meta, "VIEW_GAME_AUDIT", admin_id=ctx.admin.id, detail={"gameId": str(game_id)})
    await db.commit()
    return data

"""Sổ điểm bền vững và lịch sử phiên (ID 111, 129–133, 148, 150; docs/gd2/01 §3.2, 03 §7).

- Ghi kết quả ván FINISHED trong CÙNG transaction với event kết thúc ván (gọi từ GameManager).
- game_results.game_id là khóa chính → một ván không thể được cộng điểm hai lần.
- Ván CANCELLED không ghi điểm (Q-P1-9).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import Game, GameResult, GameSession, GuestPlayer, Room, ScoreTransfer, SessionScore
from tlmn_engine.state import GameState


async def record_game_result(s: AsyncSession, game: Game, state: GameState, roster: list[uuid.UUID]) -> None:
    if game.status != "FINISHED":
        return
    net = state.net()
    assert sum(net) == 0, "Tổng điểm ván phải bằng 0"  # ID 133
    s.add(
        GameResult(
            game_id=game.id,
            session_id=game.session_id,
            end_type=game.end_type or "NORMAL",
            ranks=[p.rank for p in state.players],
            statuses=[p.status.value for p in state.players],
            net=net,
        )
    )
    for line_no, t in enumerate(state.transfers, start=1):
        s.add(
            ScoreTransfer(
                game_id=game.id,
                session_id=game.session_id,
                line_no=line_no,
                from_seat=t.from_seat,
                to_seat=t.to_seat,
                from_guest=roster[t.from_seat],
                to_guest=roster[t.to_seat],
                amount=t.amount,
                reason=t.reason,
                detail=t.detail,
            )
        )
    for seat, guest_id in enumerate(roster):
        stmt = insert(SessionScore).values(
            session_id=game.session_id, guest_id=guest_id, seat=seat, total=net[seat], games_counted=1
        )
        await s.execute(
            stmt.on_conflict_do_update(
                index_elements=[SessionScore.session_id, SessionScore.guest_id],
                set_={
                    "total": SessionScore.total + stmt.excluded.total,
                    "games_counted": SessionScore.games_counted + 1,
                    "updated_at": func.now(),
                },
            )
        )


async def session_summary(s: AsyncSession, room_id: uuid.UUID) -> dict[str, Any] | None:
    """Bảng điểm phiên đang mở của phòng, hiển thị trong phòng chờ / bàn chơi."""
    session = await s.scalar(
        select(GameSession).where(GameSession.room_id == room_id, GameSession.status == "ACTIVE")
    )
    if session is None:
        return None
    totals = {
        str(row.guest_id): (row.total, row.games_counted)
        for row in await s.scalars(select(SessionScore).where(SessionScore.session_id == session.id))
    }
    names = await _nicknames(s, session.roster)
    return {
        "sessionId": str(session.id),
        "sessionNo": session.session_no,
        "gamesPlayed": max((g for _, g in totals.values()), default=0),
        "scores": [
            {
                "seat": seat,
                "nickname": names.get(gid),
                "total": totals.get(gid, (0, 0))[0],
            }  # ID 111: bắt đầu từ 0
            for seat, gid in enumerate(session.roster)
        ],
    }


async def _nicknames(s: AsyncSession, guest_ids: list[str]) -> dict[str, str]:
    rows = await s.execute(
        select(GuestPlayer.id, GuestPlayer.nickname).where(
            GuestPlayer.id.in_([uuid.UUID(g) for g in guest_ids])
        )
    )
    return {str(gid): name for gid, name in rows.all()}


async def restart_session(s: AsyncSession, guest_id: uuid.UUID, room_id: uuid.UUID) -> None:
    """ID 148, 129: chủ phòng khởi động lại phiên giữa các ván → ván sau bắt đầu phiên mới, điểm về 0."""
    room = await s.scalar(select(Room).where(Room.id == room_id).with_for_update())
    if room is None or room.status == "CLOSED":
        raise AppError(404, "ROOM_NOT_FOUND", "Không tìm thấy phòng")
    if room.owner_guest_id != guest_id:
        raise AppError(403, "NOT_OWNER", "Chỉ chủ phòng được khởi động lại phiên")
    if room.status != "WAITING":
        raise AppError(409, "GAME_IN_PROGRESS", "Chỉ khởi động lại phiên giữa các ván")
    session = await s.scalar(
        select(GameSession).where(GameSession.room_id == room_id, GameSession.status == "ACTIVE")
    )
    if session is None:
        raise AppError(409, "NO_SESSION", "Phòng chưa có phiên chơi nào")
    session.status, session.end_reason, session.ended_at = "ENDED", "RESTARTED", datetime.now(UTC)
    room.state_version += 1
    await s.commit()


def _standings(
    roster: list[str], names: dict[str, str], totals: dict[str, tuple[int, int]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {
            "seat": seat,
            "nickname": names.get(gid),
            "total": totals.get(gid, (0, 0))[0],
            "gamesCounted": totals.get(gid, (0, 0))[1],
        }
        for seat, gid in enumerate(roster)
    ]
    rows.sort(key=lambda r: (-r["total"], r["seat"]))  # ID 130: xếp hạng theo điểm tích lũy
    for place, row in enumerate(rows, start=1):
        row["place"] = place
    return rows


async def _session_totals(s: AsyncSession, session_id: uuid.UUID) -> dict[str, tuple[int, int]]:
    rows = await s.scalars(select(SessionScore).where(SessionScore.session_id == session_id))
    return {str(r.guest_id): (r.total, r.games_counted) for r in rows}


async def list_sessions(
    s: AsyncSession, guest_id: uuid.UUID, room_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    """Các phiên mà guest này là thành viên (quyền đọc lịch sử: chỉ người chơi trong phiên)."""
    stmt = (
        select(GameSession, Room.code)
        .join(Room, Room.id == GameSession.room_id)
        .where(GameSession.roster.contains([str(guest_id)]))
        .order_by(GameSession.started_at.desc())
        .limit(30)
    )
    if room_id is not None:
        stmt = stmt.where(GameSession.room_id == room_id)
    out = []
    for session, code in (await s.execute(stmt)).all():
        names = await _nicknames(s, session.roster)
        totals = await _session_totals(s, session.id)
        out.append(
            {
                "sessionId": str(session.id),
                "roomCode": code,
                "sessionNo": session.session_no,
                "status": session.status,
                "startedAt": session.started_at.isoformat(),
                "endedAt": session.ended_at.isoformat() if session.ended_at else None,
                "gamesPlayed": max((g for _, g in totals.values()), default=0),
                "standings": _standings(session.roster, names, totals),
            }
        )
    return out


async def session_detail(s: AsyncSession, guest_id: uuid.UUID, session_id: uuid.UUID) -> dict[str, Any]:
    """ID 130, 131, 150: tổng kết phiên + biến động điểm từng ván + chi tiết từng khoản."""
    row = (
        await s.execute(
            select(GameSession, Room.code)
            .join(Room, Room.id == GameSession.room_id)
            .where(GameSession.id == session_id)
        )
    ).first()
    if row is None or str(guest_id) not in row[0].roster:
        raise AppError(404, "SESSION_NOT_FOUND", "Không tìm thấy phiên chơi")  # không lộ phiên của người khác
    session, code = row
    names = await _nicknames(s, session.roster)
    totals = await _session_totals(s, session.id)

    games = list(await s.scalars(select(Game).where(Game.session_id == session.id).order_by(Game.game_no)))
    results = {
        r.game_id: r for r in await s.scalars(select(GameResult).where(GameResult.session_id == session.id))
    }
    transfers: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for t in await s.scalars(
        select(ScoreTransfer).where(ScoreTransfer.session_id == session.id).order_by(ScoreTransfer.line_no)
    ):
        transfers.setdefault(t.game_id, []).append(
            {"from": t.from_seat, "to": t.to_seat, "amount": t.amount, "reason": t.reason, "detail": t.detail}
        )

    cumulative = [0] * len(session.roster)
    game_rows = []
    for g in games:
        result = results.get(g.id)
        if result is not None:
            cumulative = [c + n for c, n in zip(cumulative, result.net, strict=True)]
        game_rows.append(
            {
                "gameId": str(g.id),
                "gameNo": g.game_no,
                "status": g.status,
                "endType": g.end_type,
                "cancelReason": g.cancel_reason,
                "ruleVersion": g.rule_version,
                "startedAt": g.started_at.isoformat(),
                "endedAt": g.ended_at.isoformat() if g.ended_at else None,
                "ranks": result.ranks if result else None,
                "statuses": result.statuses if result else None,
                "net": result.net if result else None,  # ván hủy: không tính điểm
                "cumulative": list(cumulative) if result else None,
                "transfers": transfers.get(g.id, []),
            }
        )
    return {
        "sessionId": str(session.id),
        "roomCode": code,
        "sessionNo": session.session_no,
        "status": session.status,
        "endReason": session.end_reason,
        "startedAt": session.started_at.isoformat(),
        "endedAt": session.ended_at.isoformat() if session.ended_at else None,
        "players": [{"seat": seat, "nickname": names.get(gid)} for seat, gid in enumerate(session.roster)],
        "standings": _standings(session.roster, names, totals),
        "games": game_rows,
    }

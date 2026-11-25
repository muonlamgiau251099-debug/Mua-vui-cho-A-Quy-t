"""Khôi phục ván sau khi server khởi động lại, xem lại ván, đối soát tranh chấp (slice S6)."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import Select, select, update
from starlette.testclient import TestClient

from app.config import Settings
from app.db import make_engine, make_sessionmaker
from app.main import create_app
from app.models import Game, GameResult, RoomSeat, RuleAuditLog
from tests.game_support import (
    DECK,
    HANDS,
    Table,
    bearer,
    finish_by_timeouts,
    of_type,
    recv_until,
    rid,
    started_table,
)
from tests.support import ADMIN_PASSWORD, ADMIN_USER
from tlmn_engine.cards import THREE_CLUBS


@pytest.fixture
def table(ws_app: FastAPI) -> Iterator[Table]:
    with started_table(ws_app) as t:
        yield t


def start_and_play_two_moves(ws_app: FastAPI) -> tuple[str, list[str], str]:
    """Bắt đầu ván, đánh 3♣ và bỏ lượt, rồi "tắt server" (thoát TestClient).

    Trả về room_id, token của 4 người và state hash đã lưu.
    """
    with started_table(ws_app) as t:
        t.send(0, "game.play", {"cards": [THREE_CLUBS]}, 0)
        t.send(1, "game.pass", {}, 1)
        live = t.games.live(uuid.UUID(t.room_id))
        assert live.state.seq == 2
        ((stored_hash,),) = t.db(select(Game.state_hash))
        return t.room_id, list(t.tokens), stored_hash


@pytest.mark.rule(143, 149)
def test_server_restart_recovers_game_and_players_continue(ws_app: FastAPI, settings: Settings) -> None:
    room_id, tokens, _ = start_and_play_two_moves(ws_app)
    restarted = create_app(settings)  # "server khởi động lại" trên cùng DB
    restarted.state.games.deck_source = lambda: list(DECK)
    with TestClient(restarted) as tc:
        live = restarted.state.games.live(uuid.UUID(room_id))
        assert live is not None, "Ván phải được khôi phục"
        assert live.state.seq == 3  # 2 nước đi + RESUME (cấp lại thời gian lượt — G5)
        assert live.state.current == 2
        assert live.state.players[0].hand == [c for c in HANDS[0] if c != THREE_CLUBS]
        code = tc.get("/api/guests/me", headers=bearer(tokens[2])).json()["currentRoom"]["code"]
        seats = tc.get(f"/api/rooms/by-code/{code}").json()["seats"]
        assert not any(s["connected"] for s in seats)  # mọi người phải kết nối lại, ghế vẫn được giữ
        assert all(s["holdUntil"] for s in seats)

        with tc.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.send_json({"type": "auth", "requestId": rid(), "payload": {"token": tokens[2]}})
            snapshot = recv_until(ws, of_type("game.state"))
            assert snapshot["payload"]["state"]["yourHand"] == HANDS[2]
            assert snapshot["sequence"] == 3
            ws.send_json({"type": "game.pass", "requestId": rid(), "sequence": 3, "payload": {}})
            assert recv_until(ws, lambda m: m["type"] in ("ack", "error"))["type"] == "ack"  # chơi tiếp được


def run_sql(settings: Settings, statement: Any) -> Any:
    """Chạy một câu lệnh trên DB bằng engine riêng (ngoài app) — mô phỏng sửa DB trực tiếp."""

    async def _run() -> Any:
        engine = make_engine(settings.database_url)
        try:
            async with make_sessionmaker(engine)() as s:
                result = await s.execute(statement)
                rows = list(result.all()) if isinstance(statement, Select) else None
                await s.commit()
                return rows
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def test_recovery_refuses_tampered_state_and_cancels_game(ws_app: FastAPI, settings: Settings) -> None:
    room_id, _, _ = start_and_play_two_moves(ws_app)
    run_sql(settings, update(Game).values(state_hash="0" * 64))  # log và hash không còn khớp
    restarted = create_app(settings)
    with TestClient(restarted):
        assert restarted.state.games.live(uuid.UUID(room_id)) is None
    assert [tuple(r) for r in run_sql(settings, select(Game.status, Game.cancel_reason))] == [
        ("CANCELLED", "RECOVERY_FAILED")
    ]


@pytest.mark.rule(152, 154)
def test_replay_only_after_game_ends_and_only_for_its_players(table: Table) -> None:
    game_id = table.started[0]["payload"]["gameId"]
    url = f"/api/games/{game_id}/replay"
    assert table.tc.get(url, headers=bearer(table.tokens[1])).json()["code"] == "GAME_NOT_FINISHED"
    outsider = table.tc.post("/api/guests", json={"nickname": "Ngoài"}).json()["token"]
    assert table.tc.get(url, headers=bearer(outsider)).status_code == 404
    finish_by_timeouts(table)
    replay = table.tc.get(url, headers=bearer(table.tokens[1])).json()
    ((last_seq,),) = table.db(select(Game.last_seq))
    assert replay["verified"] is True
    assert len(replay["steps"]) == last_seq
    assert replay["initial"]["hands"] == HANDS  # hết ván mới lộ bài cả 4 người
    assert replay["steps"][0]["events"][0]["cards"] == [THREE_CLUBS]
    assert replay["steps"][-1]["view"]["phase"] == "FINISHED"
    assert [p["nickname"] for p in replay["players"]] == ["P0", "P1", "P2", "P3"]


@pytest.mark.rule(155)
def test_admin_dispute_audit_verifies_every_piece_of_evidence(table: Table) -> None:
    finish_by_timeouts(table)
    game_id = table.started[0]["payload"]["gameId"]
    assert (
        table.tc.get(f"/api/admin/games/{game_id}/audit", headers=bearer(table.tokens[0])).status_code == 401
    )
    table.tc.post("/api/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    audit = table.tc.get(f"/api/admin/games/{game_id}/audit").json()
    assert audit["verification"] == {
        "deckCommitmentOk": True,
        "rulesHashOk": True,
        "replayMatchesStoredHash": True,
        "badEventHashes": [],
        "resultMatchesReplay": True,
        "zeroSum": True,
    }
    assert audit["rulesSnapshot"]["ruleVersion"] == 1
    assert audit["events"][0]["type"] == "GAME_STARTED"
    actions = [row[0] for row in table.db(select(RuleAuditLog.action))]
    assert "VIEW_GAME_AUDIT" in actions  # Admin xem log ván cũng được ghi lại

    async def tamper() -> None:
        async with table.app.state.sessionmaker() as s:
            await s.execute(update(GameResult).values(net=[999, -999, 0, 0]))
            await s.commit()

    table.run(tamper)
    tampered = table.tc.get(f"/api/admin/games/{game_id}/audit").json()
    assert tampered["verification"]["resultMatchesReplay"] is False  # phát hiện kết quả bị sửa


def test_seats_are_marked_disconnected_after_restart(ws_app: FastAPI, settings: Settings) -> None:
    room_id, _, _ = start_and_play_two_moves(ws_app)
    restarted = create_app(settings)
    with TestClient(restarted) as tc:
        assert tc.portal is not None

        async def seats() -> list[str]:
            async with restarted.state.sessionmaker() as s:
                rows = await s.scalars(
                    select(RoomSeat.conn_state).where(RoomSeat.room_id == uuid.UUID(room_id))
                )
                return list(rows)

        assert tc.portal.call(seats) == ["DISCONNECTED"] * 4

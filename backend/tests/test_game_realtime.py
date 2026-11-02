"""Ván chơi realtime qua WebSocket với 4 client (slice S4)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, text
from starlette.websockets import WebSocketDisconnect

from app.models import Game, GameEvent
from app.realtime.games import deck_commitment
from app.realtime.sweeper import sweep_once
from tests.game_support import DECK, HANDS, Table, bearer, of_type, recv_until, rid, started_table
from tests.support import ADMIN_PASSWORD, ADMIN_USER
from tlmn_engine.cards import THREE_CLUBS
from tlmn_engine.reducer import Timeout


@pytest.fixture
def table(ws_app: FastAPI) -> Iterator[Table]:
    with started_table(ws_app) as t:
        yield t


@pytest.mark.rule(140, 152, 153)
def test_all_ready_deals_and_each_player_sees_only_own_hand(table: Table) -> None:
    for seat, started in enumerate(table.started):
        state = started["payload"]["state"]
        assert state["yourSeat"] == seat
        assert state["yourHand"] == HANDS[seat]
        assert "hands" not in state  # không lộ bài người khác (ID 152)
        assert [p["cardCount"] for p in state["players"]] == [13, 13, 13, 13]
        assert len(started["payload"]["deckCommitment"]) == 64
    room = table.tc.get(f"/api/rooms/by-code/{table.code}").json()
    assert room["status"] == "PLAYING" and room["gameId"]
    assert not any(s["ready"] for s in room["seats"])  # ván sau phải bấm sẵn sàng lại


@pytest.mark.rule(136, 156)
def test_game_stores_immutable_rules_snapshot_and_deck_commitment(table: Table) -> None:
    ((game,),) = table.db(select(Game))
    assert game.rule_version == 1 and game.rules_snapshot["ruleVersion"] == 1
    assert game.rules_snapshot["config"]["turn"]["timeLimitSeconds"] == 30
    assert game.deck == DECK and game.deck_commitment == deck_commitment(DECK, game.deck_salt)

    async def tamper() -> None:
        async with table.app.state.sessionmaker() as s:
            await s.execute(text("UPDATE games SET rules_hash = 'x'"))

    with pytest.raises(Exception, match="immutable"):
        table.run(tamper)


def test_play_is_acked_after_commit_and_broadcast_to_everyone(table: Table) -> None:
    ack = table.send(0, "game.play", {"cards": [THREE_CLUBS]}, 0)
    assert ack["type"] == "ack" and ack["payload"]["sequence"] == 1
    for seat, ws in enumerate(table.sockets):
        update = recv_until(ws, lambda m: m["type"] == "game.update")
        played = next(e for e in update["payload"]["events"] if e["type"] == "PLAYED")
        assert played["cards"] == [THREE_CLUBS] and played["seat"] == 0
        assert update["payload"]["state"]["current"] == 1
        assert update["payload"]["state"]["yourHand"] == [c for c in HANDS[seat] if c != THREE_CLUBS]
    rows = table.db(select(GameEvent.seq, GameEvent.type).order_by(GameEvent.seq))
    assert [tuple(r) for r in rows] == [(0, "GAME_STARTED"), (1, "PLAY")]


@pytest.mark.rule(151)
def test_server_rejects_illegal_moves(table: Table) -> None:
    other = next(c for c in HANDS[1])
    assert table.send(1, "game.play", {"cards": [other]}, 0)["payload"]["code"] == "NOT_YOUR_TURN"
    assert table.send(0, "game.play", {"cards": [HANDS[1][0]]}, 0)["payload"]["code"] == "CARDS_NOT_IN_HAND"
    assert table.send(0, "game.play", {"cards": ["3C"]}, 0)["payload"]["code"] == "PAYLOAD_INVALID"
    non_3c = next(c for c in HANDS[0] if c != THREE_CLUBS)
    assert table.send(0, "game.play", {"cards": [non_3c]}, 0)["payload"]["code"] == "MUST_INCLUDE_THREE_CLUBS"
    assert table.send(0, "game.pass", {}, 0)["payload"]["code"] == "LEADER_CANNOT_PASS"
    assert table.live_seq() == 0  # không lệnh nào làm đổi trạng thái


def test_duplicate_request_returns_same_ack_without_reapplying(table: Table) -> None:
    request_id = rid()
    first = table.send(0, "game.play", {"cards": [THREE_CLUBS]}, 0, request_id)
    second = table.send(0, "game.play", {"cards": [THREE_CLUBS]}, 0, request_id)
    assert second == first
    assert table.live_seq() == 1
    ((count,),) = table.db(select(func.count()).select_from(GameEvent))
    assert count == 2  # GAME_STARTED + 1 nước đi


def test_stale_base_sequence_is_rejected_with_fresh_state(table: Table) -> None:
    table.send(0, "game.play", {"cards": [THREE_CLUBS]}, 0)
    error = table.send(1, "game.pass", {}, 0)  # client 1 vẫn nghĩ sequence = 0
    assert error["payload"]["code"] == "STALE_STATE"
    fresh = recv_until(table.sockets[1], of_type("game.state"))
    assert fresh["sequence"] == 1
    assert table.send(1, "game.pass", {}, 1)["type"] == "ack"


@pytest.mark.rule(141, 142)
def test_turn_timeout_auto_plays_lowest_three_clubs_then_passes(table: Table) -> None:
    room = uuid.UUID(table.room_id)
    live = table.games.live(room)
    assert live.state.turn_deadline - datetime.now(UTC).timestamp() == pytest.approx(30, abs=5)
    assert table.run(table.games.system_action, room, Timeout())
    update = recv_until(table.sockets[2], of_type("game.update"))
    auto = next(e for e in update["payload"]["events"] if e["type"] == "PLAYED")
    assert (auto["seat"], auto["cards"], auto["auto"]) == (0, [THREE_CLUBS], True)
    table.run(table.games.system_action, room, Timeout())
    update = recv_until(table.sockets[2], of_type("game.update"))
    assert update["payload"]["events"][0] == {"type": "PASSED", "seat": 1, "auto": True}


@pytest.mark.rule(87, 145, 146)
def test_leaving_mid_game_forfeits_and_seat_cannot_be_taken_until_game_ends(table: Table) -> None:
    assert (
        table.tc.post(f"/api/rooms/{table.room_id}/leave", headers=bearer(table.tokens[2])).status_code == 204
    )
    update = recv_until(table.sockets[0], lambda m: m["type"] == "game.update")
    assert update["payload"]["events"][0] == {"type": "PLAYER_FORFEITED", "seat": 2, "rank": 4}
    newcomer = table.tc.post("/api/guests", json={"nickname": "Mới"}).json()["token"]
    response = table.tc.post(f"/api/rooms/{table.room_id}/join", json={}, headers=bearer(newcomer))
    assert response.json()["code"] == "GAME_IN_PROGRESS"  # ID 146: chỉ thay người sau khi ván kết thúc


@pytest.mark.rule(143)
def test_reconnect_mid_game_receives_own_hand(table: Table) -> None:
    table.send(0, "game.play", {"cards": [THREE_CLUBS]}, 0)
    table.sockets[3].close()
    again = table.connect(3)
    snapshot = recv_until(again, of_type("game.state"))
    assert snapshot["payload"]["state"]["yourHand"] == HANDS[3]
    assert snapshot["sequence"] == 1


def test_seat_hold_expiry_during_game_forfeits(table: Table) -> None:
    table.sockets[3].close()
    recv_until(
        table.sockets[0], lambda m: m["type"] == "room.state" and not m["payload"]["seats"][3]["connected"]
    )
    later = datetime.now(UTC) + timedelta(minutes=5)
    table.run(sweep_once, table.app.state.sessionmaker, table.app.state.hub, later, table.games)
    update = recv_until(table.sockets[0], of_type("game.update"))
    assert update["payload"]["events"][0]["type"] == "PLAYER_FORFEITED"


@pytest.mark.rule(109)
def test_admin_cancels_game_and_next_game_opens_with_three_clubs(table: Table) -> None:
    login = table.tc.post("/api/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    game_id = table.games.live(uuid.UUID(table.room_id)).game_id
    denied = table.tc.post(f"/api/admin/games/{game_id}/cancel")
    assert denied.status_code == 403  # thiếu CSRF
    ok = table.tc.post(
        f"/api/admin/games/{game_id}/cancel", headers={"X-CSRF-Token": login.json()["csrfToken"]}
    )
    assert ok.status_code == 204
    cancelled = recv_until(table.sockets[1], of_type("game.cancelled"))
    assert cancelled["payload"]["reason"] == "ADMIN"
    ((status, reason),) = table.db(select(Game.status, Game.cancel_reason))
    assert (status, reason) == ("CANCELLED", "ADMIN")
    assert table.tc.get(f"/api/rooms/by-code/{table.code}").json()["status"] == "WAITING"
    for seat in range(4):
        table.send(seat, "room.ready", {"ready": True}, 0)
    state = recv_until(table.sockets[0], of_type("game.started"))["payload"]["state"]
    assert (state["openingMode"], state["current"]) == ("THREE_CLUBS", 0)  # G8: sau ván hủy, 3♣ đi đầu


@pytest.mark.rule(136, 137)
def test_rules_published_mid_game_apply_only_to_next_game(table: Table) -> None:
    login = table.tc.post("/api/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    headers = {"X-CSRF-Token": login.json()["csrfToken"]}
    draft = table.tc.post("/api/admin/rules/draft", json={}, headers=headers).json()
    draft["config"]["turn"]["timeLimitSeconds"] = 60
    table.tc.put(
        "/api/admin/rules/draft", json={"config": draft["config"]}, headers={**headers, "If-Match": "1"}
    )
    report = table.tc.post("/api/admin/rules/draft/validate", headers=headers).json()
    table.tc.post(
        "/api/admin/rules/draft/publish",
        json={"expectedHash": report["configHash"], "expectedActiveVersion": 1, "note": "Lượt 60 giây"},
        headers=headers,
    )
    recv_until(table.sockets[0], of_type("rules.updated"))
    live = table.games.live(uuid.UUID(table.room_id))
    assert live.rule_version == 1 and live.rules.turn.timeLimitSeconds == 30  # ván đang chơi giữ luật cũ
    game_id = live.game_id
    table.tc.post(f"/api/admin/games/{game_id}/cancel", headers=headers)
    for seat in range(4):
        table.send(seat, "room.ready", {"ready": True}, 0)
    started = recv_until(table.sockets[0], of_type("game.started"))
    assert started["payload"]["rules"]["version"] == 2  # ván mới dùng luật mới


def test_full_game_by_timeouts_ends_reveals_deck_and_winner_leads_next(table: Table) -> None:
    room = uuid.UUID(table.room_id)
    for _ in range(400):
        if table.games.live(room) is None:
            break
        table.run(table.games.system_action, room, Timeout())
    ended = recv_until(table.sockets[0], of_type("game.ended"))
    result, reveal = ended["payload"]["result"], ended["payload"]["deckReveal"]
    assert result["phase"] == "FINISHED" and sum(result["net"]) == 0
    assert deck_commitment(reveal["deck"], reveal["salt"]) == ended["payload"]["deckCommitment"]
    ((status, winner, last_seq),) = table.db(select(Game.status, Game.winner_seat, Game.last_seq))
    ((events,),) = table.db(select(func.count()).select_from(GameEvent))
    assert status == "FINISHED" and events == last_seq + 1
    assert table.tc.get(f"/api/rooms/by-code/{table.code}").json()["status"] == "WAITING"
    for seat in range(4):
        table.send(seat, "room.ready", {"ready": True}, 0)
    started = recv_until(table.sockets[0], of_type("game.started"))
    state = started["payload"]["state"]
    assert (state["openingMode"], state["current"]) == ("WINNER_LEADS", winner)  # ID 9


def test_owner_closing_room_mid_game_cancels_game(table: Table) -> None:
    assert (
        table.tc.post(f"/api/rooms/{table.room_id}/close", headers=bearer(table.tokens[0])).status_code == 204
    )
    recv_until(table.sockets[2], of_type("room.closed"))
    with pytest.raises(WebSocketDisconnect):
        recv_until(table.sockets[2], lambda m: False)
    ((status, reason),) = table.db(select(Game.status, Game.cancel_reason))
    assert (status, reason) == ("CANCELLED", "ROOM_CLOSED")


def _walk(value: Any, key: str = "") -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _walk(v, k)
    elif isinstance(value, list):
        yield key, value
        for item in value:
            yield from _walk(item, key)


@pytest.mark.rule(152)
def test_no_hidden_card_ever_reaches_another_player_during_a_whole_game(table: Table) -> None:
    """AC3: trước khi ván kết thúc, ghế 1 không bao giờ nhận được bộ bài hay lá còn trên tay người khác."""
    room = uuid.UUID(table.room_id)
    still_hidden = {c for seat in (0, 2, 3) for c in HANDS[seat]}
    checked = 0
    while table.games.live(room) is not None:
        table.run(table.games.system_action, room, Timeout())
        message = table.sockets[1].receive_json()
        while message["type"] not in ("game.update", "game.ended"):
            message = table.sockets[1].receive_json()
        if message["type"] == "game.ended" or any(
            e["type"] == "GAME_ENDED" for e in message["payload"]["events"]
        ):
            break  # ván đã kết thúc: lúc này mới được công khai bài của mọi người
        for event in message["payload"]["events"]:
            if event["type"] == "PLAYED":
                still_hidden -= set(event["cards"])  # lá đã đánh ra bàn là công khai
        for key, values in _walk(message):
            assert key not in ("hands", "deck", "deckSalt"), f"Lộ '{key}' khi ván đang chơi"
            ints = {v for v in values if isinstance(v, int) and not isinstance(v, bool)}
            if key in ("yourHand", "cards", "top"):
                assert not ints & still_hidden, f"Lộ bài người khác qua '{key}'"
        assert set(message["payload"]["state"]["yourHand"]) <= set(HANDS[1])
        checked += 1
    assert checked > 20

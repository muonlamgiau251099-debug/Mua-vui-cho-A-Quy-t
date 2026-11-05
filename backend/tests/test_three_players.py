"""Phòng và ván 3 người: đổi số người, lá mở ván khi 3♣ không được chia (loại 3♠), người thắng vắng mặt."""

import random
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from starlette.testclient import TestClient

from app.models import Game, GameResult
from tests.game_support import (
    Table,
    bearer,
    finish_by_timeouts,
    of_type,
    ready_all,
    recv_until,
    started_table,
)
from tlmn_engine.cards import THREE_SPADES, parse_card, parse_cards
from tlmn_engine.dealing import check_instant_win, deal, detect_redeal, determine_opener
from tlmn_engine.reducer import Timeout
from tlmn_engine.rules_config import default_config

RULES = default_config()


def three_player_deck(hands: list[str], undealt: str) -> list[int]:
    """Bộ 52 lá cho 3 người: các tay chỉ định, `undealt` chắc chắn không được chia; phần còn lại xáo có
    seed, chọn seed để ván luôn bắt đầu bình thường (không tới trắng, không chia lại)."""
    fixed = [parse_cards(h) for h in hands]
    kept_back = parse_cards(undealt)
    used = {c for h in fixed for c in h} | set(kept_back)
    for seed in range(2000):
        pool = [c for c in range(52) if c not in used]
        random.Random(seed).shuffle(pool)
        deck: list[int] = []
        for h in fixed:
            deck.extend(sorted(h + [pool.pop() for _ in range(13 - len(h))]))
        deck.extend(kept_back + pool)
        dealt = deal(deck, 3)
        if check_instant_win(dealt, 0, RULES) is None and detect_redeal(dealt, RULES) is None:
            return deck
    raise AssertionError("Không dựng được bộ bài")


# 3♣ nằm trong phần thừa; 3♠ ở ghế 0; 3♦ ở ghế 1; 3♥ ở ghế 2 → lá mở ván là 3♦ của ghế 1.
NO_THREE_CLUBS = three_player_deck(["3S 9S", "3D 8S", "3H 7S"], undealt="3C")


def new_guest(tc: TestClient, nickname: str) -> str:
    return str(tc.post("/api/guests", json={"nickname": nickname}).json()["token"])


def join(tc: TestClient, room_id: str, token: str, **body: int) -> int:
    return tc.post(f"/api/rooms/{room_id}/join", json=body, headers=bearer(token)).status_code


def set_count(tc: TestClient, room_id: str, token: str, count: int) -> int:
    url = f"/api/rooms/{room_id}/player-count"
    return tc.patch(url, json={"playerCount": count}, headers=bearer(token)).status_code


def room_state(tc: TestClient, code: str) -> dict[str, Any]:
    state: dict[str, Any] = tc.get(f"/api/rooms/by-code/{code}").json()
    return state


@pytest.fixture
def table3(ws_app: FastAPI) -> Iterator[Table]:
    with started_table(ws_app, NO_THREE_CLUBS, players=3) as t:
        yield t


# --- Đổi số người của phòng -------------------------------------------------------------


def test_owner_switches_room_between_three_and_four_players(ws_app: FastAPI) -> None:
    with TestClient(ws_app) as tc:
        owner = new_guest(tc, "Chủ")
        room = tc.post("/api/rooms", headers=bearer(owner)).json()
        rid, code = room["roomId"], room["code"]
        state = room_state(tc, code)
        assert (state["playerCount"], len(state["seats"])) == (4, 4)

        assert set_count(tc, rid, owner, 3) == 200
        state = room_state(tc, code)
        assert state["playerCount"] == 3
        assert [s["seatNo"] for s in state["seats"]] == [0, 1, 2]

        # Phòng 3 người: ghế thứ 4 không còn, nên người thứ 4 nhận "phòng đã đủ 3 người".
        guests = [new_guest(tc, f"K{n}") for n in range(4)]
        assert join(tc, rid, guests[0]) == 200 and join(tc, rid, guests[1]) == 200
        full = tc.post(f"/api/rooms/{rid}/join", json={}, headers=bearer(guests[2]))
        assert full.status_code == 409 and full.json()["code"] == "ROOM_FULL" and "3" in full.json()["title"]
        assert join(tc, rid, guests[3], seatNo=3) in (404, 409)  # không có ghế thứ 4

        # Nâng lại 4 người: thêm ghế thứ 4 và người đó vào được.
        assert set_count(tc, rid, owner, 4) == 200
        assert len(room_state(tc, code)["seats"]) == 4
        assert join(tc, rid, guests[2]) == 200


def test_player_count_change_is_owner_only_validated_and_needs_the_last_seat_empty(ws_app: FastAPI) -> None:
    with TestClient(ws_app) as tc:
        owner, guest = new_guest(tc, "Chủ"), new_guest(tc, "Khách")
        room = tc.post("/api/rooms", headers=bearer(owner)).json()
        rid = room["roomId"]
        assert join(tc, rid, guest, seatNo=3) == 200
        assert set_count(tc, rid, guest, 3) == 403  # không phải chủ phòng
        assert set_count(tc, rid, owner, 2) == 422  # chỉ 3 hoặc 4
        url = f"/api/rooms/{rid}/player-count"
        denied = tc.patch(url, json={"playerCount": 3}, headers=bearer(owner))
        assert denied.status_code == 409 and denied.json()["code"] == "SEAT_OCCUPIED"  # ghế 4 đang có người
        assert len(room_state(tc, room["code"])["seats"]) == 4


def test_player_count_cannot_change_while_a_game_is_running(table3: Table) -> None:
    url = f"/api/rooms/{table3.room_id}/player-count"
    response = table3.tc.patch(url, json={"playerCount": 4}, headers=bearer(table3.tokens[0]))
    assert response.status_code == 409 and response.json()["code"] == "GAME_IN_PROGRESS"


# --- Ván 3 người -----------------------------------------------------------------------


def test_three_player_game_starts_when_all_three_are_ready_and_deals_39_cards(table3: Table) -> None:
    hands = [s["payload"]["state"]["yourHand"] for s in table3.started]
    for seat, started in enumerate(table3.started):
        state = started["payload"]["state"]
        assert len(state["players"]) == 3 and len(hands[seat]) == 13 and state["yourSeat"] == seat
        assert "undealt" not in state and "hands" not in state
        others = {c for s, h in enumerate(hands) if s != seat for c in h}
        assert not others & set(hands[seat])  # không lộ / trùng bài giữa các ghế
    ((mode,),) = table3.db(select(Game.opening_mode))
    assert mode == "THREE_CLUBS"


def test_leader_is_decided_without_three_spades_and_backend_enforces_the_opening_card(table3: Table) -> None:
    state = table3.started[0]["payload"]["state"]
    three_diamonds = parse_card("3D")
    assert state["current"] == 1 and state["openingCard"] == three_diamonds  # ghế 1, không phải ghế 0 giữ 3♠
    assert THREE_SPADES in state["yourHand"]  # ghế 0 giữ 3♠ nhưng không được đánh đầu

    not_my_turn = table3.send(0, "game.play", {"cards": [THREE_SPADES]}, 0)
    assert not_my_turn["payload"]["code"] == "NOT_YOUR_TURN"

    wrong = table3.send(1, "game.play", {"cards": [parse_card("8S")]}, 0)
    assert wrong["payload"]["code"] == "MUST_INCLUDE_OPENING_CARD" and "3♦" in wrong["payload"]["message"]

    ok = table3.send(1, "game.play", {"cards": [three_diamonds]}, 0)
    assert ok["type"] == "ack"
    update = recv_until(table3.sockets[0], of_type("game.update"))["payload"]
    assert update["state"]["firstMovePending"] is False and update["state"]["current"] == 2


def test_timeout_on_the_first_move_plays_the_opening_card(table3: Table) -> None:
    import uuid

    table3.run(table3.games.system_action, uuid.UUID(table3.room_id), Timeout())
    update = recv_until(table3.sockets[0], of_type("game.update"))
    played = next(e for e in update["payload"]["events"] if e["type"] == "PLAYED")
    assert played["cards"] == [parse_card("3D")] and played["auto"] is True


def test_three_player_game_finishes_zero_sum_is_stored_and_shows_three_scores(table3: Table) -> None:
    ended = finish_by_timeouts(table3)
    result = ended["payload"]["result"]
    assert len(result["players"]) == 3 and sum(result["net"]) == 0
    assert sorted(p["rank"] for p in result["players"]) == [1, 2, 3]
    assert len(result["hands"]) == 3  # lộ bài cả 3 người khi hết ván
    ((end_type, ranks, net),) = table3.db(select(GameResult.end_type, GameResult.ranks, GameResult.net))
    assert end_type == "NORMAL" and sorted(ranks) == [1, 2, 3] and net == result["net"] and sum(net) == 0

    summary = table3.tc.get(f"/api/rooms/by-code/{table3.code}").json()["session"]
    assert len(summary["scores"]) == 3 and sum(s["total"] for s in summary["scores"]) == 0


def test_next_game_is_led_by_the_previous_winner_while_everyone_stays(table3: Table) -> None:
    finish_by_timeouts(table3)
    ((winner,),) = table3.db(select(Game.winner_seat))
    state = ready_all(table3)[0]["payload"]["state"]
    assert state["current"] == winner  # ID 9: người thắng ván trước còn tham gia thì đánh đầu
    assert state["openingMode"] == "WINNER_LEADS"
    assert len(state["players"]) == 3 and state["firstMovePending"] is True


def test_absent_previous_winner_next_game_uses_the_opener_rule_and_never_blocks(table3: Table) -> None:
    finish_by_timeouts(table3)
    ((winner,),) = table3.db(select(Game.winner_seat))
    leave_url = f"/api/rooms/{table3.room_id}/leave"
    assert table3.tc.post(leave_url, headers=bearer(table3.tokens[winner])).status_code == 204

    newcomer = new_guest(table3.tc, "Người mới")  # người thắng vắng mặt, người khác ngồi vào ghế đó
    assert join(table3.tc, table3.room_id, newcomer) == 200
    table3.tokens[winner] = newcomer
    table3.sockets[winner] = table3.connect(winner)

    state = ready_all(table3)[0]["payload"]["state"]
    card, leader = determine_opener(deal(NO_THREE_CLUBS, 3))  # cùng bộ bài giả lập → cùng người đánh đầu
    assert state["openingMode"] == "THREE_CLUBS" and state["firstMovePending"] is True
    assert (state["current"], state["openingCard"]) == (leader, card)
    assert card == parse_card("3D") and leader == 1  # 3♠ không được dùng, 3♣ không được chia
    # Danh sách người chơi đổi nên là phiên mới: điểm phiên bắt đầu lại từ 0.
    session = table3.tc.get(f"/api/rooms/by-code/{table3.code}").json()["session"]
    assert session["gamesPlayed"] == 0 and all(s["total"] == 0 for s in session["scores"])

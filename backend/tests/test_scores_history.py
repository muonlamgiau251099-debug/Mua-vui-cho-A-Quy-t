"""Sổ điểm bền vững, bảng điểm phiên, lịch sử, khởi động lại phiên (slice S5)."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import Game, GameResult, GameSession, ScoreTransfer, SessionScore
from tests.game_support import (
    DECK,
    RULES,
    Table,
    bearer,
    finish_by_timeouts,
    of_type,
    ready_all,
    recv_until,
    started_table,
)
from tlmn_engine.dealing import check_instant_win
from tlmn_testkit import deck_with


@pytest.fixture
def table(ws_app: FastAPI) -> Iterator[Table]:
    with started_table(ws_app) as t:
        yield t


def session_detail(table: Table, seat: int = 0) -> dict:  # type: ignore[type-arg]
    ((session_id,),) = table.db(select(GameSession.id).where(GameSession.status == "ACTIVE"))
    response = table.tc.get(f"/api/sessions/{session_id}", headers=bearer(table.tokens[seat]))
    assert response.status_code == 200, response.text
    return dict(response.json())


@pytest.mark.rule(111, 131, 132, 133)
def test_finished_game_records_result_transfers_and_session_scores(table: Table) -> None:
    ended = finish_by_timeouts(table)
    net = ended["payload"]["result"]["net"]
    ((result,),) = table.db(select(GameResult))
    assert result.net == net and sum(net) == 0
    transfers = [row[0] for row in table.db(select(ScoreTransfer).order_by(ScoreTransfer.line_no))]
    per_seat = [0, 0, 0, 0]
    for t in transfers:
        per_seat[t.from_seat] -= t.amount
        per_seat[t.to_seat] += t.amount
    assert per_seat == net  # mỗi biến động là một khoản chuyển (ID 132)
    totals = {row[0].seat: (row[0].total, row[0].games_counted) for row in table.db(select(SessionScore))}
    assert totals == {seat: (net[seat], 1) for seat in range(4)}
    state = recv_until(table.sockets[1], lambda m: m["type"] == "room.state" and m["payload"]["session"])
    assert [s["total"] for s in state["payload"]["session"]["scores"]] == net


@pytest.mark.rule(130, 131, 150)
def test_two_games_accumulate_and_history_shows_each_change(table: Table) -> None:
    first = finish_by_timeouts(table)["payload"]["result"]["net"]
    ready_all(table)
    second = finish_by_timeouts(table)["payload"]["result"]["net"]
    detail = session_detail(table, seat=2)
    games = detail["games"]
    assert [g["net"] for g in games] == [first, second]
    assert games[1]["cumulative"] == [a + b for a, b in zip(first, second, strict=True)]
    assert all(g["transfers"] for g in games)
    totals = [a + b for a, b in zip(first, second, strict=True)]
    standings = detail["standings"]
    assert [s["total"] for s in standings] == sorted(totals, reverse=True)  # ID 130: xếp theo điểm tích lũy
    assert [s["place"] for s in standings] == [1, 2, 3, 4]
    assert {s["seat"]: s["total"] for s in standings} == dict(enumerate(totals))


@pytest.mark.rule(109)
def test_cancelled_game_is_not_scored(table: Table) -> None:
    assert table.run(table.games.cancel, uuid.UUID(table.room_id), "ADMIN")
    recv_until(table.sockets[0], of_type("game.cancelled"))
    assert table.db(select(GameResult)) == []
    assert table.db(select(ScoreTransfer)) == []
    games = session_detail(table)["games"]
    assert (games[0]["status"], games[0]["net"], games[0]["cancelReason"]) == ("CANCELLED", None, "ADMIN")


def test_same_game_can_never_be_scored_twice(table: Table) -> None:
    finish_by_timeouts(table)

    async def record_again() -> None:
        async with table.app.state.sessionmaker() as s:
            game = await s.scalar(select(Game))
            assert game is not None
            s.add(
                GameResult(
                    game_id=game.id,
                    session_id=game.session_id,
                    end_type="NORMAL",
                    ranks=[],
                    statuses=[],
                    net=[],
                )
            )
            await s.commit()

    with pytest.raises(IntegrityError):
        table.run(record_again)


def test_score_transfers_are_append_only(table: Table) -> None:
    finish_by_timeouts(table)

    async def tamper() -> None:
        async with table.app.state.sessionmaker() as s:
            await s.execute(text("UPDATE score_transfers SET amount = 1"))

    with pytest.raises(Exception, match="append-only"):
        table.run(tamper)


@pytest.mark.rule(129, 148)
def test_owner_restarts_session_and_scores_start_again_from_zero(table: Table) -> None:
    url = f"/api/rooms/{table.room_id}/sessions/restart"
    assert table.tc.post(url, headers=bearer(table.tokens[0])).json()["code"] == "GAME_IN_PROGRESS"
    finish_by_timeouts(table)
    assert table.tc.post(url, headers=bearer(table.tokens[1])).json()["code"] == "NOT_OWNER"
    assert table.tc.post(url, headers=bearer(table.tokens[0])).status_code == 204
    recv_until(table.sockets[2], of_type("session.restarted"))
    cleared = recv_until(
        table.sockets[2], lambda m: m["type"] == "room.state" and m["payload"]["session"] is None
    )
    assert cleared["payload"]["session"] is None
    started = ready_all(table)
    assert started[0]["payload"]["state"]["openingMode"] == "THREE_CLUBS"  # phiên mới: ván đầu mở bằng 3♣
    rows = table.db(
        select(GameSession.session_no, GameSession.status, GameSession.end_reason).order_by(
            GameSession.session_no
        )
    )
    assert [tuple(r) for r in rows] == [(1, "ENDED", "RESTARTED"), (2, "ACTIVE", None)]
    session = table.tc.get(f"/api/rooms/by-code/{table.code}").json()["session"]
    assert (session["sessionNo"], [s["total"] for s in session["scores"]]) == (2, [0, 0, 0, 0])


def test_changing_a_player_starts_a_new_session(table: Table) -> None:
    finish_by_timeouts(table)
    assert (
        table.tc.post(f"/api/rooms/{table.room_id}/leave", headers=bearer(table.tokens[3])).status_code == 204
    )
    newcomer = table.tc.post("/api/guests", json={"nickname": "Mới"}).json()["token"]
    assert (
        table.tc.post(f"/api/rooms/{table.room_id}/join", json={}, headers=bearer(newcomer)).json()["seatNo"]
        == 3
    )
    table.tokens[3] = newcomer
    table.sockets[3] = table.connect(3)
    ready_all(table)
    rows = table.db(select(GameSession.session_no, GameSession.end_reason).order_by(GameSession.session_no))
    assert [tuple(r) for r in rows] == [(1, "ROSTER_CHANGED"), (2, None)]


def test_history_is_only_visible_to_session_members(table: Table) -> None:
    finish_by_timeouts(table)
    ((session_id,),) = table.db(select(GameSession.id))
    outsider = table.tc.post("/api/guests", json={"nickname": "Ngoài"}).json()["token"]
    assert table.tc.get(f"/api/sessions/{session_id}", headers=bearer(outsider)).status_code == 404
    assert table.tc.get("/api/guests/me/sessions", headers=bearer(outsider)).json()["items"] == []
    mine = table.tc.get("/api/guests/me/sessions", headers=bearer(table.tokens[1])).json()["items"]
    assert [s["sessionId"] for s in mine] == [str(session_id)]
    room_list = table.tc.get(f"/api/rooms/{table.room_id}/sessions", headers=bearer(table.tokens[1])).json()
    assert room_list["items"][0]["gamesPlayed"] == 1


def test_instant_win_is_scored_right_after_dealing(ws_app: FastAPI) -> None:
    dragon = "3D 4D 5D 6D 7D 8D 9D 10D JD QD KD AD"
    deck = deck_with(
        ["3C", dragon, "", ""],
        lambda h: (w := check_instant_win(h, 0, RULES)) is not None and w.winners == [1],
    )
    with started_table(ws_app, deck) as t:
        ended = recv_until(t.sockets[0], of_type("game.ended"))
        assert ended["payload"]["result"]["endType"] == "INSTANT_WIN"
        ((result,),) = t.db(select(GameResult))
        assert result.net == [-200, 600, -200, -200]
        totals = {row[0].seat: row[0].total for row in t.db(select(SessionScore))}
        assert totals == {0: -200, 1: 600, 2: -200, 3: -200}
        # Ván sau tới trắng mở bằng 3♣ (ID 60) và cộng dồn tiếp vào cùng phiên
        t.app.state.games.deck_source = lambda: list(DECK)
        assert ready_all(t)[0]["payload"]["state"]["openingMode"] == "THREE_CLUBS"

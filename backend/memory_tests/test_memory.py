import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.memory import MemoryStore


def message(kind, payload=None, seq=0, request_id=None):
    return dict(type=kind, payload=payload or {}, sequence=seq, requestId=request_id or str(uuid4()))


def receive(ws, kind, request_id=None):
    for _ in range(100):
        msg = ws.receive_json()
        if msg["type"] == "error" and kind != "error":
            raise AssertionError(msg)
        if msg["type"] == kind and (request_id is None or msg["requestId"] == request_id):
            return msg
    raise AssertionError(f"no {kind}")


def guest(client, name):
    response = client.post("/api/guests", json={"nickname": name})
    assert response.status_code == 201, response.text
    result = response.json()
    return result, {"Authorization": f"Bearer {result['token']}"}


def setup_players(client):
    players = [guest(client, f"Test {i}") for i in range(4)]
    room = client.post("/api/rooms", headers=players[0][1]).json()
    for _player, headers in players[1:]:
        assert client.post(f"/api/rooms/{room['roomId']}/join", headers=headers, json={}).status_code == 200
    return players, room


def play_game(client, sockets):
    views = [receive(ws, "game.started") for ws in sockets]
    game_id = views[0]["payload"]["gameId"]
    # Only the recipient's hand is revealed; all four hands form a complete shuffled deck.
    hands = [v["payload"]["state"]["yourHand"] for v in views]
    assert len({card for hand in hands for card in hand}) == 52
    assert all(len(hand) == 13 for hand in hands)
    assert all("hands" not in v["payload"]["state"] for v in views)
    for _ in range(600):
        state = views[0]["payload"]["state"]
        if state["phase"] != "PLAYING":
            break
        seat = state["current"]
        mine = views[seat]["payload"]["state"]
        if state["trick"]["top"] is not None:
            kind, payload = "game.pass", {}
        else:
            card = 1 if state["firstMovePending"] and 1 in mine["yourHand"] else mine["yourHand"][0]
            kind, payload = "game.play", {"cards": [card]}
        req = message(kind, payload, views[seat]["sequence"])
        sockets[seat].send_json(req)
        ack = receive(sockets[seat], "ack", req["requestId"])
        assert ack["payload"]["sequence"] == views[seat]["sequence"] + 1
        views = [receive(ws, "game.update") for ws in sockets]
        # pace below server's real 10 messages/s cap; four clients together still simulate fast play
        import time

        time.sleep(0.11)
    else:
        raise AssertionError("game did not finish")
    results = [receive(ws, "game.ended") for ws in sockets]
    assert all(r["payload"]["result"]["phase"] == "FINISHED" for r in results)
    assert all(sum(r["payload"]["result"]["net"]) == 0 for r in results)
    return game_id, results


def test_four_websocket_players_complete_game_and_replay(tmp_path):
    (tmp_path / "index.html").write_text("<html>original SPA build</html>")
    store = MemoryStore()
    with TestClient(create_app(store, tmp_path)) as client, ExitStack() as stack:
        assert client.get("/").status_code == 200
        assert client.get("/r/ABCDEF").status_code == 200
        assert client.get("/.env").status_code == 404
        players, room = setup_players(client)
        sockets = [
            stack.enter_context(client.websocket_connect(f"/ws/rooms/{room['roomId']}")) for _ in players
        ]
        for ws, (player, _) in zip(sockets, players, strict=True):
            ws.send_json(message("auth", {"token": player["token"]}))
            assert receive(ws, "ack")["payload"]["type"] == "auth"
        for ws in sockets:
            ws.send_json(message("room.ready", {"ready": True}))
        game_id, results = play_game(client, sockets)
        assert len(set(r["payload"]["gameId"] for r in results)) == 1
        replay = client.get(f"/api/games/{game_id}/replay", headers=players[0][1])
        assert replay.status_code == 200, replay.text
        assert replay.json()["verified"] is True
        assert replay.json()["steps"]
        assert len(client.get("/api/guests/me/sessions", headers=players[0][1]).json()["items"]) == 1
        _stranger, headers = guest(client, "Stranger")
        assert client.get(f"/api/games/{game_id}/replay", headers=headers).status_code == 404
        assert client.get("/api/health").json()["seatedPlayers"] == 4
        assert "sqlalchemy" not in sys.modules  # runtime imports no DB layer


def test_capacity_20_and_fifth_seat_and_reclaim():
    with TestClient(create_app()) as client:
        players, room = setup_players(client)
        _fifth, headers = guest(client, "Fifth")
        assert client.post(f"/api/rooms/{room['roomId']}/join", headers=headers, json={}).status_code == 409
        for i in range(16):
            _, h = guest(client, f"Capacity {i}")
            assert client.post("/api/rooms", headers=h).status_code == 201
        assert client.post("/api/rooms", headers=headers).status_code == 503
        assert client.post(f"/api/rooms/{room['roomId']}/leave", headers=players[0][1]).status_code == 204
        assert client.post("/api/rooms", headers=headers).status_code == 201
        assert client.get("/api/health").json()["seatedPlayers"] == 20


def test_concurrent_join_does_not_exceed_four():
    with TestClient(create_app()) as client:
        _owner, headers = guest(client, "Owner")
        room = client.post("/api/rooms", headers=headers).json()
        players = [guest(client, f"Join {i}")[1] for i in range(10)]

        def join(h):
            return client.post(f"/api/rooms/{room['roomId']}/join", headers=h, json={}).status_code

        with ThreadPoolExecutor(max_workers=10) as executor:
            codes = list(executor.map(join, players))
        assert codes.count(200) == 3
        assert codes.count(409) == 7
        assert client.get("/api/health").json()["seatedPlayers"] == 4


@pytest.mark.asyncio
async def test_midnight_keeps_active_game_then_purges_only_old_data():
    clock = [datetime(2026, 11, 2, 23, 59, 59, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp()]
    store = MemoryStore(lambda: clock[0])
    guests = [store.create_guest(f"Player {i}")[0] for i in range(4)]
    room = store.create_room(guests[0])
    for g in guests[1:]:
        store.join(room, g, None)
    # deterministic shuffled game without an instant win
    import random

    deck = list(range(52))
    random.Random(42).shuffle(deck)
    store.deck_source = lambda: deck
    for s in room.seats:
        s.connected = s.ready = True
    await store.start(room)
    assert room.live
    game_id = room.live["id"]
    waiting_guest, _ = store.create_guest("Waiting")
    waiting = store.create_room(waiting_guest)
    clock[0] += 1
    await store.tick()
    assert room.pending_reset and room.live["id"] == game_id
    assert waiting.id not in store.rooms
    assert len(store.games) == 1
    new_guest, new_token = store.create_guest("New Day")
    new_room = store.create_room(new_guest)
    # Normal legal play across midnight, never reset an active game.
    while room.live:
        state = room.live["state"]
        seat = state.current
        from tlmn_engine.reducer import Pass, Play

        hand = state.players[seat].hand
        card = 1 if state.first_move_pending and 1 in hand else hand[0]
        action = Pass(seat) if state.trick.top else Play(seat, (card,))
        events = await store.action(room, action)
        await store.after_action(room, events)
    assert room.id not in store.rooms
    assert new_room.id in store.rooms
    assert store.authenticate(new_token) is new_guest
    assert not store.games
    assert all(g.id == new_guest.id for g in store.guests.values())
    assert store.day == "2026-11-03"


def test_websocket_reconnect_dedup_stale_state_and_origin():
    store = MemoryStore()
    with TestClient(create_app(store)) as client, ExitStack() as stack:
        players, room = setup_players(client)
        sockets = []
        for p, _ in players:
            ws = stack.enter_context(client.websocket_connect(f"/ws/rooms/{room['roomId']}"))
            ws.send_json(message("auth", {"token": p["token"]}))
            receive(ws, "ack")
            sockets.append(ws)
        for ws in sockets:
            ws.send_json(message("room.ready", {"ready": True}))
        views = [receive(ws, "game.started") for ws in sockets]
        state = views[0]["payload"]["state"]
        if state["phase"] != "PLAYING":
            pytest.skip("random instant win")
        seat = state["current"]
        hand = views[seat]["payload"]["state"]["yourHand"]
        req = message("game.play", {"cards": [1 if 1 in hand else hand[0]]}, views[seat]["sequence"])
        sockets[seat].send_json(req)
        ack = receive(sockets[seat], "ack", req["requestId"])
        for ws in sockets:
            receive(ws, "game.update")
        # Same requestId after reconnect receives the exact same ack, no second action.
        replacement = stack.enter_context(client.websocket_connect(f"/ws/rooms/{room['roomId']}"))
        replacement.send_json(message("auth", {"token": players[seat][0]["token"]}))
        receive(replacement, "ack")
        snapshot = receive(replacement, "game.state")
        assert snapshot["sequence"] == ack["sequence"]
        replacement.send_json(req)
        assert receive(replacement, "ack", req["requestId"]) == ack
        replacement.send_json(message("game.pass", seq=-1))
        assert receive(replacement, "error")["payload"]["code"] == "STALE_STATE"
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"/ws/rooms/{room['roomId']}", headers={"origin": "https://evil.example"}
            ):
                pass


def test_reset_does_not_purge_new_day_games():
    # Regression: an older room finishing must not erase a new-day room's replay.
    store = MemoryStore()
    store.games["new"] = {"day": store.day}
    store.games["old"] = {"day": "2000-01-01"}
    store.purge_previous_day()
    assert list(store.games) == ["new"]

"""Test WebSocket phòng chờ với nhiều client (Starlette TestClient, chạy đồng bộ)."""

import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient, WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from app.realtime.sweeper import sweep_once
from tests.support import ADMIN_PASSWORD, ADMIN_USER

Msg = dict[str, Any]


def rid() -> str:
    return str(uuid.uuid4())


def new_guest(tc: TestClient, nickname: str) -> str:
    response = tc.post("/api/guests", json={"nickname": nickname})
    assert response.status_code == 201, response.text
    return str(response.json()["token"])


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def recv_until(ws: WebSocketTestSession, predicate: Callable[[Msg], bool], limit: int = 30) -> Msg:
    for _ in range(limit):
        message: Msg = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("Không nhận được message mong đợi")


def drain_until(ws: WebSocketTestSession, msg_type: str, limit: int = 30) -> list[Msg]:
    """Đọc tới khi gặp message msg_type; trả về mọi message đã đọc (kể cả message đó)."""
    seen: list[Msg] = []
    for _ in range(limit):
        seen.append(ws.receive_json())
        if seen[-1]["type"] == msg_type:
            return seen
    raise AssertionError(f"Không nhận được {msg_type}")


def eventually(check: Callable[[], bool], timeout: float = 5.0) -> None:
    """Chờ điều kiện đúng (việc dọn dẹp khi ngắt kết nối chạy bất đồng bộ phía server)."""
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() > deadline:
            raise AssertionError("Điều kiện không thành đúng trong thời gian chờ")
        time.sleep(0.05)


def of_type(msg_type: str) -> Callable[[Msg], bool]:
    return lambda m: m["type"] == msg_type


@contextmanager
def connected(tc: TestClient, room_id: str, token: str) -> Iterator[WebSocketTestSession]:
    with tc.websocket_connect(f"/ws/rooms/{room_id}") as ws:
        ws.send_json({"type": "auth", "requestId": rid(), "payload": {"token": token}})
        ack = ws.receive_json()
        assert ack["type"] == "ack", ack
        recv_until(ws, of_type("room.state"))
        yield ws


@pytest.fixture
def tc(ws_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(ws_app) as client:
        yield client


@pytest.fixture
def full_room(tc: TestClient) -> tuple[str, list[str]]:
    tokens = [new_guest(tc, f"P{n}") for n in range(4)]
    room_id = tc.post("/api/rooms", headers=bearer(tokens[0])).json()["roomId"]
    for token in tokens[1:]:
        assert tc.post(f"/api/rooms/{room_id}/join", json={}, headers=bearer(token)).status_code == 200
    return room_id, tokens


def test_first_message_must_be_auth(tc: TestClient, full_room: tuple[str, list[str]]) -> None:
    room_id, _ = full_room
    with tc.websocket_connect(f"/ws/rooms/{room_id}") as ws:
        ws.send_json({"type": "ping", "requestId": rid(), "payload": {}})
        assert ws.receive_json()["payload"]["code"] == "UNAUTHORIZED"
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 4401


def test_auth_timeout_closes_socket(tc: TestClient, full_room: tuple[str, list[str]]) -> None:
    room_id, _ = full_room
    with tc.websocket_connect(f"/ws/rooms/{room_id}") as ws, pytest.raises(WebSocketDisconnect) as exc:
        ws.receive_json()  # không gửi gì → server đóng sau ws_auth_timeout_seconds
    assert exc.value.code == 4408  # khác 4401: client hiểu là lỗi tạm thời và tự kết nối lại


def test_guest_not_in_room_is_rejected(tc: TestClient, full_room: tuple[str, list[str]]) -> None:
    room_id, _ = full_room
    outsider = new_guest(tc, "Ngoài")
    with tc.websocket_connect(f"/ws/rooms/{room_id}") as ws:
        ws.send_json({"type": "auth", "requestId": rid(), "payload": {"token": outsider}})
        assert ws.receive_json()["payload"]["code"] == "NOT_IN_ROOM"
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 4403


def test_foreign_origin_is_rejected(tc: TestClient, full_room: tuple[str, list[str]]) -> None:
    room_id, _ = full_room
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        tc.websocket_connect(f"/ws/rooms/{room_id}", headers={"origin": "https://evil.example"}),
    ):
        pass
    assert exc.value.code == 4403


@pytest.mark.rule(139, 140)
def test_all_four_ready_triggers_all_ready_for_everyone(
    tc: TestClient, full_room: tuple[str, list[str]]
) -> None:
    room_id, tokens = full_room
    code = _code(tc, tokens[0])
    with ExitStack() as stack:
        sockets = [stack.enter_context(connected(tc, room_id, t)) for t in tokens]
        for ws in sockets:
            ws.send_json({"type": "room.ready", "requestId": rid(), "payload": {"ready": True}})
            # Ack được gửi trước; với người cuối cùng, sau ack là room.allReady rồi server chia bài (S4).
            assert not any(m["type"] == "room.allReady" for m in drain_until(ws, "ack"))
        for ws in sockets:
            recv_until(ws, of_type("room.allReady"))
            recv_until(ws, of_type("game.started"))
    # Sau khi mọi người đóng kết nối thì không còn ai sẵn sàng.
    eventually(lambda: not any(s["ready"] for s in tc.get(f"/api/rooms/by-code/{code}").json()["seats"]))


def test_room_state_tells_each_player_their_own_seat(
    tc: TestClient, full_room: tuple[str, list[str]]
) -> None:
    room_id, tokens = full_room
    with connected(tc, room_id, tokens[2]) as ws:
        ws.send_json({"type": "room.ready", "requestId": rid(), "payload": {"ready": True}})
        state = recv_until(ws, lambda m: m["type"] == "room.state" and m["payload"]["seats"][2]["ready"])
    assert state["payload"]["yourSeat"] == 2
    assert state["sequence"] == state["payload"]["version"]


def test_ready_requires_boolean(tc: TestClient, full_room: tuple[str, list[str]]) -> None:
    room_id, tokens = full_room
    with connected(tc, room_id, tokens[0]) as ws:
        ws.send_json({"type": "room.ready", "requestId": rid(), "payload": {"ready": "yes"}})
        assert recv_until(ws, of_type("error"))["payload"]["code"] == "PAYLOAD_INVALID"


def test_duplicate_request_id_returns_same_response_without_reprocessing(
    tc: TestClient, full_room: tuple[str, list[str]]
) -> None:
    room_id, tokens = full_room
    with connected(tc, room_id, tokens[0]) as ws:
        request_id = rid()
        ws.send_json({"type": "room.ready", "requestId": request_id, "payload": {"ready": True}})
        first = recv_until(ws, of_type("ack"))
        version = tc.get(f"/api/rooms/by-code/{_code(tc, tokens[0])}").json()["version"]
        ws.send_json({"type": "room.ready", "requestId": request_id, "payload": {"ready": False}})
        second = recv_until(ws, of_type("ack"))
        assert second == first
        state = tc.get(f"/api/rooms/by-code/{_code(tc, tokens[0])}").json()
        assert state["version"] == version
        assert state["seats"][0]["ready"] is True  # lệnh gửi lặp không được xử lý lại


def _code(tc: TestClient, token: str) -> str:
    return str(tc.get("/api/guests/me", headers=bearer(token)).json()["currentRoom"]["code"])


@pytest.mark.rule(143, 144)
def test_disconnect_keeps_seat_and_reconnect_restores_it(
    tc: TestClient, full_room: tuple[str, list[str]]
) -> None:
    room_id, tokens = full_room
    with connected(tc, room_id, tokens[0]) as watcher:
        with connected(tc, room_id, tokens[1]) as ws:
            ws.send_json({"type": "room.ready", "requestId": rid(), "payload": {"ready": True}})
            recv_until(ws, of_type("ack"))
        lost = recv_until(
            watcher, lambda m: m["type"] == "room.state" and not m["payload"]["seats"][1]["connected"]
        )
        seat = lost["payload"]["seats"][1]
        assert (seat["occupied"], seat["ready"]) == (True, False)
        hold = datetime.fromisoformat(seat["holdUntil"]) - datetime.now(UTC)
        assert timedelta(seconds=100) < hold <= timedelta(seconds=120)  # ID 144: giữ ghế 120 giây
        with connected(tc, room_id, tokens[1]):
            back = recv_until(
                watcher, lambda m: m["type"] == "room.state" and m["payload"]["seats"][1]["connected"]
            )
            assert back["payload"]["seats"][1]["holdUntil"] is None


@pytest.mark.rule(144)
def test_seat_is_released_after_hold_expires_and_owner_moves(
    ws_app: FastAPI, tc: TestClient, full_room: tuple[str, list[str]]
) -> None:
    room_id, tokens = full_room
    with connected(tc, room_id, tokens[1]) as watcher:
        with connected(tc, room_id, tokens[0]):
            pass  # chủ phòng (ghế 0) mất kết nối
        recv_until(watcher, lambda m: m["type"] == "room.state" and not m["payload"]["seats"][0]["connected"])
        later = datetime.now(UTC) + timedelta(minutes=5)
        assert tc.portal is not None
        tc.portal.call(sweep_once, ws_app.state.sessionmaker, ws_app.state.hub, later)
        state = recv_until(
            watcher, lambda m: m["type"] == "room.state" and not m["payload"]["seats"][0]["occupied"]
        )
    # Ghế 2, 3 chưa từng kết nối nên cũng hết hạn giữ ghế; ghế 1 đang kết nối thành chủ phòng.
    assert state["payload"]["ownerSeat"] == 1


def test_new_connection_replaces_old_one(tc: TestClient, full_room: tuple[str, list[str]]) -> None:
    room_id, tokens = full_room
    with connected(tc, room_id, tokens[0]) as first, connected(tc, room_id, tokens[0]):
        with pytest.raises(WebSocketDisconnect) as exc:
            recv_until(first, lambda m: False)
        assert exc.value.code == 4409


def test_rate_limit_and_oversized_frames(tc: TestClient, full_room: tuple[str, list[str]]) -> None:
    room_id, tokens = full_room
    with connected(tc, room_id, tokens[0]) as ws:
        ws.send_text("x" * 5000)
        assert recv_until(ws, of_type("error"))["payload"]["code"] == "PAYLOAD_TOO_LARGE"
        for _ in range(15):
            ws.send_json({"type": "ping", "requestId": rid(), "payload": {}})
        codes = [ws.receive_json() for _ in range(15)]
        assert any(m["type"] == "error" and m["payload"]["code"] == "RATE_LIMITED" for m in codes)


@pytest.mark.rule(147)
def test_owner_closing_room_disconnects_everyone(tc: TestClient, full_room: tuple[str, list[str]]) -> None:
    room_id, tokens = full_room
    with connected(tc, room_id, tokens[3]) as ws:
        assert tc.post(f"/api/rooms/{room_id}/close", headers=bearer(tokens[0])).status_code == 204
        assert recv_until(ws, of_type("room.closed"))["payload"]["reason"] == "OWNER_CLOSED"
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4000


def test_leaving_by_rest_disconnects_that_player_socket(
    tc: TestClient, full_room: tuple[str, list[str]]
) -> None:
    room_id, tokens = full_room
    with connected(tc, room_id, tokens[0]) as watcher, connected(tc, room_id, tokens[2]) as leaver:
        assert tc.post(f"/api/rooms/{room_id}/leave", headers=bearer(tokens[2])).status_code == 204
        with pytest.raises(WebSocketDisconnect) as exc:
            recv_until(leaver, lambda m: False)
        assert exc.value.code == 4001
        recv_until(watcher, lambda m: m["type"] == "room.state" and not m["payload"]["seats"][2]["occupied"])


@pytest.mark.rule(137)
def test_publishing_rules_notifies_open_rooms(tc: TestClient, full_room: tuple[str, list[str]]) -> None:
    room_id, tokens = full_room
    with connected(tc, room_id, tokens[0]) as ws:
        login = tc.post("/api/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
        headers = {"X-CSRF-Token": login.json()["csrfToken"]}
        draft = tc.post("/api/admin/rules/draft", json={}, headers=headers).json()
        config = draft["config"]
        config["turn"]["timeLimitSeconds"] = 45
        tc.put("/api/admin/rules/draft", json={"config": config}, headers={**headers, "If-Match": '"1"'})
        report = tc.post("/api/admin/rules/draft/validate", headers=headers).json()
        published = tc.post(
            "/api/admin/rules/draft/publish",
            json={"expectedHash": report["configHash"], "expectedActiveVersion": 1, "note": "Lượt 45 giây"},
            headers=headers,
        )
        assert published.status_code == 200, published.text
        update = recv_until(ws, of_type("rules.updated"))
        assert update["payload"]["version"] == 2
        assert update["payload"]["appliesFrom"] == "next_game"


# --- Chat nhanh bằng câu có sẵn ---


def test_chat_cooldown_unit() -> None:
    from app.realtime.chat import ChatCooldown

    now = [100.0]
    cooldown = ChatCooldown(10.0, clock=lambda: now[0])
    assert cooldown.check("a") == 0.0
    now[0] = 103.0
    assert cooldown.check("a") == pytest.approx(7.0)  # chưa đủ 10 giây
    assert cooldown.check("b") == 0.0  # người khác không bị ảnh hưởng
    now[0] = 110.5
    assert cooldown.check("a") == 0.0  # hết thời gian chờ


def test_chat_phrase_is_broadcast_to_everyone_with_sender_seat(
    tc: TestClient, full_room: tuple[str, list[str]]
) -> None:
    room_id, tokens = full_room
    with connected(tc, room_id, tokens[1]) as sender, connected(tc, room_id, tokens[3]) as other:
        sender.send_json({"type": "chat.send", "requestId": rid(), "payload": {"phrase": "hurry"}})
        for ws in (sender, other):
            message = recv_until(ws, of_type("chat.message"))
            assert message["payload"] == {"seat": 1, "phrase": "hurry"}


def test_chat_rejects_free_text_and_unknown_phrase(tc: TestClient, full_room: tuple[str, list[str]]) -> None:
    room_id, tokens = full_room
    with connected(tc, room_id, tokens[0]) as ws:
        for payload in ({"phrase": "xin chào mọi người"}, {"phrase": 5}, {}):
            ws.send_json({"type": "chat.send", "requestId": rid(), "payload": payload})
            assert recv_until(ws, of_type("error"))["payload"]["code"] == "PAYLOAD_INVALID"


def test_chat_cooldown_blocks_spam_even_after_reconnect(
    tc: TestClient, full_room: tuple[str, list[str]]
) -> None:
    room_id, tokens = full_room
    with connected(tc, room_id, tokens[0]) as ws:
        ws.send_json({"type": "chat.send", "requestId": rid(), "payload": {"phrase": "think"}})
        recv_until(ws, of_type("chat.message"))
        ws.send_json({"type": "chat.send", "requestId": rid(), "payload": {"phrase": "doomed"}})
        assert recv_until(ws, of_type("error"))["payload"]["code"] == "CHAT_COOLDOWN"
    with connected(tc, room_id, tokens[0]) as ws:  # vào lại cũng không reset được thời gian chờ
        ws.send_json({"type": "chat.send", "requestId": rid(), "payload": {"phrase": "doomed"}})
        assert recv_until(ws, of_type("error"))["payload"]["code"] == "CHAT_COOLDOWN"


def test_chat_new_preset_phrases_are_accepted(tc: TestClient, full_room: tuple[str, list[str]]) -> None:
    room_id, tokens = full_room
    for index, phrase in enumerate(("spade3", "mistake", "undo")):
        with connected(tc, room_id, tokens[index]) as ws:
            ws.send_json({"type": "chat.send", "requestId": rid(), "payload": {"phrase": phrase}})
            assert recv_until(ws, of_type("chat.message"))["payload"] == {"seat": index, "phrase": phrase}


def test_free_text_chat_is_cleaned_and_broadcast(tc: TestClient, full_room: tuple[str, list[str]]) -> None:
    room_id, tokens = full_room
    messy = "  Cho\te  đánh\nlại   được không \202e\u0007 "  # tab, xuống dòng, đảo chiều chữ, ký tự chuông
    with connected(tc, room_id, tokens[2]) as sender, connected(tc, room_id, tokens[0]) as other:
        sender.send_json({"type": "chat.send", "requestId": rid(), "payload": {"text": messy}})
        for ws in (sender, other):
            message = recv_until(ws, of_type("chat.message"))
            assert message["payload"] == {"seat": 2, "text": "Cho e đánh lại được không"}


def test_free_text_chat_validation(tc: TestClient, full_room: tuple[str, list[str]]) -> None:
    from app.realtime.chat import CHAT_MAX_LENGTH

    room_id, tokens = full_room
    bad_payloads: list[dict[str, object]] = [
        {"text": ""},
        {"text": "   \n\t "},  # chỉ có khoảng trắng
        {"text": "\202e\u0007"},  # chỉ có ký tự điều khiển
        {"text": "a" * (CHAT_MAX_LENGTH + 1)},  # quá dài
        {"text": 123},
        {"text": "xin chào", "phrase": "think"},  # gửi cả hai
    ]
    with connected(tc, room_id, tokens[0]) as ws:
        for payload in bad_payloads:
            ws.send_json({"type": "chat.send", "requestId": rid(), "payload": payload})
            assert recv_until(ws, of_type("error"))["payload"]["code"] == "PAYLOAD_INVALID"
        # Tin không hợp lệ không được tính vào thời gian chờ: gửi tin đúng độ dài tối đa vẫn được ngay.
        ws.send_json({"type": "chat.send", "requestId": rid(), "payload": {"text": "a" * CHAT_MAX_LENGTH}})
        assert recv_until(ws, of_type("chat.message"))["payload"]["text"] == "a" * CHAT_MAX_LENGTH


def test_free_text_and_preset_share_one_cooldown(tc: TestClient, full_room: tuple[str, list[str]]) -> None:
    room_id, tokens = full_room
    with connected(tc, room_id, tokens[0]) as ws:
        ws.send_json({"type": "chat.send", "requestId": rid(), "payload": {"text": "ơ"}})
        recv_until(ws, of_type("chat.message"))
        ws.send_json({"type": "chat.send", "requestId": rid(), "payload": {"phrase": "think"}})
        assert recv_until(ws, of_type("error"))["payload"]["code"] == "CHAT_COOLDOWN"
        ws.send_json({"type": "chat.send", "requestId": rid(), "payload": {"text": "lại nữa"}})
        assert recv_until(ws, of_type("error"))["payload"]["code"] == "CHAT_COOLDOWN"


def test_free_text_keeps_emoji_sequences_intact() -> None:
    from app.realtime.chat import normalize_chat_text

    family = "👨‍👩‍👧"
    assert normalize_chat_text(f"hi {family}") == f"hi {family}"
    assert normalize_chat_text(None) is None

"""Dựng bàn 4 người đã vào ván qua WebSocket (dùng chung cho test S4+)."""

import uuid
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from starlette.testclient import TestClient, WebSocketTestSession

from tlmn_engine.cards import THREE_CLUBS
from tlmn_engine.dealing import check_instant_win, deal, detect_redeal
from tlmn_engine.reducer import Timeout
from tlmn_engine.rules_config import default_config
from tlmn_testkit import deck_with

Msg = dict[str, Any]
RULES = default_config()
DECK = deck_with(
    ["", "", "", ""],
    lambda h: (
        check_instant_win(h, 0, RULES) is None and detect_redeal(h, RULES) is None and THREE_CLUBS in h[0]
    ),
)
HANDS = deal(DECK)  # ghế 0 giữ 3♣ → đi đầu


def rid() -> str:
    return str(uuid.uuid4())


def recv_until(ws: WebSocketTestSession, predicate: Callable[[Msg], bool], limit: int = 60) -> Msg:
    for _ in range(limit):
        message: Msg = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("Không nhận được message mong đợi")


def of_type(t: str) -> Callable[[Msg], bool]:
    return lambda m: m["type"] == t


@dataclass
class Table:
    tc: TestClient
    app: FastAPI
    room_id: str
    code: str
    tokens: list[str]
    sockets: list[WebSocketTestSession] = field(default_factory=list)
    started: list[Msg] = field(default_factory=list)  # game.started mỗi ghế nhận được
    stack: ExitStack = field(default_factory=ExitStack)

    def connect(self, seat: int) -> WebSocketTestSession:
        ws = self.stack.enter_context(self.tc.websocket_connect(f"/ws/rooms/{self.room_id}"))
        ws.send_json({"type": "auth", "requestId": rid(), "payload": {"token": self.tokens[seat]}})
        assert recv_until(ws, lambda m: m["type"] in ("ack", "error"))["type"] == "ack"
        return ws

    def send(
        self, seat: int, msg_type: str, payload: Msg, sequence: int, request_id: str | None = None
    ) -> Msg:
        self.sockets[seat].send_json(
            {"type": msg_type, "requestId": request_id or rid(), "sequence": sequence, "payload": payload}
        )
        return recv_until(self.sockets[seat], lambda m: m["type"] in ("ack", "error"))

    def run(self, coro_fn: Callable[..., Any], *args: Any) -> Any:
        assert self.tc.portal is not None
        return self.tc.portal.call(coro_fn, *args)

    @property
    def games(self) -> Any:
        return self.app.state.games

    def live_seq(self) -> int:
        live = self.games.live(uuid.UUID(self.room_id))
        return -1 if live is None else int(live.state.seq)

    def db(self, query: Any) -> Any:
        async def _run() -> Any:
            async with self.app.state.sessionmaker() as s:
                return (await s.execute(query)).all()

        return self.run(_run)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@contextmanager
def started_table(ws_app: FastAPI, deck: list[int] = DECK, players: int = 4) -> Iterator[Table]:
    ws_app.state.games.deck_source = lambda: list(deck)
    with TestClient(ws_app) as tc:
        tokens = [tc.post("/api/guests", json={"nickname": f"P{n}"}).json()["token"] for n in range(players)]
        room = tc.post("/api/rooms", headers=bearer(tokens[0])).json()
        if players != 4:  # chủ phòng đổi phòng sang chế độ 3 người trước khi mọi người vào
            changed = tc.patch(
                f"/api/rooms/{room['roomId']}/player-count",
                json={"playerCount": players},
                headers=bearer(tokens[0]),
            )
            assert changed.status_code == 200, changed.text
        for token in tokens[1:]:
            tc.post(f"/api/rooms/{room['roomId']}/join", json={}, headers=bearer(token))
        table = Table(tc, ws_app, room["roomId"], room["code"], tokens)
        with table.stack:
            table.sockets = [table.connect(seat) for seat in range(players)]
            for seat in range(players):
                table.send(seat, "room.ready", {"ready": True}, 0)
            # Server ack lệnh sẵn sàng trước rồi mới chia bài → chờ mọi người nhận game.started.
            table.started = [recv_until(ws, of_type("game.started")) for ws in table.sockets]
            yield table


def ready_all(table: Table) -> list[Msg]:
    """Mọi người trong phòng bấm sẵn sàng ván tiếp; trả về game.started mỗi ghế nhận được."""
    for seat in range(len(table.sockets)):
        table.send(seat, "room.ready", {"ready": True}, 0)
    return [recv_until(ws, of_type("game.started")) for ws in table.sockets]


def finish_by_timeouts(table: Table) -> Msg:
    """Cho ván chạy tới hết chỉ bằng hết giờ (server tự đánh / tự bỏ lượt); trả về game.ended."""
    room = uuid.UUID(table.room_id)
    for _ in range(400):
        if table.games.live(room) is None:
            break
        table.run(table.games.system_action, room, Timeout())
    return recv_until(table.sockets[0], of_type("game.ended"), limit=2000)

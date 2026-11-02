"""Kiểm thử tải: N bàn × 4 bot chơi đồng thời qua REST + WebSocket thật (docs/gd2/06 §2).

Đo độ trễ từ lúc gửi lệnh tới lúc nhận ack (= đã commit DB) và đếm lỗi.
Server cần nới giới hạn tra cứu phòng theo IP vì mọi bot đến từ cùng một máy:
  ROOM_LOOKUP_PER_MINUTE=100000 uv run uvicorn app.main:app --app-dir backend/src --port 8000
  uv run python tools/loadtest.py --base http://localhost:8000 --tables 100
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import websockets


@dataclass
class Stats:
    latencies: list[float] = field(default_factory=list)
    errors: dict[str, int] = field(default_factory=dict)
    games_finished: int = 0
    tables_failed: int = 0

    def error(self, code: str) -> None:
        self.errors[code] = self.errors.get(code, 0) + 1


def choose(state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    hand = sorted(state["yourHand"])
    top = state["trick"]["top"]
    if top is None:
        if state["firstMovePending"] and state["openingMode"] == "THREE_CLUBS" and 1 in hand:
            return "game.play", {"cards": [1]}
        return "game.play", {"cards": [hand[0]]}
    if len(top) == 1:
        higher = [c for c in hand if c > top[0]]
        if higher and random.random() < 0.7:
            return "game.play", {"cards": [higher[0]]}
    return "game.pass", {}


async def bot(seat: int, ws: Any, stats: Stats, games: int, think: tuple[float, float]) -> None:
    pending: dict[str, float] = {}
    finished = 0
    while finished < games:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
        kind = msg["type"]
        if kind in ("ack", "error") and msg.get("requestId") in pending:
            stats.latencies.append(time.perf_counter() - pending.pop(msg["requestId"]))
            if kind == "error" and msg["payload"]["code"] != "STALE_STATE":
                stats.error(msg["payload"]["code"])
        elif kind in ("game.started", "game.update", "game.state"):
            state = msg["payload"]["state"]
            if state["phase"] == "PLAYING" and state["current"] == seat:
                msg_type, payload = choose(state)
                await asyncio.sleep(random.uniform(*think))
                request_id = str(uuid.uuid4())
                pending[request_id] = time.perf_counter()
                await ws.send(
                    json.dumps(
                        {
                            "type": msg_type,
                            "requestId": request_id,
                            "sequence": msg["sequence"],
                            "payload": payload,
                        }
                    )
                )
        elif kind == "game.ended":
            finished += 1
            if seat == 0:
                stats.games_finished += 1
            if finished < games:
                await ws.send(
                    json.dumps(
                        {"type": "room.ready", "requestId": str(uuid.uuid4()), "payload": {"ready": True}}
                    )
                )


async def table(
    n: int, base: str, stats: Stats, games: int, think: tuple[float, float], gate: asyncio.Semaphore
) -> None:
    ws_base = base.replace("http", "ws", 1)
    try:
        async with (
            gate,
            httpx.AsyncClient(base_url=base, timeout=30) as http,
        ):  # dựng bàn từ từ, tránh dồn cục
            tokens = [
                (await http.post("/api/guests", json={"nickname": f"B{n}-{s}"})).json()["token"]
                for s in range(4)
            ]
            auth = [{"Authorization": f"Bearer {t}"} for t in tokens]
            room = (await http.post("/api/rooms", headers=auth[0])).json()
            for s in range(1, 4):
                (
                    await http.post(f"/api/rooms/{room['roomId']}/join", json={}, headers=auth[s])
                ).raise_for_status()
        sockets = []
        for token in tokens:
            ws = await websockets.connect(f"{ws_base}/ws/rooms/{room['roomId']}", max_queue=None)
            await ws.send(
                json.dumps({"type": "auth", "requestId": str(uuid.uuid4()), "payload": {"token": token}})
            )
            sockets.append(ws)
        for ws in sockets:
            await ws.send(
                json.dumps({"type": "room.ready", "requestId": str(uuid.uuid4()), "payload": {"ready": True}})
            )
        await asyncio.gather(*(bot(s, ws, stats, games, think) for s, ws in enumerate(sockets)))
        for ws in sockets:
            await ws.close()
    except Exception as exc:  # một bàn lỗi không làm dừng cả bài test
        stats.tables_failed += 1
        stats.error(type(exc).__name__)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--tables", type=int, default=100)
    parser.add_argument("--games", type=int, default=1, help="số ván mỗi bàn")
    parser.add_argument("--think-min", type=float, default=0.3)
    parser.add_argument("--think-max", type=float, default=1.0)
    args = parser.parse_args()

    stats = Stats()
    started = time.perf_counter()
    gate = asyncio.Semaphore(10)
    await asyncio.gather(
        *(
            table(n, args.base, stats, args.games, (args.think_min, args.think_max), gate)
            for n in range(args.tables)
        )
    )
    elapsed = time.perf_counter() - started
    lat = sorted(stats.latencies)

    def pct(p: float) -> float:
        return lat[min(len(lat) - 1, int(p * len(lat)))] * 1000 if lat else float("nan")

    print(
        f"Bàn: {args.tables} ({args.tables * 4} kết nối WebSocket), ván hoàn thành: {stats.games_finished}/"
        f"{args.tables * args.games}, bàn lỗi: {stats.tables_failed}"
    )
    print(f"Lệnh: {len(lat)} trong {elapsed:.1f}s ({len(lat) / elapsed:.1f} lệnh/giây)")
    if lat:
        print(
            f"Độ trễ ack (ms): p50 {pct(0.50):.1f} · p95 {pct(0.95):.1f} · p99 {pct(0.99):.1f}"
            f" · max {lat[-1] * 1000:.1f} · trung bình {statistics.mean(lat) * 1000:.1f}"
        )
    print(f"Lỗi: {stats.errors or 'không có'}")


if __name__ == "__main__":
    asyncio.run(main())

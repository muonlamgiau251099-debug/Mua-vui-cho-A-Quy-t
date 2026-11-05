"""Four real TCP/WebSocket clients complete one game on a supplied HTTP(S) origin.

Run: uv run python tools/smoke_memory.py https://SERVICE.onrender.com
Without an origin, starts and stops a local production ASGI server automatically.
Only test guests/rooms are created; the room is closed after verification.
"""

import asyncio
import contextlib
import json
import socket
import subprocess
import sys
import time
import uuid

import httpx
import websockets


def msg(kind, payload=None, sequence=0):
    return dict(type=kind, requestId=str(uuid.uuid4()), payload=payload or {}, sequence=sequence)


async def receive(ws, kind, request_id=None):
    for _ in range(100):
        data = json.loads(await asyncio.wait_for(ws.recv(), 10))
        if data["type"] == "error":
            raise AssertionError(data["payload"])
        if data["type"] == kind and (not request_id or data["requestId"] == request_id):
            return data
    raise AssertionError(f"Missing {kind}")


async def smoke(origin):
    async with httpx.AsyncClient(base_url=origin, timeout=90, trust_env=False) as client:
        health = await client.get("/api/health")
        health.raise_for_status()
        assert health.json()["storage"] == "memory"
        index = await client.get("/")
        assert index.status_code == 200 and "/assets/" in index.text
        players = []
        for i in range(4):
            r = await client.post("/api/guests", json={"nickname": f"Smoke {i}"})
            r.raise_for_status()
            p = r.json()
            p["headers"] = {"Authorization": f"Bearer {p['token']}"}
            players.append(p)
        r = await client.post("/api/rooms", headers=players[0]["headers"])
        r.raise_for_status()
        room = r.json()
        try:
            for p in players[1:]:
                r = await client.post(f"/api/rooms/{room['roomId']}/join", json={}, headers=p["headers"])
                r.raise_for_status()
            ws_url = (
                origin.replace("https://", "wss://").replace("http://", "ws://")
                + f"/ws/rooms/{room['roomId']}"
            )
            async with contextlib.AsyncExitStack() as stack:
                sockets = []
                for p in players:
                    ws = await stack.enter_async_context(
                        websockets.connect(ws_url, origin=origin, proxy=None)
                    )
                    await ws.send(json.dumps(msg("auth", {"token": p["token"]})))
                    await receive(ws, "ack")
                    sockets.append(ws)
                for ws in sockets:
                    await ws.send(json.dumps(msg("room.ready", {"ready": True})))
                views = [await receive(ws, "game.started") for ws in sockets]
                game_id = views[0]["payload"]["gameId"]
                actions = 0
                if views[0]["payload"]["state"]["phase"] == "PLAYING":
                    assert len({c for v in views for c in v["payload"]["state"]["yourHand"]}) == 52
                    assert all("hands" not in v["payload"]["state"] for v in views)
                for _ in range(600):
                    state = views[0]["payload"]["state"]
                    if state["phase"] != "PLAYING":
                        break
                    seat = state["current"]
                    hand = views[seat]["payload"]["state"]["yourHand"]
                    card = 1 if state["firstMovePending"] and 1 in hand else hand[0]
                    command = msg(
                        "game.pass" if state["trick"]["top"] else "game.play",
                        {} if state["trick"]["top"] else {"cards": [card]},
                        views[seat]["sequence"],
                    )
                    await sockets[seat].send(json.dumps(command))
                    await receive(sockets[seat], "ack", command["requestId"])
                    views = [await receive(ws, "game.update") for ws in sockets]
                    actions += 1
                    await asyncio.sleep(0.11)
                else:
                    raise AssertionError("Game did not finish")
                results = [await receive(ws, "game.ended") for ws in sockets]
                assert all(sum(r["payload"]["result"]["net"]) == 0 for r in results)
                r = await client.get(f"/api/games/{game_id}/replay", headers=players[0]["headers"])
                r.raise_for_status()
                assert r.json()["verified"]
                print(
                    json.dumps(
                        dict(
                            origin=origin,
                            status="passed",
                            players=4,
                            websocket=True,
                            fullGame=True,
                            actions=actions,
                            zeroSum=True,
                            privateHands=True,
                            replayVerified=True,
                        )
                    )
                )
        finally:
            await client.post(f"/api/rooms/{room['roomId']}/close", headers=players[0]["headers"])


def main():
    server = None
    try:
        if len(sys.argv) > 1:
            origin = sys.argv[1].rstrip("/")
        else:
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            sock.close()
            origin = f"http://127.0.0.1:{port}"
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-access-log",
                    "--ws-max-size",
                    "4096",
                ],
                stdout=subprocess.DEVNULL,
            )
            for _ in range(100):
                try:
                    with httpx.Client(trust_env=False) as client:
                        if client.get(origin + "/api/health").status_code == 200:
                            break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("ASGI server did not start")
        asyncio.run(smoke(origin))
    finally:
        if server:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()

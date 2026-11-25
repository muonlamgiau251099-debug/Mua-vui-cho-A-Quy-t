import asyncio
import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import update

from app.models import GuestPlayer


async def new_guest(client: httpx.AsyncClient, nickname: str = "Lan") -> dict[str, str]:
    response = await client.post("/api/guests", json={"nickname": nickname})
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['token']}", "id": body["guestId"]}


def auth(guest: dict[str, str]) -> dict[str, str]:
    return {"Authorization": guest["Authorization"]}


async def create_room(client: httpx.AsyncClient, guest: dict[str, str]) -> dict[str, str]:
    response = await client.post("/api/rooms", headers=auth(guest))
    assert response.status_code == 201, response.text
    return dict(response.json())


# --- Guest -----------------------------------------------------------------------------------------


async def test_guest_gets_token_once_and_can_read_profile(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/guests", json={"nickname": "  Minh   Anh  "})
    body = response.json()
    assert body["nickname"] == "Minh Anh"
    assert len(body["token"]) >= 40
    me = await client.get("/api/guests/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.json() == {"guestId": body["guestId"], "nickname": "Minh Anh", "currentRoom": None}
    assert "token" not in me.json()


@pytest.mark.parametrize("nickname", ["A", "x" * 21, "<script>", "   ", "___"])
async def test_invalid_nickname_is_rejected(client: httpx.AsyncClient, nickname: str) -> None:
    response = await client.post("/api/guests", json={"nickname": nickname})
    assert (response.status_code, response.json()["code"]) == (422, "NICKNAME_INVALID")


async def test_vietnamese_nickname_is_allowed(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/guests", json={"nickname": "Đức Thắng_99"})).status_code == 201


async def test_rename_guest(client: httpx.AsyncClient) -> None:
    guest = await new_guest(client)
    response = await client.patch("/api/guests/me", json={"nickname": "Lan Anh"}, headers=auth(guest))
    assert response.json()["nickname"] == "Lan Anh"


@pytest.mark.parametrize("header", [None, "Bearer sai-token", "Basic abc"])
async def test_missing_or_wrong_guest_token_is_401(client: httpx.AsyncClient, header: str | None) -> None:
    headers = {"Authorization": header} if header else {}
    response = await client.get("/api/guests/me", headers=headers)
    assert (response.status_code, response.json()["code"]) == (401, "GUEST_UNAUTHORIZED")


async def test_expired_guest_token_is_401(app: FastAPI, client: httpx.AsyncClient) -> None:
    guest = await new_guest(client)
    async with app.state.sessionmaker() as session:
        await session.execute(update(GuestPlayer).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        await session.commit()
    assert (await client.get("/api/guests/me", headers=auth(guest))).status_code == 401


@pytest.mark.rule(134)
async def test_guest_token_cannot_use_admin_rule_api(client: httpx.AsyncClient) -> None:
    guest = await new_guest(client)
    room = await create_room(client, guest)  # kể cả khi là chủ phòng
    assert room["seatNo"] == 0
    for method, path in [("GET", "/api/admin/rules/active"), ("POST", "/api/admin/rules/draft")]:
        response = await client.request(method, path, headers=auth(guest), json={})
        assert response.status_code == 401


# --- Phòng -----------------------------------------------------------------------------------------


async def test_create_room_seats_owner_at_seat_0_with_readable_code(client: httpx.AsyncClient) -> None:
    guest = await new_guest(client)
    room = await create_room(client, guest)
    assert re.fullmatch(r"[A-HJ-NP-Z2-9]{6}", room["code"])
    assert room["invitePath"] == f"/r/{room['code']}"
    me = (await client.get("/api/guests/me", headers=auth(guest))).json()
    assert me["currentRoom"] == {"roomId": room["roomId"], "code": room["code"], "seatNo": 0}
    again = await client.post("/api/rooms", headers=auth(guest))
    assert (again.status_code, again.json()["code"], again.json()["roomCode"]) == (
        409,
        "ALREADY_IN_ROOM",
        room["code"],
    )


async def test_room_preview_by_code_hides_tokens_and_guest_ids(client: httpx.AsyncClient) -> None:
    owner = await new_guest(client, "Chủ")
    room = await create_room(client, owner)
    state = (await client.get(f"/api/rooms/by-code/{room['code'].lower()}")).json()
    assert state["code"] == room["code"]
    assert state["ownerSeat"] == 0
    assert state["seats"][0]["nickname"] == "Chủ"
    assert [s["occupied"] for s in state["seats"]] == [True, False, False, False]
    assert state["rules"]["version"] == 1
    assert owner["id"] not in str(state)
    assert "token" not in str(state).lower()


@pytest.mark.rule(2)
async def test_room_has_exactly_four_seats(client: httpx.AsyncClient) -> None:
    owner = await new_guest(client, "P0")
    room = await create_room(client, owner)
    for n in range(1, 4):
        guest = await new_guest(client, f"P{n}")
        joined = await client.post(f"/api/rooms/{room['roomId']}/join", json={}, headers=auth(guest))
        assert joined.json()["seatNo"] == n
    fifth = await new_guest(client, "P5")
    response = await client.post(f"/api/rooms/{room['roomId']}/join", json={}, headers=auth(fifth))
    assert (response.status_code, response.json()["code"]) == (409, "ROOM_FULL")


async def test_join_specific_seat_and_rejoin_is_idempotent(client: httpx.AsyncClient) -> None:
    owner = await new_guest(client)
    room = await create_room(client, owner)
    guest = await new_guest(client, "Huy")
    url = f"/api/rooms/{room['roomId']}/join"
    assert (await client.post(url, json={"seatNo": 2}, headers=auth(guest))).json()["seatNo"] == 2
    assert (await client.post(url, json={}, headers=auth(guest))).json()[
        "seatNo"
    ] == 2  # vào lại không đổi ghế
    other = await new_guest(client, "Minh")
    taken = await client.post(url, json={"seatNo": 2}, headers=auth(other))
    assert taken.json()["code"] == "SEAT_TAKEN"


async def test_guest_cannot_sit_in_two_rooms(client: httpx.AsyncClient) -> None:
    room_a = await create_room(client, await new_guest(client, "An"))
    room_b = await create_room(client, await new_guest(client, "Bo"))
    guest = await new_guest(client, "Cu")
    await client.post(f"/api/rooms/{room_a['roomId']}/join", json={}, headers=auth(guest))
    response = await client.post(f"/api/rooms/{room_b['roomId']}/join", json={}, headers=auth(guest))
    assert (response.status_code, response.json()["code"]) == (409, "ALREADY_IN_ROOM")


async def test_two_guests_racing_for_last_seat_only_one_wins(client: httpx.AsyncClient) -> None:
    room = await create_room(client, await new_guest(client, "P0"))
    for n in (1, 2):
        await client.post(
            f"/api/rooms/{room['roomId']}/join", json={}, headers=auth(await new_guest(client, f"P{n}"))
        )
    racers = [await new_guest(client, "Xa"), await new_guest(client, "Ya")]
    results = await asyncio.gather(
        *(client.post(f"/api/rooms/{room['roomId']}/join", json={}, headers=auth(g)) for g in racers)
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    state = (await client.get(f"/api/rooms/by-code/{room['code']}")).json()
    assert all(s["occupied"] for s in state["seats"])


async def test_owner_leaving_passes_ownership_clockwise(client: httpx.AsyncClient) -> None:
    owner = await new_guest(client, "P0")
    room = await create_room(client, owner)
    p2 = await new_guest(client, "P2")
    await client.post(f"/api/rooms/{room['roomId']}/join", json={"seatNo": 2}, headers=auth(p2))
    assert (await client.post(f"/api/rooms/{room['roomId']}/leave", headers=auth(owner))).status_code == 204
    state = (await client.get(f"/api/rooms/by-code/{room['code']}")).json()
    assert state["ownerSeat"] == 2


async def test_last_player_leaving_closes_room(client: httpx.AsyncClient) -> None:
    owner = await new_guest(client)
    room = await create_room(client, owner)
    await client.post(f"/api/rooms/{room['roomId']}/leave", headers=auth(owner))
    response = await client.get(f"/api/rooms/by-code/{room['code']}")
    assert response.status_code == 404  # D5: tất cả rời → hủy bàn
    assert (await client.post("/api/rooms", headers=auth(owner))).status_code == 201  # tạo phòng mới được


@pytest.mark.rule(147)
async def test_only_owner_can_close_room(client: httpx.AsyncClient) -> None:
    owner = await new_guest(client, "Chủ")
    room = await create_room(client, owner)
    guest = await new_guest(client, "Khách")
    await client.post(f"/api/rooms/{room['roomId']}/join", json={}, headers=auth(guest))
    denied = await client.post(f"/api/rooms/{room['roomId']}/close", headers=auth(guest))
    assert (denied.status_code, denied.json()["code"]) == (403, "NOT_OWNER")
    assert (await client.post(f"/api/rooms/{room['roomId']}/close", headers=auth(owner))).status_code == 204
    assert (await client.get(f"/api/rooms/by-code/{room['code']}")).status_code == 404
    me = (await client.get("/api/guests/me", headers=auth(guest))).json()
    assert me["currentRoom"] is None  # ghế được giải phóng


async def test_owner_kicks_player_and_seat_is_freed(client: httpx.AsyncClient) -> None:
    owner = await new_guest(client, "Chủ")
    room = await create_room(client, owner)
    guest = await new_guest(client, "Khách")
    other = await new_guest(client, "Khác")
    url = f"/api/rooms/{room['roomId']}"
    await client.post(f"{url}/join", json={"seatNo": 2}, headers=auth(guest))
    await client.post(f"{url}/join", json={"seatNo": 3}, headers=auth(other))

    denied = await client.post(f"{url}/kick", json={"seatNo": 3}, headers=auth(guest))
    assert (denied.status_code, denied.json()["code"]) == (403, "NOT_OWNER")
    self_kick = await client.post(f"{url}/kick", json={"seatNo": 0}, headers=auth(owner))
    assert self_kick.json()["code"] == "CANNOT_KICK_SELF"
    empty = await client.post(f"{url}/kick", json={"seatNo": 1}, headers=auth(owner))
    assert (empty.status_code, empty.json()["code"]) == (404, "SEAT_EMPTY")

    assert (await client.post(f"{url}/kick", json={"seatNo": 2}, headers=auth(owner))).status_code == 204
    state = (await client.get(f"/api/rooms/by-code/{room['code']}")).json()
    assert [s["occupied"] for s in state["seats"]] == [True, False, False, True]
    assert (await client.get("/api/guests/me", headers=auth(guest))).json()["currentRoom"] is None


async def test_room_creation_is_rate_limited(app: FastAPI, client: httpx.AsyncClient) -> None:
    app.state.room_create_limiter.limit = 1
    guest = await new_guest(client)
    room = await create_room(client, guest)
    await client.post(f"/api/rooms/{room['roomId']}/leave", headers=auth(guest))
    response = await client.post("/api/rooms", headers=auth(guest))
    assert response.status_code == 429

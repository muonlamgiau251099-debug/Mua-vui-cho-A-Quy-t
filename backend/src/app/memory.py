"""Single-process RAM runtime. No database, filesystem state or external credentials.

Every mutation holds one lock (maximum 20 seated players); broadcasts are ordered
under that lock. Engine, projections, scoring and wire protocol match the original.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import secrets
import time
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import WebSocket

from app.errors import AppError
from app.realtime.chat import CHAT_PHRASES, ChatCooldown
from tlmn_engine.beats import MoveRejected
from tlmn_engine.cards import full_deck
from tlmn_engine.codec import action_from_json, action_to_json, state_from_json, state_hash, state_to_json
from tlmn_engine.dealing import DealResult, next_opening, start_game
from tlmn_engine.projection import project_private, project_public
from tlmn_engine.reducer import Forfeit, Pass, Play, Timeout, apply
from tlmn_engine.rules_config import RuleConfig, build_rules_snapshot, sha256_hex
from tlmn_engine.state import Phase

JST = ZoneInfo("Asia/Tokyo")
MAX_PLAYERS = 20
MAX_GUESTS = 200
MAX_GAMES = 100  # bounded replay/history memory for the free 512 MB instance
MAX_SESSIONS = 100
HOLD_SECONDS = 120


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def day_at(now: float) -> str:
    return datetime.fromtimestamp(now, JST).date().isoformat()


def uid() -> str:
    return str(uuid.uuid4())


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def envelope(
    kind: str,
    payload: dict,
    room_id: str | None = None,
    sequence: int | None = None,
    request_id: str | None = None,
) -> dict:
    return dict(
        type=kind, payload=payload, roomId=room_id, gameId=None, sequence=sequence, requestId=request_id
    )


def nickname(raw: str) -> str:
    value = " ".join(raw.split())
    if (
        not 2 <= len(value) <= 20
        or not any(c.isalnum() for c in value)
        or not all(c.isalnum() or c in " ._-" for c in value)
    ):
        raise AppError(422, "NICKNAME_INVALID", "Tên gồm 2–20 ký tự: chữ, số, khoảng trắng và . _ -")
    return value


@dataclass
class Guest:
    id: str
    name: str
    last_seen: float = field(default_factory=time.time)
    day: str = ""


@dataclass
class Seat:
    guest: str | None = None
    ready: bool = False
    connected: bool = False
    hold_until: float | None = None


@dataclass
class Room:
    id: str
    code: str
    owner: str
    seats: list[Seat] = field(default_factory=lambda: [Seat() for _ in range(4)])
    version: int = 1
    live: dict | None = None
    session_id: str | None = None
    session_no: int = 0
    pending_reset: bool = False
    conns: dict[str, WebSocket] = field(default_factory=dict)
    dedup: OrderedDict = field(default_factory=OrderedDict)
    chat: ChatCooldown = field(default_factory=ChatCooldown)


class MemoryStore:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = asyncio.Lock()
        self.day = day_at(clock())
        self.guests: dict[str, Guest] = {}  # hashed token -> guest; raw token never retained
        self.rooms: dict[str, Room] = {}
        self.games: OrderedDict[str, dict] = OrderedDict()
        self.sessions: OrderedDict[str, dict] = OrderedDict()
        self.rules = RuleConfig()
        self.rules_hash = sha256_hex(build_rules_snapshot(self.rules, 1))
        self.deck_source = self.shuffle
        self.latencies: deque[float] = deque(maxlen=1000)

    @staticmethod
    def shuffle():
        deck = full_deck()
        secrets.SystemRandom().shuffle(deck)
        return deck

    def authenticate(self, token: str | None) -> Guest:
        guest = self.guests.get(digest(token)) if isinstance(token, str) and len(token) <= 128 else None
        if guest is None:
            raise AppError(401, "GUEST_UNAUTHORIZED", "Phiên chơi đã hết hạn, hãy nhập tên lại")
        guest.last_seen = self.clock()
        return guest

    def create_guest(self, name: str) -> tuple[Guest, str]:
        name = nickname(name)
        if len(self.guests) >= MAX_GUESTS:
            seated = {s.guest for r in self.rooms.values() for s in r.seats}
            idle = sorted(
                (k for k, g in self.guests.items() if g.id not in seated),
                key=lambda k: self.guests[k].last_seen,
            )
            if not idle:
                raise AppError(503, "SERVER_FULL", "Máy chủ đang đầy, vui lòng thử lại")
            del self.guests[idle[0]]
        token = secrets.token_urlsafe(32)
        guest = Guest(uid(), name, self.clock(), self.day)
        self.guests[digest(token)] = guest
        return guest, token

    def names(self) -> dict[str, str]:
        return {g.id: g.name for g in self.guests.values()}

    def seat_of(self, guest_id: str) -> tuple[Room, int] | None:
        return next(
            ((r, n) for r in self.rooms.values() for n, s in enumerate(r.seats) if s.guest == guest_id), None
        )

    def profile(self, guest: Guest) -> dict:
        seated = self.seat_of(guest.id)
        return dict(
            guestId=guest.id,
            nickname=guest.name,
            currentRoom=(
                dict(roomId=seated[0].id, code=seated[0].code, seatNo=seated[1]) if seated else None
            ),
        )

    def get_room(self, room_id: str) -> Room:
        room = self.rooms.get(room_id)
        if room is None:
            raise AppError(404, "ROOM_NOT_FOUND", "Không tìm thấy phòng")
        return room

    def member(self, room: Room, guest: Guest) -> int:
        seat = next((n for n, s in enumerate(room.seats) if s.guest == guest.id), None)
        if seat is None:
            raise AppError(403, "NOT_IN_ROOM", "Bạn không ngồi trong phòng này")
        return seat

    def available(self, guest: Guest):
        old = self.seat_of(guest.id)
        if old:
            raise AppError(409, "ALREADY_IN_ROOM", "Bạn đang ngồi ở một phòng khác", roomCode=old[0].code)
        if sum(s.guest is not None for r in self.rooms.values() for s in r.seats) >= MAX_PLAYERS:
            raise AppError(503, "SERVER_FULL", "Đã đủ 20 người chơi, vui lòng thử lại sau")

    def create_room(self, guest: Guest) -> Room:
        self.available(guest)
        codes = {r.code for r in self.rooms.values()}
        while True:
            code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
            if code not in codes:
                break
        room = Room(uid(), code, guest.id)
        room.seats[0] = Seat(guest.id, hold_until=self.clock() + HOLD_SECONDS)
        self.rooms[room.id] = room
        return room

    def join(self, room: Room, guest: Guest, seat_no: int | None) -> int:
        existing = self.seat_of(guest.id)
        if existing and existing[0] is room:
            return existing[1]
        self.available(guest)
        if room.pending_reset or room.live:
            raise AppError(409, "GAME_IN_PROGRESS", "Phòng đang chơi; hãy đợi ván kết thúc")
        free = [n for n, s in enumerate(room.seats) if s.guest is None]
        if not free:
            raise AppError(409, "ROOM_FULL", "Phòng đã đủ 4 người")
        seat_no = free[0] if seat_no is None else seat_no
        if seat_no not in free:
            raise AppError(409, "SEAT_TAKEN", "Ghế này đã có người")
        room.seats[seat_no] = Seat(guest.id, hold_until=self.clock() + HOLD_SECONDS)
        room.version += 1
        return seat_no

    def summary(self, room: Room) -> dict | None:
        session = self.sessions.get(room.session_id)
        if session is None:
            return None
        return dict(
            sessionId=session["id"],
            sessionNo=session["no"],
            gamesPlayed=session["count"],
            scores=[dict(seat=i, nickname=session["names"][i], total=session["totals"][i]) for i in range(4)],
        )

    def room_state(self, room: Room, seat_no=None) -> dict:
        names = self.names()
        return dict(
            roomId=room.id,
            code=room.code,
            status="PLAYING" if room.live else "WAITING",
            version=room.version,
            ownerSeat=next((i for i, s in enumerate(room.seats) if s.guest == room.owner), None),
            gameId=room.live["id"] if room.live else None,
            seats=[
                dict(
                    seatNo=i,
                    occupied=s.guest is not None,
                    nickname=names.get(s.guest),
                    ready=s.ready,
                    connected=s.connected,
                    holdUntil=datetime.fromtimestamp(s.hold_until, UTC).isoformat() if s.hold_until else None,
                )
                for i, s in enumerate(room.seats)
            ],
            allReady=all(s.ready and s.connected for s in room.seats),
            yourSeat=seat_no,
            session=self.summary(room),
            rules=dict(version=1, configHash=self.rules_hash),
            resetPending=room.pending_reset,
        )

    async def send(self, ws: WebSocket, message: dict):
        try:
            await asyncio.wait_for(ws.send_json(message), 2)
        except Exception:
            # A stalled peer cannot block the entire 20-player runtime indefinitely.
            with contextlib.suppress(Exception):
                await asyncio.wait_for(ws.close(code=1013), 0.25)

    async def broadcast(self, room: Room, kind: str, payload: dict):
        await asyncio.gather(
            *(self.send(ws, envelope(kind, payload, room.id)) for ws in list(room.conns.values()))
        )

    async def broadcast_state(self, room: Room):
        await asyncio.gather(
            *(
                self.send(ws, envelope("room.state", self.room_state(room, n), room.id, room.version))
                for gid, ws in list(room.conns.items())
                for n, s in enumerate(room.seats)
                if s.guest == gid
            )
        )

    def header(self, game: dict) -> dict:
        return dict(
            gameId=game["id"], rules=dict(version=1, hash=self.rules_hash), deckCommitment=game["commitment"]
        )

    async def send_game(self, room: Room, kind: str, events: list):
        game = room.live
        if game is None:
            return
        for gid, ws in list(room.conns.items()):
            if gid in game["roster"]:
                seat = game["roster"].index(gid)
                await self.send(
                    ws,
                    envelope(
                        kind,
                        {
                            **self.header(game),
                            "events": events,
                            "state": project_private(game["state"], seat),
                        },
                        room.id,
                        game["state"].seq,
                    ),
                )

    def new_session(self, room: Room):
        old = self.sessions.get(room.session_id)
        if old:
            old.update(status="ENDED", endedAt=now_iso(), endReason="ROSTER_CHANGED")
        room.session_no += 1
        room.session_id = uid()
        names = self.names()
        self.sessions[room.session_id] = dict(
            id=room.session_id,
            room=room.id,
            code=room.code,
            no=room.session_no,
            roster=[s.guest for s in room.seats],
            names=[names.get(s.guest) for s in room.seats],
            totals=[0] * 4,
            count=0,
            games=[],
            status="ACTIVE",
            startedAt=now_iso(),
            endedAt=None,
            endReason=None,
            day=self.day,
        )
        self.prune()

    def prune(self):
        active_sessions = {r.session_id for r in self.rooms.values()}
        while len(self.sessions) > MAX_SESSIONS:
            key = next((k for k in self.sessions if k not in active_sessions), None)
            if key is None:
                break
            del self.sessions[key]
        while len(self.games) > MAX_GAMES:
            key = next((k for k, g in self.games.items() if g["state"].phase != Phase.PLAYING), None)
            if key is None:
                break
            del self.games[key]
            for session in self.sessions.values():
                if key in session["games"]:
                    session["games"].remove(key)

    async def start(self, room: Room):
        if (
            room.live
            or room.pending_reset
            or not all(s.guest and s.ready and s.connected for s in room.seats)
        ):
            return
        roster = [s.guest for s in room.seats]
        session = self.sessions.get(room.session_id)
        if session is None or session["status"] != "ACTIVE" or session["roster"] != roster:
            self.new_session(room)
            session = self.sessions[room.session_id]
        previous = next((self.games[k] for k in reversed(session["games"]) if k in self.games), None)
        winner = previous["winner"] if previous else None
        end_type = previous["state"].end_type if previous else None
        for _ in range(100):
            deck = self.deck_source()
            outcome = start_game(deck, next_opening(end_type, winner), self.rules, self.clock(), winner)
            if outcome.result != DealResult.REDEAL:
                break
        else:
            raise AppError(500, "REDEAL_LIMIT", "Chia lại quá nhiều lần")
        salt = secrets.token_hex(16)
        commitment = hashlib.sha256(f"{json.dumps(deck, separators=(',', ':'))}:{salt}".encode()).hexdigest()
        game = dict(
            id=uid(),
            state=outcome.state,
            initial=state_to_json(outcome.state),
            deck=deck,
            salt=salt,
            commitment=commitment,
            roster=roster,
            session=session["id"],
            winner=None,
            steps=[],
            startedAt=now_iso(),
            endedAt=None,
            number=session["count"] + 1,
            cancelReason=None,
            cumulative=None,
            initialHash=state_hash(outcome.state),
            day=self.day,
        )
        room.live = game
        self.games[game["id"]] = game
        session["games"].append(game["id"])
        for seat in room.seats:
            seat.ready = False
        room.version += 1
        await self.broadcast_state(room)
        await self.send_game(room, "game.started", outcome.events)
        if game["state"].phase != Phase.PLAYING:
            await self.finish(room)
        self.prune()

    async def action(self, room: Room, action, now: float | None = None):
        game = room.live
        now = self.clock() if now is None else now
        state, events = apply(game["state"], action, self.rules, now)
        game["state"] = state
        game["steps"].append(
            dict(
                seq=state.seq,
                kind=action_to_json(action)["kind"],
                seat=getattr(action, "seat", None),
                action=action_to_json(action),
                now=now,
                events=events,
                hash=state_hash(state),
            )
        )
        return events

    async def after_action(self, room: Room, events: list):
        await self.send_game(room, "game.update", events)
        if room.live["state"].phase != Phase.PLAYING:
            await self.finish(room)

    async def finish(self, room: Room):
        game = room.live
        state = game["state"]
        game["endedAt"] = now_iso()
        game["winner"] = next((n for n, p in enumerate(state.players) if p.rank == 1), None)
        session = self.sessions[game["session"]]
        if state.phase == Phase.FINISHED:
            session["count"] += 1
            session["totals"] = [a + b for a, b in zip(session["totals"], state.net(), strict=True)]
            game["cumulative"] = list(session["totals"])
        room.live = None
        room.version += 1
        await self.broadcast_state(room)
        await self.broadcast(
            room,
            "game.ended",
            {
                **self.header(game),
                "result": project_public(state),
                "deckReveal": dict(deck=game["deck"], salt=game["salt"]),
            },
        )
        if room.pending_reset:
            await self.close_room(room, "DAILY_RESET")
            self.purge_previous_day()

    async def close_room(self, room: Room, reason: str):
        if room.live:
            game = room.live
            game["cancelReason"] = reason
            game["endedAt"] = now_iso()
            room.live = None
            # Closing a room explicitly cancels its current game, as in the original.
            self.games.pop(game["id"], None)
            session = self.sessions.get(game["session"])
            if session and game["id"] in session["games"]:
                session["games"].remove(game["id"])
        await self.broadcast(room, "room.closed", {"reason": reason})
        for ws in list(room.conns.values()):
            with contextlib.suppress(Exception):
                await asyncio.wait_for(ws.close(code=4000, reason=reason), 0.5)
        room.conns.clear()
        self.rooms.pop(room.id, None)
        session = self.sessions.get(room.session_id)
        if session:
            session.update(status="ENDED", endedAt=now_iso(), endReason=reason)

    async def release(self, room: Room, seat_no: int):
        guest_id = room.seats[seat_no].guest
        if (
            room.live
            and guest_id in room.live["roster"]
            and room.live["state"].players[room.live["roster"].index(guest_id)].status == "ACTIVE"
        ):
            events = await self.action(room, Forfeit(room.live["roster"].index(guest_id)))
            await self.after_action(room, events)
            if room.id not in self.rooms:
                return
        ws = room.conns.pop(guest_id, None)
        if ws:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(ws.close(code=4001), 0.5)
        room.seats[seat_no] = Seat()
        room.version += 1
        if room.owner == guest_id:
            room.owner = next(
                (
                    room.seats[(seat_no + i) % 4].guest
                    for i in range(1, 4)
                    if room.seats[(seat_no + i) % 4].guest
                ),
                "",
            )
        if not any(s.guest for s in room.seats):
            await self.close_room(room, "EMPTY")
        else:
            await self.broadcast_state(room)

    async def reset_if_due(self):
        today = day_at(self.clock())
        if today == self.day:
            return
        self.day = today
        # Mark all before any await, so new rounds cannot start across midnight.
        for room in self.rooms.values():
            room.pending_reset = True
        for room in list(self.rooms.values()):
            if room.live:
                await self.broadcast(
                    room, "daily.resetPending", {"message": "Kết thúc ván rồi reset ngày mới."}
                )
            else:
                await self.close_room(room, "DAILY_RESET")
        self.purge_previous_day()

    def purge_previous_day(self):
        retained_rooms = [r for r in self.rooms.values() if r.pending_reset]
        keep_sessions = {r.session_id for r in retained_rooms}
        keep_games = {r.live["id"] for r in retained_rooms if r.live}
        # Pending games only need the current session and roster. Remove all old history.
        for key in list(self.games):
            if key not in keep_games and self.games[key]["day"] != self.day:
                del self.games[key]
        for key in list(self.sessions):
            if key not in keep_sessions:
                # Do not delete new-day sessions.
                s = self.sessions[key]
                if s["day"] != self.day:
                    del self.sessions[key]
        seated = {s.guest for r in self.rooms.values() for s in r.seats if s.guest}
        for key, guest in list(self.guests.items()):
            if guest.id not in seated and guest.day != self.day:
                del self.guests[key]

    async def tick(self):
        async with self.lock:
            await self.reset_if_due()
            for room in list(self.rooms.values()):
                if room.live:
                    deadline = room.live["state"].turn_deadline
                    if deadline is not None and deadline <= self.clock():
                        events = await self.action(room, Timeout(), self.clock())
                        await self.after_action(room, events)
                if room.id not in self.rooms:
                    continue
                for i, seat in enumerate(list(room.seats)):
                    if (
                        seat.guest
                        and not seat.connected
                        and seat.hold_until
                        and seat.hold_until <= self.clock()
                    ):
                        try:
                            await self.release(room, i)
                        except MoveRejected:
                            # Already finished/forfeited in this game: release after the game.
                            if not room.live:
                                room.seats[i] = Seat()
                        if room.id not in self.rooms:
                            break

    async def dispatch(self, room: Room, guest: Guest, ws: WebSocket, msg: dict) -> dict | None:
        req, kind, payload = msg["requestId"], msg["type"], msg.get("payload", {})
        seat = self.member(room, guest)
        key = (guest.id, req)
        if key in room.dedup:
            return room.dedup[key]
        try:
            if kind == "ping":
                response = envelope("pong", {"serverTime": self.clock()}, room.id, request_id=req)
            elif kind == "room.ready":
                if room.live or room.pending_reset:
                    raise AppError(409, "ROOM_NOT_WAITING", "Phòng không ở trạng thái chờ")
                if not isinstance(payload.get("ready"), bool):
                    raise AppError(422, "PAYLOAD_INVALID", "ready phải là true/false")
                room.seats[seat].ready = payload["ready"]
                room.version += 1
                await self.broadcast_state(room)
                response = envelope("ack", {"type": kind}, room.id, request_id=req)
                await self.send(ws, response)
                await self.start(room)
                # Sent before start, but remembered below; caller must not send twice.
                room.dedup[key] = response
                self.trim_dedup(room)
                return None
            elif kind in ("game.play", "game.pass"):
                game = room.live
                if not game:
                    raise AppError(409, "GAME_NOT_ACTIVE", "Phòng không có ván đang chơi")
                if msg.get("sequence") != game["state"].seq:
                    await self.send_game(room, "game.state", [])
                    raise AppError(409, "STALE_STATE", "Bàn vừa thay đổi, hãy thử lại")
                action = Pass(seat)
                if kind == "game.play":
                    cards = payload.get("cards")
                    if (
                        not isinstance(cards, list)
                        or not 1 <= len(cards) <= 13
                        or not all(type(c) is int and 0 <= c < 52 for c in cards)
                    ):
                        raise AppError(422, "PAYLOAD_INVALID", "cards phải là danh sách mã lá bài 0–51")
                    action = Play(seat, tuple(cards))
                events = await self.action(room, action)
                response = envelope(
                    "ack", {"type": kind, "sequence": game["state"].seq}, room.id, game["state"].seq, req
                )
                await self.send(ws, response)
                room.dedup[key] = response
                self.trim_dedup(room)
                await self.after_action(room, events)
                return None
            elif kind == "chat.send":
                phrase = payload.get("phrase")
                if not isinstance(phrase, str) or phrase not in CHAT_PHRASES:
                    raise AppError(422, "PAYLOAD_INVALID", "Câu chat không hợp lệ")
                if room.chat.check(guest.id) > 0:
                    raise AppError(429, "CHAT_COOLDOWN", "Chờ 10 giây giữa các câu chat")
                await self.broadcast(room, "chat.message", dict(seat=seat, phrase=phrase))
                response = envelope("ack", {"type": kind}, room.id, request_id=req)
            else:
                raise AppError(422, "UNKNOWN_TYPE", "Không hỗ trợ message này")
        except (AppError, MoveRejected) as exc:
            response = envelope("error", dict(code=exc.code, message=exc.message), room.id, request_id=req)
        room.dedup[key] = response
        self.trim_dedup(room)
        return response

    @staticmethod
    def trim_dedup(room: Room):
        while len(room.dedup) > 800:
            room.dedup.popitem(last=False)

    def session_json(self, session: dict, detail=False) -> dict:
        standings = [
            dict(
                seat=i,
                nickname=session["names"][i],
                total=session["totals"][i],
                gamesCounted=session["count"],
            )
            for i in range(4)
        ]
        standings.sort(key=lambda r: (-r["total"], r["seat"]))
        for place, row in enumerate(standings, 1):
            row["place"] = place
        result = dict(
            sessionId=session["id"],
            roomCode=session["code"],
            sessionNo=session["no"],
            status=session["status"],
            startedAt=session["startedAt"],
            endedAt=session["endedAt"],
            gamesPlayed=session["count"],
            standings=standings,
        )
        if detail:
            rows = []
            for key in session["games"]:
                game = self.games.get(key)
                if game is None:
                    continue
                state = game["state"]
                finished = state.phase == Phase.FINISHED
                rows.append(
                    dict(
                        gameId=key,
                        gameNo=game["number"],
                        status="FINISHED" if finished else "IN_PROGRESS",
                        endType=state.end_type,
                        cancelReason=game["cancelReason"],
                        ruleVersion=1,
                        startedAt=game["startedAt"],
                        endedAt=game["endedAt"],
                        ranks=[p.rank for p in state.players] if finished else None,
                        net=state.net() if finished else None,
                        cumulative=game["cumulative"],
                        transfers=[t.to_json() for t in state.transfers] if finished else [],
                    )
                )
            result.update(
                endReason=session["endReason"],
                games=rows,
                players=[dict(seat=i, nickname=n) for i, n in enumerate(session["names"])],
            )
        return result

    def replay(self, game_id: str, guest: Guest) -> dict:
        game = self.games.get(game_id)
        if game is None or guest.id not in game["roster"]:
            raise AppError(404, "GAME_NOT_FOUND", "Không tìm thấy ván")
        if game["state"].phase == Phase.PLAYING:
            raise AppError(409, "GAME_NOT_FINISHED", "Chỉ xem lại được sau khi ván kết thúc")
        session = self.sessions.get(game["session"])
        if not session:
            raise AppError(404, "SESSION_NOT_FOUND", "Lịch sử phiên đã hết hạn")

        def view(state):
            return {**project_public(state), "hands": [list(p.hand) for p in state.players]}

        state = state_from_json(game["initial"])
        initial = view(state)
        verified = state_hash(state) == game["initialHash"]
        steps = []
        for step in game["steps"]:
            state, events = apply(state, action_from_json(step["action"]), self.rules, step["now"])
            verified &= state_hash(state) == step["hash"]
            steps.append(
                dict(seq=state.seq, kind=step["kind"], seat=step["seat"], events=events, view=view(state))
            )
        verified &= state_hash(state) == state_hash(game["state"])
        return dict(
            gameId=game_id,
            gameNo=game["number"],
            sessionId=session["id"],
            roomCode=session["code"],
            status="FINISHED",
            endType=state.end_type,
            ruleVersion=1,
            deckCommitment=game["commitment"],
            deckSalt=game["salt"],
            verified=verified,
            players=[dict(seat=i, nickname=n) for i, n in enumerate(session["names"])],
            initial=initial,
            steps=steps,
        )

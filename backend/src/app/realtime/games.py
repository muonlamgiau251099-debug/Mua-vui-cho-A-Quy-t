"""Ván đang chơi theo phòng (RoomActor — ADR-003, ADR-006; docs/gd2/04 §3–4).

Mỗi lệnh: khóa phòng → dedup → kiểm tra baseSeq → engine.apply → 1 transaction DB (event, dedup,
last_seq có điều kiện, kết thúc ván) → commit → cập nhật bộ nhớ → ack → broadcast → hẹn giờ lượt.
Khôi phục ván sau khi server khởi động lại thuộc slice S6; ở S4 ván dang dở bị hủy khi khởi động.
"""

import asyncio
import hashlib
import json
import logging
import secrets
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.errors import AppError
from app.models import CommandDedup, Game, GameEvent, GameSession, GameSnapshot, Room, RoomSeat
from app.realtime.hub import Connection, RoomHub, envelope
from app.services import rooms as room_service
from app.services import rules as rule_service
from app.services import scores
from tlmn_engine.beats import MoveRejected
from tlmn_engine.cards import DECK_SIZE, full_deck
from tlmn_engine.codec import action_from_json, action_to_json, state_from_json, state_hash, state_to_json
from tlmn_engine.dealing import DealResult, next_opening, start_game
from tlmn_engine.projection import project_private, project_public
from tlmn_engine.reducer import Action, Forfeit, Pass, Play, ResumeTimer, Timeout, apply
from tlmn_engine.rules_config import RuleConfig, build_rules_snapshot, parse_rule_config, sha256_hex
from tlmn_engine.state import PLAYER_COUNTS, EndType, GameState, Phase

log = logging.getLogger(__name__)
MAX_REDEALS = 100
SNAPSHOT_EVERY = 20  # ngoài ra luôn snapshot khi đóng vòng (ADR-005)


class RecoveryError(Exception):
    pass


def action_kind(action: Action) -> str:
    return str(action_to_json(action)["kind"])


def secure_shuffled_deck() -> list[int]:
    """ID 153: server xáo bài bằng CSPRNG (secrets.SystemRandom)."""
    deck = full_deck()
    secrets.SystemRandom().shuffle(deck)
    return deck


def deck_commitment(deck: list[int], salt: str) -> str:
    """ADR-008 / G7: người chơi tự kiểm chứng sau ván: sha256(json(deck) + ":" + salt)."""
    return hashlib.sha256(f"{json.dumps(deck, separators=(',', ':'))}:{salt}".encode()).hexdigest()


@dataclass(eq=False)
class LiveGame:
    game_id: uuid.UUID
    room_id: uuid.UUID
    rules: RuleConfig
    rule_version: int
    rules_hash: str
    deck_commitment: str
    seat_guests: list[uuid.UUID]
    state: GameState
    timer: asyncio.Task[None] | None = field(default=None, repr=False)

    def seat_of(self, guest_id: uuid.UUID) -> int | None:
        return self.seat_guests.index(guest_id) if guest_id in self.seat_guests else None

    def header(self) -> dict[str, Any]:
        return {
            "gameId": str(self.game_id),
            "rules": {"version": self.rule_version, "hash": self.rules_hash},
            "deckCommitment": self.deck_commitment,
        }


class GameManager:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], hub: RoomHub) -> None:
        self._sessionmaker = sessionmaker
        self._hub = hub
        self._live: dict[uuid.UUID, LiveGame] = {}
        self.deck_source: Callable[[], list[int]] = (
            secure_shuffled_deck  # test có thể thay bằng bộ bài cố định
        )
        self._locks: defaultdict[uuid.UUID, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._latencies: deque[float] = deque(maxlen=5000)  # thời gian xử lý lệnh phía server (giây)

    def live(self, room_id: uuid.UUID) -> LiveGame | None:
        return self._live.get(room_id)

    def live_count(self) -> int:
        return len(self._live)

    def latency_stats(self) -> dict[str, float | int]:
        """Phân vị thời gian xử lý lệnh của người chơi (nhận lệnh → gửi ack), hiển thị ở /api/health."""
        values = sorted(self._latencies)
        if not values:
            return {"count": 0}

        def pct(p: float) -> float:
            return round(values[min(len(values) - 1, int(p * len(values)))] * 1000, 1)

        return {"count": len(values), "p50Ms": pct(0.5), "p95Ms": pct(0.95), "p99Ms": pct(0.99)}

    # --- Bắt đầu ván --------------------------------------------------------------------------------

    async def start_if_ready(self, room_id: uuid.UUID) -> bool:
        """ID 140: đủ người (3 hoặc 4) đã kết nối và sẵn sàng → server xáo bài và chia (ID 153)."""
        async with self._locks[room_id]:
            if room_id in self._live:
                return False
            async with self._sessionmaker() as s:
                started = await self._create_game(s, room_id)
            if started is None:
                return False
            live, outcome_events = started
            if live.state.phase == Phase.PLAYING:
                self._live[room_id] = live
                self._schedule_timer(live)
        await self._hub.broadcast_state(room_id)
        await self._send_each(live, "game.started", outcome_events)
        if live.state.phase != Phase.PLAYING:
            await self._send_ended(live)
        return True

    async def _create_game(
        self, s: AsyncSession, room_id: uuid.UUID
    ) -> tuple[LiveGame, list[dict[str, Any]]] | None:
        room = await s.scalar(select(Room).where(Room.id == room_id).with_for_update())
        if room is None or room.status != "WAITING":
            return None
        seats = list(
            await s.scalars(select(RoomSeat).where(RoomSeat.room_id == room_id).order_by(RoomSeat.seat_no))
        )
        everyone_ready = all(seat.conn_state == "CONNECTED" and seat.ready for seat in seats)
        if len(seats) not in PLAYER_COUNTS or not everyone_ready:
            return None
        guests = [seat.guest_id for seat in seats if seat.guest_id is not None]
        roster = [str(g) for g in guests]

        session = await s.scalar(
            select(GameSession).where(GameSession.room_id == room_id, GameSession.status == "ACTIVE")
        )
        if session is not None and session.roster != roster:  # đổi người → phiên mới (Q-P1-10)
            session.status, session.end_reason, session.ended_at = (
                "ENDED",
                "ROSTER_CHANGED",
                datetime.now(UTC),
            )
            await s.flush()
            session = None
        if session is None:
            last_no = await s.scalar(
                select(func.max(GameSession.session_no)).where(GameSession.room_id == room_id)
            )
            session = GameSession(room_id=room_id, session_no=(last_no or 0) + 1, roster=roster)
            s.add(session)
            await s.flush()

        previous = await s.scalar(
            select(Game).where(Game.session_id == session.id).order_by(Game.game_no.desc()).limit(1)
        )
        prev_end = EndType(previous.end_type) if previous and previous.end_type else None
        opening = next_opening(prev_end, previous.winner_seat if previous else None)

        active = await rule_service.get_active(s)  # ID 135, 137: ván mới lấy luật GLOBAL đang áp dụng
        assert active.version is not None
        config = parse_rule_config(active.config)
        snapshot = build_rules_snapshot(config, active.version)  # ID 156: chốt luật vào ván

        now = time.time()
        redeals = 0
        while True:
            deck = self.deck_source()
            outcome = start_game(
                deck, opening, config, now, previous.winner_seat if previous else None, players=len(seats)
            )
            if outcome.result != DealResult.REDEAL:
                break
            redeals += 1  # ID 58, 59: chia lại
            if redeals >= MAX_REDEALS:  # pragma: no cover - xác suất gần như bằng 0
                raise AppError(500, "REDEAL_LIMIT", "Chia lại quá nhiều lần")
        assert outcome.state is not None and len(deck) == DECK_SIZE

        salt = secrets.token_hex(16)
        state = outcome.state
        game = Game(
            session_id=session.id,
            room_id=room_id,
            game_no=(previous.game_no + 1) if previous else 1,
            rule_version=active.version,
            rules_snapshot=snapshot,
            rules_hash=sha256_hex(snapshot),
            opening_mode=state.opening_mode.value,  # có thể khác `opening` nếu người thắng ván trước vắng mặt
            deck=deck,
            deck_salt=salt,
            deck_commitment=deck_commitment(deck, salt),
            redeal_count=redeals,
            state_hash=state_hash(state),
        )
        s.add(game)
        await s.flush()
        s.add(GameSnapshot(game_id=game.id, seq=0, state=state_to_json(state), state_hash=game.state_hash))
        s.add(
            GameEvent(
                game_id=game.id,
                seq=0,
                type="GAME_STARTED",
                payload={
                    "now": now,
                    "openingMode": state.opening_mode.value,
                    "redeals": redeals,
                    "events": outcome.events,
                },
                state_hash=game.state_hash,
            )
        )
        for seat in seats:
            seat.ready = False  # ván sau mọi người bấm sẵn sàng lại
        room.state_version += 1
        if state.phase == Phase.PLAYING:
            room.status = "PLAYING"
        else:  # tới trắng: ván kết thúc ngay sau khi chia (ID 66)
            self._mark_finished(game, state)
            await scores.record_game_result(s, game, state, guests)
        await s.commit()

        live = LiveGame(
            game_id=game.id,
            room_id=room_id,
            rules=config,
            rule_version=active.version,
            rules_hash=game.rules_hash,
            deck_commitment=game.deck_commitment,
            seat_guests=guests,
            state=state,
        )
        return live, outcome.events

    @staticmethod
    def _mark_finished(game: Game, state: GameState) -> None:
        cancelled = state.phase == Phase.CANCELLED
        game.status = "CANCELLED" if cancelled else "FINISHED"
        game.end_type = state.end_type.value if state.end_type else None
        game.cancel_reason = "ALL_LEFT" if cancelled else None
        game.winner_seat = next((i for i, p in enumerate(state.players) if p.rank == 1), None)
        game.ended_at = datetime.now(UTC)

    # --- Lệnh của người chơi -------------------------------------------------------------------------

    async def handle_command(
        self, conn: Connection, msg_type: str, payload: dict[str, Any], request_id: str, base_seq: Any
    ) -> tuple[dict[str, Any], bool]:
        """Trả (phản hồi, đã_gửi). Lệnh hợp lệ: ack được gửi ngay sau commit, trước broadcast."""
        received = time.perf_counter()
        room_id, seat = conn.room_id, conn.seat_no
        req_uuid = uuid.UUID(request_id)
        async with self._locks[room_id]:
            live = self._live.get(room_id)
            if live is None:
                return self._error(conn, request_id, "GAME_NOT_ACTIVE", "Phòng không có ván đang chơi"), False
            async with self._sessionmaker() as s:
                stored = await s.get(CommandDedup, (live.game_id, seat, req_uuid))
                if stored is not None:  # gửi lặp: trả lại đúng phản hồi cũ, không xử lý lại (AC6)
                    return dict(stored.outcome), False
                action = self._parse_action(msg_type, payload, seat)
                if isinstance(action, dict):
                    return await self._reject(
                        s, live, conn, req_uuid, action["code"], action["message"]
                    ), False
                if base_seq != live.state.seq:  # G9: client đang dựa trên trạng thái cũ
                    stale = await self._reject(
                        s, live, conn, req_uuid, "STALE_STATE", "Bàn vừa thay đổi, hãy thử lại"
                    )
                    await conn.send(stale)  # báo lỗi trước, rồi gửi trạng thái mới nhất
                    await conn.send(self._state_message(live, conn.seat_no, "game.state", []))
                    return stale, True
                now = time.time()
                try:
                    new_state, events = apply(live.state, action, live.rules, now)
                except MoveRejected as exc:
                    return await self._reject(s, live, conn, req_uuid, exc.code, exc.message), False
                ack = envelope(
                    "ack",
                    {"type": msg_type, "sequence": new_state.seq},
                    room_id=room_id,
                    sequence=new_state.seq,
                    request_id=request_id,
                )
                await self._commit(s, live, new_state, events, action, seat, req_uuid, now, ack)
        await conn.send(ack)
        self._latencies.append(time.perf_counter() - received)
        await self._after_commit(live, events)
        return ack, True

    @staticmethod
    def _parse_action(msg_type: str, payload: dict[str, Any], seat: int) -> Action | dict[str, str]:
        if msg_type == "game.pass":
            return Pass(seat)
        cards = payload.get("cards")
        if (
            not isinstance(cards, list)
            or not 1 <= len(cards) <= 13
            or not all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c < DECK_SIZE for c in cards)
        ):
            return {"code": "PAYLOAD_INVALID", "message": "cards phải là danh sách mã lá bài 0–51"}
        return Play(seat, tuple(cards))

    def _error(self, conn: Connection, request_id: str, code: str, message: str) -> dict[str, Any]:
        return envelope(
            "error", {"code": code, "message": message}, room_id=conn.room_id, request_id=request_id
        )

    async def _reject(
        self, s: AsyncSession, live: LiveGame, conn: Connection, req: uuid.UUID, code: str, message: str
    ) -> dict[str, Any]:
        outcome = self._error(conn, str(req), code, message)
        outcome["payload"]["sequence"] = live.state.seq
        s.add(CommandDedup(game_id=live.game_id, seat=conn.seat_no, request_id=req, outcome=outcome))
        await s.commit()
        return outcome

    async def _commit(
        self,
        s: AsyncSession,
        live: LiveGame,
        new_state: GameState,
        events: list[dict[str, Any]],
        action: Action,
        seat: int | None,
        request_id: uuid.UUID | None,
        now: float,
        outcome: dict[str, Any] | None,
    ) -> None:
        """Ghi bền vững TRƯỚC khi ack/broadcast (ADR-006). Event lưu đủ input để replay (ID 149)."""
        new_hash = state_hash(new_state)
        s.add(
            GameEvent(
                game_id=live.game_id,
                seq=new_state.seq,
                type=action_kind(action),
                actor_seat=seat,
                request_id=request_id,
                payload={"now": now, "action": action_to_json(action), "events": events},
                state_hash=new_hash,
            )
        )
        if new_state.seq % SNAPSHOT_EVERY == 0 or any(e["type"] == "TRICK_CLOSED" for e in events):
            s.add(
                GameSnapshot(
                    game_id=live.game_id,
                    seq=new_state.seq,
                    state=state_to_json(new_state),
                    state_hash=new_hash,
                )
            )
        if request_id is not None and seat is not None and outcome is not None:
            s.add(CommandDedup(game_id=live.game_id, seat=seat, request_id=request_id, outcome=outcome))
        result = await s.execute(
            update(Game)
            .where(Game.id == live.game_id, Game.last_seq == live.state.seq)  # chặn ghi chồng
            .values(last_seq=new_state.seq, state_hash=new_hash)
        )
        if result.rowcount != 1:  # type: ignore[attr-defined]
            await s.rollback()
            raise AppError(409, "STALE_STATE", "Trạng thái ván đã thay đổi")
        if new_state.phase != Phase.PLAYING:
            game = await s.get(Game, live.game_id)
            assert game is not None
            self._mark_finished(game, new_state)
            await scores.record_game_result(s, game, new_state, live.seat_guests)  # cùng transaction
            room = await s.scalar(select(Room).where(Room.id == live.room_id).with_for_update())
            if room is not None and room.status == "PLAYING":
                room.status = "WAITING"
                room.state_version += 1
        await s.commit()
        live.state = new_state

    async def _after_commit(self, live: LiveGame, events: list[dict[str, Any]]) -> None:
        await self._send_each(live, "game.update", events)
        if live.state.phase == Phase.PLAYING:
            self._schedule_timer(live)
            return
        await self._finish_live(live)

    async def _finish_live(self, live: LiveGame) -> None:
        self._live.pop(live.room_id, None)
        self._cancel_timer(live)
        await self._hub.broadcast_state(live.room_id)
        await self._send_ended(live)

    # --- Hệ thống: hết giờ, thoát ván, hủy ván ----------------------------------------------------------

    async def system_action(
        self, room_id: uuid.UUID, action: Action, *, expected_seq: int | None = None
    ) -> bool:
        async with self._locks[room_id]:
            live = self._live.get(room_id)
            if live is None or (expected_seq is not None and live.state.seq != expected_seq):
                return False
            now = time.time()
            if isinstance(action, Timeout):
                now = max(now, live.state.turn_deadline or now)
            try:
                new_state, events = apply(live.state, action, live.rules, now)
            except MoveRejected:
                return False
            seat = action.seat if isinstance(action, Forfeit) else None
            async with self._sessionmaker() as s:
                await self._commit(s, live, new_state, events, action, seat, None, now, None)
        await self._after_commit(live, events)
        return True

    async def forfeit(self, room_id: uuid.UUID, guest_id: uuid.UUID) -> bool:
        """Thoát giữa ván / hết thời gian giữ ghế khi đang chơi (ID 87, 145; D9)."""
        live = self._live.get(room_id)
        seat = live.seat_of(guest_id) if live else None
        if live is None or seat is None or live.state.players[seat].status != "ACTIVE":
            return False
        return await self.system_action(room_id, Forfeit(seat))

    async def cancel(self, room_id: uuid.UUID, reason: str) -> bool:
        """Hủy ván (ID 109): Admin, chủ phòng đóng phòng, hoặc lỗi hệ thống. Điểm của ván bị bỏ (Q-P1-9)."""
        async with self._locks[room_id]:
            live = self._live.pop(room_id, None)
            if live is None:
                return False
            self._cancel_timer(live)
            async with self._sessionmaker() as s:
                await s.execute(
                    update(Game)
                    .where(Game.id == live.game_id)
                    .values(
                        status="CANCELLED",
                        end_type="CANCELLED",
                        cancel_reason=reason,
                        ended_at=datetime.now(UTC),
                    )
                )
                await s.execute(
                    update(Room)
                    .where(Room.id == room_id, Room.status == "PLAYING")
                    .values(status="WAITING", state_version=Room.state_version + 1)
                )
                await s.commit()
        await self._hub.send_room_event(
            room_id, "game.cancelled", {"gameId": str(live.game_id), "reason": reason}
        )
        await self._hub.broadcast_state(room_id)
        return True

    def room_of_game(self, game_id: uuid.UUID) -> uuid.UUID | None:
        return next((room for room, live in self._live.items() if live.game_id == game_id), None)

    async def recover_on_startup(self) -> tuple[int, int]:
        """Khôi phục ván dang dở sau khi server khởi động lại (AC7; ADR-005, ADR-014).

        Trạng thái = snapshot gần nhất + áp lại các action sau đó; phải khớp hash đã lưu. Mọi ghế coi như
        mất kết nối (được giữ ghế); lượt hiện tại được cấp lại đủ thời gian (G5).
        Không khôi phục được → hủy ván.
        """
        recovered = failed = 0
        async with self._sessionmaker() as s:
            games = list(await s.scalars(select(Game).where(Game.status == "IN_PROGRESS")))
        for game in games:
            try:
                live = await self._load_live(game)
            except Exception:
                log.exception("Không khôi phục được ván %s — hủy ván", game.id)
                await self._cancel_in_db(game.id, game.room_id, "RECOVERY_FAILED")
                failed += 1
                continue
            self._live[game.room_id] = live
            async with self._sessionmaker() as s:
                await room_service.mark_all_disconnected(s, game.room_id)
            await self.system_action(game.room_id, ResumeTimer())
            recovered += 1
        async with self._sessionmaker() as s:  # phòng "đang chơi" mà không còn ván → về chờ
            await s.execute(
                update(Room)
                .where(
                    Room.status == "PLAYING",
                    ~exists().where(Game.room_id == Room.id, Game.status == "IN_PROGRESS"),
                )
                .values(status="WAITING", state_version=Room.state_version + 1)
            )
            await s.commit()
        return recovered, failed

    async def _load_live(self, game: Game) -> LiveGame:
        async with self._sessionmaker() as s:
            snap = await s.scalar(
                select(GameSnapshot)
                .where(GameSnapshot.game_id == game.id)
                .order_by(GameSnapshot.seq.desc())
                .limit(1)
            )
            if snap is None:
                raise RecoveryError("Ván không có snapshot")
            later = list(
                await s.scalars(
                    select(GameEvent)
                    .where(GameEvent.game_id == game.id, GameEvent.seq > snap.seq)
                    .order_by(GameEvent.seq)
                )
            )
            session = await s.get(GameSession, game.session_id)
        assert session is not None
        rules = parse_rule_config(game.rules_snapshot["config"])
        state = state_from_json(snap.state)
        for event in later:
            state, _ = apply(state, action_from_json(event.payload["action"]), rules, event.payload["now"])
        if state.seq != game.last_seq or state_hash(state) != game.state_hash:
            raise RecoveryError("Trạng thái dựng lại không khớp hash đã lưu")
        return LiveGame(
            game_id=game.id,
            room_id=game.room_id,
            rules=rules,
            rule_version=game.rule_version,
            rules_hash=game.rules_hash,
            deck_commitment=game.deck_commitment,
            seat_guests=[uuid.UUID(g) for g in session.roster],
            state=state,
        )

    async def _cancel_in_db(self, game_id: uuid.UUID, room_id: uuid.UUID, reason: str) -> None:
        async with self._sessionmaker() as s:
            await s.execute(
                update(Game)
                .where(Game.id == game_id)
                .values(
                    status="CANCELLED", end_type="CANCELLED", cancel_reason=reason, ended_at=datetime.now(UTC)
                )
            )
            await s.execute(
                update(Room)
                .where(Room.id == room_id, Room.status == "PLAYING")
                .values(status="WAITING", state_version=Room.state_version + 1)
            )
            await s.commit()

    # --- Đồng hồ lượt (ID 141) ------------------------------------------------------------------------

    def _schedule_timer(self, live: LiveGame) -> None:
        self._cancel_timer(live)
        deadline, seq = live.state.turn_deadline, live.state.seq
        if deadline is None:
            return

        async def fire() -> None:
            await asyncio.sleep(max(0.0, deadline - time.time()))
            try:
                await self.system_action(live.room_id, Timeout(), expected_seq=seq)
            except Exception:  # pragma: no cover - không để task timer chết âm thầm
                log.exception("Lỗi xử lý hết giờ lượt")

        live.timer = asyncio.create_task(fire())

    @staticmethod
    def _cancel_timer(live: LiveGame) -> None:
        if live.timer is not None and live.timer is not asyncio.current_task():
            live.timer.cancel()
        live.timer = None

    async def shutdown(self) -> None:
        for live in list(self._live.values()):
            self._cancel_timer(live)

    # --- Gửi dữ liệu (chỉ qua projection — ID 152) ------------------------------------------------------

    def _state_message(
        self, live: LiveGame, seat: int, msg_type: str, events: list[dict[str, Any]]
    ) -> dict[str, Any]:
        payload = {**live.header(), "events": events, "state": project_private(live.state, seat)}
        return envelope(msg_type, payload, room_id=live.room_id, sequence=live.state.seq)

    async def _send_each(self, live: LiveGame, msg_type: str, events: list[dict[str, Any]]) -> None:
        for conn in self._hub.connections(live.room_id):
            seat = live.seat_of(conn.guest_id)
            if seat is not None:
                await conn.send(self._state_message(live, seat, msg_type, events))

    async def _send_ended(self, live: LiveGame) -> None:
        async with self._sessionmaker() as s:
            game = await s.get(Game, live.game_id)
        reveal = {"deck": game.deck, "salt": game.deck_salt} if game else None
        # Ván đã kết thúc: project_public lộ toàn bộ bài để đối chiếu thối; G7: kèm bộ bài + salt để
        # người chơi tự kiểm chứng deckCommitment công bố lúc chia.
        payload = {**live.header(), "result": project_public(live.state), "deckReveal": reveal}
        await self._hub.send_room_event(live.room_id, "game.ended", payload)

    async def send_snapshot(self, conn: Connection) -> None:
        """Vào lại phòng khi đang có ván: gửi trạng thái riêng của đúng người đó (ID 143)."""
        live = self._live.get(conn.room_id)
        seat = live.seat_of(conn.guest_id) if live else None
        if live is not None and seat is not None:
            await conn.send(self._state_message(live, seat, "game.state", []))

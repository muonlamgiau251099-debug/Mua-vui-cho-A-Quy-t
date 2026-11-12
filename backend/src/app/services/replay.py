"""Xem lại ván (ID 154) và đối soát tranh chấp (ID 155) từ event log + snapshot luật (ID 149, 156)."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import Game, GameEvent, GameResult, GameSession, GameSnapshot, GuestPlayer, Room
from app.realtime.games import deck_commitment
from tlmn_engine.codec import action_from_json, state_from_json, state_hash
from tlmn_engine.projection import project_public
from tlmn_engine.reducer import apply
from tlmn_engine.rules_config import parse_rule_config, sha256_hex
from tlmn_engine.state import GameState


@dataclass(frozen=True, slots=True)
class Step:
    event: GameEvent
    state: GameState
    hash_ok: bool


@dataclass(frozen=True, slots=True)
class Replay:
    game: Game
    session: GameSession
    initial: GameState
    steps: list[Step]

    @property
    def final(self) -> GameState:
        return self.steps[-1].state if self.steps else self.initial

    @property
    def matches_stored_hash(self) -> bool:
        return state_hash(self.final) == self.game.state_hash and all(step.hash_ok for step in self.steps)


async def build_replay(s: AsyncSession, game_id: uuid.UUID) -> Replay:
    game = await s.get(Game, game_id)
    if game is None:
        raise AppError(404, "GAME_NOT_FOUND", "Không tìm thấy ván")
    session = await s.get(GameSession, game.session_id)
    assert session is not None
    snap = await s.get(GameSnapshot, (game.id, 0))
    if snap is None:
        raise AppError(409, "REPLAY_UNAVAILABLE", "Ván này được tạo trước khi có chức năng xem lại")
    events = list(
        await s.scalars(
            select(GameEvent).where(GameEvent.game_id == game.id, GameEvent.seq > 0).order_by(GameEvent.seq)
        )
    )
    rules = parse_rule_config(game.rules_snapshot["config"])  # luật đã chốt của chính ván này
    state = initial = state_from_json(snap.state)
    steps = []
    for event in events:
        state, _ = apply(state, action_from_json(event.payload["action"]), rules, event.payload["now"])
        steps.append(Step(event, state, event.state_hash is None or event.state_hash == state_hash(state)))
    return Replay(game, session, initial, steps)


def _view(state: GameState) -> dict[str, Any]:
    """Ván đã kết thúc nên được lộ bài cả 4 người ở mọi bước."""
    return {**project_public(state), "hands": [list(p.hand) for p in state.players]}


async def _nicknames(s: AsyncSession, roster: list[str]) -> list[dict[str, Any]]:
    rows = dict(
        (
            await s.execute(select(GuestPlayer.id, GuestPlayer.nickname).where(GuestPlayer.id.in_(roster)))
        ).all()
    )
    return [{"seat": seat, "nickname": rows.get(uuid.UUID(g))} for seat, g in enumerate(roster)]


async def replay_for_player(s: AsyncSession, guest_id: uuid.UUID, game_id: uuid.UUID) -> dict[str, Any]:
    game = await s.get(Game, game_id)
    session = await s.get(GameSession, game.session_id) if game else None
    if game is None or session is None or str(guest_id) not in session.roster:
        raise AppError(404, "GAME_NOT_FOUND", "Không tìm thấy ván")  # không lộ ván của người khác
    if game.status == "IN_PROGRESS":
        raise AppError(409, "GAME_NOT_FINISHED", "Chỉ xem lại được sau khi ván kết thúc")  # ID 152
    replay = await build_replay(s, game_id)
    room_code = await s.scalar(select(Room.code).where(Room.id == game.room_id))
    return {
        "gameId": str(game.id),
        "gameNo": game.game_no,
        "sessionId": str(session.id),
        "roomCode": room_code,
        "status": game.status,
        "endType": game.end_type,
        "cancelReason": game.cancel_reason,
        "ruleVersion": game.rule_version,
        "rulesHash": game.rules_hash,
        "deckCommitment": game.deck_commitment,
        "deck": game.deck,
        "deckSalt": game.deck_salt,
        "verified": replay.matches_stored_hash,
        "players": await _nicknames(s, session.roster),
        "initial": _view(replay.initial),
        "steps": [
            {
                "seq": step.event.seq,
                "kind": step.event.type,
                "seat": step.event.actor_seat,
                "events": step.event.payload["events"],
                "view": _view(step.state),
            }
            for step in replay.steps
        ],
    }


async def audit_for_admin(s: AsyncSession, game_id: uuid.UUID) -> dict[str, Any]:
    """ID 155: bằng chứng cho tranh chấp — log đầy đủ + kiểm tra độc lập từng điểm."""
    replay = await build_replay(s, game_id)
    game = replay.game
    result = await s.get(GameResult, game.id)
    raw = list(await s.scalars(select(GameEvent).where(GameEvent.game_id == game.id).order_by(GameEvent.seq)))
    verification = {
        "deckCommitmentOk": deck_commitment(game.deck, game.deck_salt) == game.deck_commitment,
        "rulesHashOk": sha256_hex(game.rules_snapshot) == game.rules_hash,
        "replayMatchesStoredHash": replay.matches_stored_hash,
        "badEventHashes": [step.event.seq for step in replay.steps if not step.hash_ok],
        "resultMatchesReplay": result is None or result.net == replay.final.net(),
        "zeroSum": sum(replay.final.net()) == 0,
    }
    return {
        "gameId": str(game.id),
        "roomId": str(game.room_id),
        "sessionId": str(game.session_id),
        "status": game.status,
        "endType": game.end_type,
        "cancelReason": game.cancel_reason,
        "ruleVersion": game.rule_version,
        "rulesSnapshot": game.rules_snapshot,
        "deck": game.deck,
        "deckSalt": game.deck_salt,
        "deckCommitment": game.deck_commitment,
        "players": await _nicknames(s, replay.session.roster),
        "finalNet": replay.final.net(),
        "storedNet": result.net if result else None,
        "verification": verification,
        "events": [
            {
                "seq": e.seq,
                "type": e.type,
                "actorSeat": e.actor_seat,
                "requestId": str(e.request_id) if e.request_id else None,
                "stateHash": e.state_hash,
                "createdAt": e.created_at.isoformat(),
                "payload": e.payload,
            }
            for e in raw
        ],
    }

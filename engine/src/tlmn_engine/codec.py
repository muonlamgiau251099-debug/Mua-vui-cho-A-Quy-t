"""Chuyển GameState ↔ JSON và hash trạng thái (ADR-005: snapshot + replay; docs/gd2/04 §5)."""

from typing import Any

from tlmn_engine.cards import THREE_CLUBS
from tlmn_engine.combos import classify
from tlmn_engine.reducer import Action, Forfeit, Pass, Play, ResumeTimer, Timeout
from tlmn_engine.rules_config import sha256_hex
from tlmn_engine.state import (
    ChopLink,
    EndType,
    GameState,
    OpeningMode,
    Phase,
    PlayerState,
    PlayerStatus,
    Transfer,
    Trick,
)


def state_to_json(s: GameState) -> dict[str, Any]:
    t = s.trick
    data: dict[str, Any] = {
        "players": [
            {"hand": list(p.hand), "playedCount": p.played_count, "status": p.status.value, "rank": p.rank}
            for p in s.players
        ],
        "openingMode": s.opening_mode.value,
        "current": s.current,
        "trick": {
            "leader": t.leader,
            "top": list(t.top.cards) if t.top else None,
            "topSeat": t.top_seat,
            "topIsChop": t.top_is_chop,
            "passed": sorted(t.passed),
            "chain": [[link.chopper, link.victim, link.value] for link in t.chain],
            "heoCarry": t.heo_carry,
        },
        "firstMovePending": s.first_move_pending,
        "turnDeadline": s.turn_deadline,
        "phase": s.phase.value,
        "endType": s.end_type.value if s.end_type else None,
        "played": list(s.played),
        "finishOrder": list(s.finish_order),
        "transfers": [t.to_json() for t in s.transfers],
        "seq": s.seq,
    }
    # Chỉ ghi khi khác mặc định: snapshot / hash của ván 4 người cũ (mở bằng 3♣, chia hết 52 lá) không đổi.
    if s.opening_card != THREE_CLUBS:
        data["openingCard"] = s.opening_card
    if s.undealt:
        data["undealt"] = list(s.undealt)
    return data


def state_from_json(d: dict[str, Any]) -> GameState:
    t = d["trick"]
    top = classify(t["top"]) if t["top"] is not None else None
    if t["top"] is not None and top is None:
        raise ValueError("Snapshot có bài trên bàn không hợp lệ")
    return GameState(
        players=[
            PlayerState(list(p["hand"]), p["playedCount"], PlayerStatus(p["status"]), p["rank"])
            for p in d["players"]
        ],
        opening_mode=OpeningMode(d["openingMode"]),
        current=d["current"],
        trick=Trick(
            leader=t["leader"],
            top=top,
            top_seat=t["topSeat"],
            top_is_chop=t["topIsChop"],
            passed=set(t["passed"]),
            chain=[ChopLink(*link) for link in t["chain"]],
            heo_carry=t.get("heoCarry", 0),  # snapshot cũ chưa có trường này
        ),
        first_move_pending=d["firstMovePending"],
        turn_deadline=d["turnDeadline"],
        phase=Phase(d["phase"]),
        end_type=EndType(d["endType"]) if d["endType"] else None,
        played=list(d["played"]),
        finish_order=list(d["finishOrder"]),
        transfers=[
            Transfer(x["from"], x["to"], x["amount"], x["reason"], x["detail"]) for x in d["transfers"]
        ],
        seq=d["seq"],
        undealt=list(d.get("undealt", [])),  # snapshot cũ (ván 4 người) chưa có trường này
        opening_card=d.get("openingCard", THREE_CLUBS),
    )


def state_hash(s: GameState) -> str:
    return sha256_hex(state_to_json(s))


def action_to_json(action: Action) -> dict[str, Any]:
    match action:
        case Play(seat, cards):
            return {"kind": "PLAY", "seat": seat, "cards": list(cards)}
        case Pass(seat):
            return {"kind": "PASS", "seat": seat}
        case Timeout():
            return {"kind": "TIMEOUT"}
        case Forfeit(seat):
            return {"kind": "FORFEIT", "seat": seat}
        case ResumeTimer():
            return {"kind": "RESUME"}
    raise TypeError(f"Action không hỗ trợ: {action!r}")


def action_from_json(d: dict[str, Any]) -> Action:
    kind = d["kind"]
    if kind == "PLAY":
        return Play(d["seat"], tuple(d["cards"]))
    if kind == "PASS":
        return Pass(d["seat"])
    if kind == "TIMEOUT":
        return Timeout()
    if kind == "FORFEIT":
        return Forfeit(d["seat"])
    if kind == "RESUME":
        return ResumeTimer()
    raise ValueError(f"Action không hỗ trợ: {kind}")

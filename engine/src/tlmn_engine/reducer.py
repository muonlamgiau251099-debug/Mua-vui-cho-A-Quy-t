"""Reducer duy nhất của ván: apply(state, action, rules, now) -> (state mới, events).

Thuần, deterministic: không đọc đồng hồ, không random; state cũ không bị sửa (docs/gd2/03 §5).
"""

from dataclasses import dataclass
from typing import Any

from tlmn_engine.beats import MoveRejected, can_beat, can_interrupt
from tlmn_engine.cards import THREE_CLUBS, THREE_SPADES
from tlmn_engine.combos import Combo, ComboType, classify
from tlmn_engine.rules_config import RuleConfig
from tlmn_engine.scoring import instant_win_transfers, normal_end_transfers, settle_chain
from tlmn_engine.state import (
    SEATS,
    ChopLink,
    EndType,
    GameState,
    Phase,
    PlayerStatus,
    Trick,
    clockwise_after,
    clockwise_from,
)

Events = list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class Play:
    seat: int
    cards: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Pass:
    seat: int


@dataclass(frozen=True, slots=True)
class Timeout:
    """Server gửi khi hết giờ lượt hiện tại (ID 141, 142; D9, D13)."""


@dataclass(frozen=True, slots=True)
class Forfeit:
    """Thoát giữa ván hoặc hết thời gian giữ ghế (ID 87, 145; D9, R6)."""

    seat: int


@dataclass(frozen=True, slots=True)
class ResumeTimer:
    """Server khởi động lại và khôi phục ván: cấp lại đủ thời gian cho lượt hiện tại (G5)."""


Action = Play | Pass | Timeout | Forfeit | ResumeTimer


def apply(state: GameState, action: Action, rules: RuleConfig, now: float) -> tuple[GameState, Events]:
    if state.phase != Phase.PLAYING:
        raise MoveRejected("GAME_NOT_ACTIVE", "Ván đã kết thúc")
    s = state.clone()
    events: Events = []
    match action:
        case Play(seat, cards):
            _play(s, rules, now, seat, cards, events, auto=False)
        case Pass(seat):
            _pass(s, rules, now, seat, events, auto=False)
        case Timeout():
            if s.turn_deadline is None or now < s.turn_deadline:
                raise MoveRejected("TIMER_NOT_EXPIRED", "Chưa hết giờ lượt")
            seat = s.current
            if s.trick.top is None:  # D13: người mở vòng hết giờ → tự đánh lá đơn nhỏ nhất
                card = THREE_CLUBS if must_include_three_clubs(s, rules, seat) else min(s.players[seat].hand)
                _play(s, rules, now, seat, (card,), events, auto=True)
            else:  # D9: hết giờ = mất lượt
                _pass(s, rules, now, seat, events, auto=True)
        case Forfeit(seat):
            _forfeit(s, rules, now, seat, events)
        case ResumeTimer():
            s.turn_deadline = now + rules.turn.timeLimitSeconds
            events.append({"type": "TURN_RESUMED", "seat": s.current, "deadline": s.turn_deadline})
    s.seq += 1
    return s, events


# --- Các bước xử lý -----------------------------------------------------------------------------


def must_include_three_clubs(s: GameState, rules: RuleConfig, seat: int) -> bool:
    """ID 8: nước đầu tiên của ván mở bằng 3♣ phải chứa 3♣ — chỉ khi người đi đầu đang giữ 3♣
    (người giữ 3♣ có thể đã thoát ván trước khi đánh; khi đó người kế tiếp được đánh tự do)."""
    return (
        s.first_move_pending
        and s.opening_mode == "THREE_CLUBS"
        and rules.opening.mustIncludeThreeClubs
        and THREE_CLUBS in s.players[seat].hand
    )


def _start_turn(s: GameState, rules: RuleConfig, now: float, events: Events) -> None:
    s.turn_deadline = now + rules.turn.timeLimitSeconds
    events.append({"type": "TURN_STARTED", "seat": s.current, "deadline": s.turn_deadline})


def _play(
    s: GameState,
    rules: RuleConfig,
    now: float,
    seat: int,
    cards: tuple[int, ...],
    events: Events,
    *,
    auto: bool,
) -> None:
    if not 0 <= seat < SEATS or s.players[seat].status != PlayerStatus.ACTIVE:
        raise MoveRejected("NOT_ACTIVE", "Bạn không còn trong ván")
    hand = s.players[seat].hand
    if len(set(cards)) != len(cards) or not set(cards) <= set(hand):
        raise MoveRejected("CARDS_NOT_IN_HAND", "Lá bài không có trên tay")
    combo = classify(cards)
    if combo is None:
        raise MoveRejected("INVALID_COMBINATION", "Bộ bài không hợp lệ")

    trick = s.trick
    result = can_beat(
        rules,
        trick.top,
        combo,
        must_include_three_clubs=must_include_three_clubs(s, rules, seat),
        top_is_chop=trick.top_is_chop,
        someone_finished=s.someone_finished(),
    )
    interrupt = False
    if seat != s.current or seat in trick.passed:
        if trick.top is not None and seat != trick.top_seat and can_interrupt(rules, combo, result):
            interrupt = True  # ID 42, R8: 4 đôi thông chặt ngoài lượt
        else:
            raise MoveRejected("NOT_YOUR_TURN", "Chưa đến lượt bạn")

    for card in combo.cards:
        hand.remove(card)
    s.played.extend(combo.cards)
    s.players[seat].played_count += len(combo.cards)
    if result.scores_as_chop:
        assert trick.top_seat is not None
        trick.chain.append(ChopLink(seat, trick.top_seat, result.target_value))
    trick.top, trick.top_seat, trick.top_is_chop = combo, seat, result.scores_as_chop
    trick.passed.discard(seat)  # G12: chặt ngoài lượt → tham gia lại vòng
    s.first_move_pending = False
    events.append(
        {
            "type": "PLAYED",
            "seat": seat,
            "cards": list(combo.cards),
            "combo": combo.type.value,
            "kind": result.kind.value,
            "chop": result.scores_as_chop,
            "interrupt": interrupt,
            "auto": auto,
            "remaining": len(hand),
        }
    )
    if not hand:
        _finish_player(s, rules, now, seat, combo, events)
        if s.phase != Phase.PLAYING:
            return
    _advance(s, rules, now, seat, events)


def _pass(s: GameState, rules: RuleConfig, now: float, seat: int, events: Events, *, auto: bool) -> None:
    if seat != s.current:
        raise MoveRejected("NOT_YOUR_TURN", "Chưa đến lượt bạn")
    if s.trick.top is None:
        raise MoveRejected("LEADER_CANNOT_PASS", "Người mở vòng phải đánh bài")  # ID 12 + X1
    s.trick.passed.add(seat)  # ID 13: đã bỏ thì không được đánh lại tới vòng mới
    events.append({"type": "PASSED", "seat": seat, "auto": auto})
    _advance(s, rules, now, seat, events)


def _advance(s: GameState, rules: RuleConfig, now: float, after: int, events: Events) -> None:
    trick = s.trick
    if trick.top is None:  # người mở vòng vừa thoát ván: người kế tiếp mở vòng
        s.current = next(x for x in clockwise_after(after) if s.players[x].status == PlayerStatus.ACTIVE)
        trick.leader = s.current
        _start_turn(s, rules, now, events)
        return
    responders = [
        x
        for x in clockwise_after(after)
        if s.players[x].status == PlayerStatus.ACTIVE and x not in trick.passed and x != trick.top_seat
    ]
    if responders:
        s.current = responders[0]
        _start_turn(s, rules, now, events)
    else:
        _close_trick(s, rules, now, events)


def _settle_open_chain(s: GameState) -> dict[str, Any] | None:
    transfer = settle_chain(s.trick.chain)
    s.trick.chain = []
    if transfer is None:
        return None
    s.transfers.append(transfer)
    return transfer.to_json()


def _close_trick(s: GameState, rules: RuleConfig, now: float, events: Events) -> None:
    top = s.trick.top_seat
    assert top is not None
    chop = _settle_open_chain(s)
    if s.players[top].status == PlayerStatus.ACTIVE:
        leader = top  # ID 14
    else:  # ID 105, D2: người đánh cuối đã hết bài/thoát → hưởng sái cho người kế tiếp
        leader = next(x for x in clockwise_after(top) if s.players[x].status == PlayerStatus.ACTIVE)
    events.append({"type": "TRICK_CLOSED", "winner": top, "nextLeader": leader, "chop": chop})
    s.trick = Trick(leader)
    s.current = leader
    _start_turn(s, rules, now, events)


def _used_ranks(s: GameState) -> set[int]:
    return {p.rank for p in s.players if p.rank is not None}


def _next_top_rank(s: GameState) -> int:
    return min(r for r in range(1, SEATS + 1) if r not in _used_ranks(s))


def _next_bottom_rank(s: GameState) -> int:
    return max(r for r in range(1, SEATS + 1) if r not in _used_ranks(s))


def _finish_player(
    s: GameState, rules: RuleConfig, now: float, seat: int, last: Combo, events: Events
) -> None:
    player = s.players[seat]
    player.rank = _next_top_rank(s)  # ID 15, 16, 99–102
    player.status = PlayerStatus.FINISHED
    s.finish_order.append(seat)
    events.append({"type": "PLAYER_FINISHED", "seat": seat, "rank": player.rank})

    if (
        player.rank == 1
        and rules.special.blindThreeSpades
        and last.type == ComboType.SINGLE
        and last.cards == (THREE_SPADES,)
    ):  # ID 89, D10, D14: về nhất bằng 3♠ đánh đơn → hết ván ngay
        _end_game(s, rules, EndType.BLIND_THREE_SPADES, events, winners=[seat])
        return

    if player.rank == 1 and rules.penalty.cong.enabled:  # ID 68, 69, D7
        cong = [
            x
            for x in clockwise_from(seat)
            if s.players[x].status == PlayerStatus.ACTIVE and s.players[x].played_count == 0
        ]
        for x in cong:
            s.players[x].status = PlayerStatus.CONG
            s.players[x].rank = _next_bottom_rank(s)
        if cong:
            events.append({"type": "CONG", "seats": cong, "allTable": len(cong) == SEATS - 1})

    _maybe_end(s, rules, events)


def _maybe_end(s: GameState, rules: RuleConfig, events: Events) -> None:
    active = s.active_seats()
    if len(active) > 1:
        return
    for x in active:  # ID 104, D15: chơi tới khi còn 1 người
        s.players[x].rank = _next_top_rank(s)
        s.players[x].status = PlayerStatus.FINISHED
        s.finish_order.append(x)
    _end_game(s, rules, EndType.NORMAL, events)


def _forfeit(s: GameState, rules: RuleConfig, now: float, seat: int, events: Events) -> None:
    player = s.players[seat]
    if player.status != PlayerStatus.ACTIVE:
        raise MoveRejected("NOT_ACTIVE", "Người chơi không còn trong ván")
    player.status = PlayerStatus.FORFEITED
    player.rank = _next_bottom_rank(s)  # D9: người thoát trước xếp thấp hơn
    events.append({"type": "PLAYER_FORFEITED", "seat": seat, "rank": player.rank})
    if all(p.status == PlayerStatus.FORFEITED for p in s.players):
        s.phase = Phase.CANCELLED  # D5: tất cả cùng thoát → hủy
        s.end_type = EndType.CANCELLED
        events.append({"type": "GAME_CANCELLED", "reason": "ALL_LEFT"})
        return
    if len(s.active_seats()) <= 1:
        _maybe_end(s, rules, events)
        return
    if s.current == seat:
        _advance(s, rules, now, seat, events)


def _end_game(
    s: GameState, rules: RuleConfig, end_type: EndType, events: Events, winners: list[int] | None = None
) -> None:
    _settle_open_chain(s)
    s.phase = Phase.FINISHED
    s.end_type = end_type
    s.turn_deadline = None
    if end_type == EndType.BLIND_THREE_SPADES:
        assert winners is not None
        for x, p in enumerate(s.players):
            if x not in winners:
                p.rank = SEATS  # D10: 3 người còn lại thua
        s.transfers.extend(
            instant_win_transfers(
                winners, rules, rules.scoring.blindThreeSpadesPerLoser, "BLIND_THREE_SPADES"
            )
        )
    else:
        s.transfers.extend(normal_end_transfers(s, rules))
    events.append(
        {
            "type": "GAME_ENDED",
            "endType": end_type.value,
            "ranks": [p.rank for p in s.players],
            "statuses": [p.status.value for p in s.players],
            "transfers": [t.to_json() for t in s.transfers],
            "net": s.net(),
            "hands": [list(p.hand) for p in s.players],
        }
    )

"""Công cụ dựng ván cho test engine: chỉ định bài trên tay từng ghế, phần còn lại coi như đã đánh."""

from collections.abc import Callable
from typing import Any

from tlmn_engine.cards import DECK_SIZE, THREE_CLUBS, parse_cards
from tlmn_engine.combos import Combo, classify
from tlmn_engine.invariants import check_invariants
from tlmn_engine.reducer import Action, Forfeit, Pass, Play, Timeout, apply
from tlmn_engine.rules_config import RuleConfig, default_config, parse_rule_config
from tlmn_engine.state import GameState, OpeningMode, PlayerState, Trick

RULES = default_config()


def rules_with(**changes: Any) -> RuleConfig:
    """rules_with(**{"chop.allowChain": False}) → RuleConfig mới."""
    data = default_config().model_dump(mode="json")
    for path, value in changes.items():
        node = data
        *parents, leaf = path.split(".")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return parse_rule_config(data)


def make_game(
    hands: list[str],
    *,
    current: int = 0,
    opening: OpeningMode = OpeningMode.WINNER_LEADS,
    first_move: bool = False,
    played_counts: list[int] | None = None,
    top: str | None = None,
    top_seat: int | None = None,
    undealt: str | None = None,
    opening_card: str | None = None,
) -> GameState:
    """hands: 4 chuỗi như '3C 4D 2H'. Lá không nằm trên tay ai được tính là đã đánh.

    played_counts mặc định = 13 − số lá trên tay (tay đủ 13 lá → chưa đánh lá nào → có thể bị cóng).
    """
    parsed = [sorted(parse_cards(h)) for h in hands]
    held = [c for h in parsed for c in h]
    assert len(held) == len(set(held)), "Lá bài bị trùng giữa các tay"
    rest = parse_cards(undealt) if undealt else []  # bài thừa không chia (ván 3 người)
    assert not set(rest) & set(held), "Bài thừa trùng với bài trên tay"
    played = [c for c in range(DECK_SIZE) if c not in held and c not in rest]
    counts = played_counts or [13 - len(h) for h in parsed]
    players = [PlayerState(h, played_count=n) for h, n in zip(parsed, counts, strict=True)]
    trick = Trick(current)
    if top is not None:
        combo = classify(parse_cards(top))
        assert combo is not None
        trick.top, trick.top_seat = combo, top_seat
    state = GameState(
        players=players,
        opening_mode=opening,
        current=current,
        trick=trick,
        first_move_pending=first_move,
        opening_card=parse_cards(opening_card)[0] if opening_card else THREE_CLUBS,
        turn_deadline=30.0,
        played=played,
        undealt=sorted(rest),
    )
    assert sum(counts) == len(played), "played_counts phải cộng lại bằng số lá đã đánh"
    check_invariants(state)
    return state


class Table:
    """Chạy liên tiếp các action; kiểm tra bất biến sau mỗi bước; lưu toàn bộ event."""

    def __init__(self, state: GameState, rules: RuleConfig = RULES, now: float = 0.0) -> None:
        self.state = state
        self.rules = rules
        self.now = now
        self.events: list[dict[str, Any]] = []

    def do(self, action: Action) -> list[dict[str, Any]]:
        self.state, events = apply(self.state, action, self.rules, self.now)
        check_invariants(self.state)
        self.events.extend(events)
        return events

    def play(self, seat: int, cards: str) -> list[dict[str, Any]]:
        return self.do(Play(seat, tuple(parse_cards(cards))))

    def pass_(self, seat: int) -> list[dict[str, Any]]:
        return self.do(Pass(seat))

    def timeout(self) -> list[dict[str, Any]]:
        self.now = max(self.now, self.state.turn_deadline or 0.0)
        return self.do(Timeout())

    def forfeit(self, seat: int) -> list[dict[str, Any]]:
        return self.do(Forfeit(seat))

    def of_type(self, event_type: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["type"] == event_type]

    @property
    def net(self) -> list[int]:
        return self.state.net()


def combo(cards: str) -> Combo:
    result = classify(parse_cards(cards))
    assert result is not None, cards
    return result


def deck_with(fixed: list[str], predicate: Callable[[list[list[int]]], bool] = lambda _: True) -> list[int]:
    """Bộ bài 52 lá: ghế s nhận các lá trong fixed[s], phần còn lại chia ngẫu nhiên (seed cố định)
    cho đủ 13 lá; thử lần lượt các seed tới khi predicate(hands) đúng."""
    import random

    parsed = [parse_cards(f) for f in fixed]
    used = {c for h in parsed for c in h}
    assert len(used) == sum(len(h) for h in parsed), "Lá bài bị trùng giữa các tay"
    rest = [c for c in range(DECK_SIZE) if c not in used]
    for seed in range(5000):
        pool = list(rest)
        random.Random(seed).shuffle(pool)
        hands = []
        for h in parsed:
            need = 13 - len(h)
            hands.append(sorted(h + pool[:need]))
            pool = pool[need:]
        if predicate(hands):
            return [c for h in hands for c in h]
    raise AssertionError("Không tìm được bộ bài thỏa điều kiện")

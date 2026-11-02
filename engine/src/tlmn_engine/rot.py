"""Thối heo / thối hàng (ID 72–77, 84; D8, D11, G4, G11).

- Heo tính từng lá: đen 100, đỏ 200 (đôi heo = tổng 2 heo; tứ quý 2 = 4 heo).
- Hàng (tứ quý, 3 đôi thông, 4 đôi thông) tách từ các lá không phải 2 sao cho tổng phạt lớn nhất,
  không lá nào bị tính hai lần (đôi thông 5–6 đôi được tách thành các bộ 3/4 đôi).
"""

from collections import Counter
from dataclasses import dataclass
from functools import cache

from tlmn_engine.cards import TWO_RANK, is_red, is_two, rank
from tlmn_engine.rules_config import RuleConfig


@dataclass(frozen=True, slots=True)
class RotItem:
    kind: str  # BLACK_TWO | RED_TWO | FOUR_KIND | THREE_PAIR_SEQ | FOUR_PAIR_SEQ
    cards: tuple[int, ...]
    value: int


# Một bộ hàng: (kind, rank bắt đầu, số rank, số lá dùng mỗi rank)
_Piece = tuple[str, int, int, int]


def _pieces(counts: tuple[int, ...], rules: RuleConfig) -> list[_Piece]:
    rot, out = rules.penalty.rot, []
    for r in range(TWO_RANK):
        if rot.fourKind and counts[r] == 4:
            out.append(("FOUR_KIND", r, 1, 4))
        for length, kind, enabled in (
            (3, "THREE_PAIR_SEQ", rot.threePairSeq),
            (4, "FOUR_PAIR_SEQ", rot.fourPairSeq),
        ):
            if enabled and r + length <= TWO_RANK and all(counts[r + i] >= 2 for i in range(length)):
                out.append((kind, r, length, 2))
    return out


def _value(kind: str, rules: RuleConfig) -> int:
    v = rules.scoring.rotComboValue
    return {"FOUR_KIND": v.fourKind, "THREE_PAIR_SEQ": v.threePairSeq, "FOUR_PAIR_SEQ": v.fourPairSeq}[kind]


def _best_combos(counts: tuple[int, ...], rules: RuleConfig) -> list[_Piece]:
    @cache
    def best(state: tuple[int, ...]) -> tuple[int, int, int, tuple[_Piece, ...]]:
        # (tổng giá trị, số lá dùng, -số bộ, các bộ): giá trị lớn nhất; hòa thì ưu tiên bộ dài
        # (vd 4 đôi thông thay vì 3 đôi thông bên trong), rồi ít bộ hơn. Deterministic.
        result: tuple[int, int, int, tuple[_Piece, ...]] = (0, 0, 0, ())
        for piece in _pieces(state, rules):
            kind, start, length, per_rank = piece
            rest = list(state)
            for i in range(length):
                rest[start + i] -= per_rank
            value, used, neg_count, pieces = best(tuple(rest))
            candidate = (
                value + _value(kind, rules),
                used + length * per_rank,
                neg_count - 1,
                (piece, *pieces),
            )
            if candidate[:3] > result[:3]:
                result = candidate
        return result

    return list(best(counts)[3])


def compute_rot(hand: list[int], rules: RuleConfig) -> list[RotItem]:
    rot, scoring = rules.penalty.rot, rules.scoring
    items: list[RotItem] = []
    for card in sorted(c for c in hand if is_two(c)):
        if is_red(card) and rot.redTwo:
            items.append(RotItem("RED_TWO", (card,), scoring.redTwoValue))
        elif not is_red(card) and rot.blackTwo:
            items.append(RotItem("BLACK_TWO", (card,), scoring.blackTwoValue))

    by_rank: dict[int, list[int]] = {}
    for card in sorted(hand):
        by_rank.setdefault(rank(card), []).append(card)
    counter = Counter(rank(c) for c in hand if not is_two(c))
    counts = tuple(counter.get(r, 0) for r in range(TWO_RANK))
    for kind, start, length, per_rank in _best_combos(counts, rules):
        cards: list[int] = []
        for r in range(start, start + length):
            cards.extend(by_rank[r][:per_rank])
            by_rank[r] = by_rank[r][per_rank:]
        items.append(RotItem(kind, tuple(sorted(cards)), _value(kind, rules)))
    return [i for i in items if i.value > 0]

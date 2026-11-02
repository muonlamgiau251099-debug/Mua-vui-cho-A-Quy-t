"""Nhận diện bộ bài và so sánh cùng loại (ID 11, 17–27; Q-P1-2, Q-P1-3)."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from tlmn_engine.cards import TWO_RANK, rank


class ComboType(StrEnum):
    SINGLE = "SINGLE"
    PAIR = "PAIR"
    TRIPLE = "TRIPLE"  # bộ ba / sám cô (Q-P1-2)
    FOUR_KIND = "FOUR_KIND"  # tứ quý
    STRAIGHT = "STRAIGHT"  # sảnh ≥ 3 lá, không chứa 2 (ID 21–23)
    PAIR_SEQ = "PAIR_SEQ"  # đôi thông ≥ 3 đôi, không chứa 2 (Q-P1-3)


class ChopCategory(StrEnum):
    HEO_SINGLE = "HEO_SINGLE"
    HEO_PAIR = "HEO_PAIR"
    PS3 = "PS3"  # 3 đôi thông
    FK = "FK"  # tứ quý
    PS4 = "PS4"  # 4 đôi thông


@dataclass(frozen=True, slots=True)
class Combo:
    type: ComboType
    cards: tuple[int, ...]  # tăng dần
    length: int  # số lá (đơn/đôi/ba/tứ quý), số lá sảnh, hoặc số đôi của đôi thông

    @property
    def top(self) -> int:
        """Lá cao nhất — khóa so sánh (ID 17–22, 26, 27): số trước, chất sau."""
        return self.cards[-1]

    @property
    def chop_category(self) -> ChopCategory | None:
        if self.type == ComboType.SINGLE and rank(self.top) == TWO_RANK:
            return ChopCategory.HEO_SINGLE
        if self.type == ComboType.PAIR and rank(self.top) == TWO_RANK:
            return ChopCategory.HEO_PAIR
        if self.type == ComboType.FOUR_KIND:
            return ChopCategory.FK
        if self.type == ComboType.PAIR_SEQ and self.length == 3:
            return ChopCategory.PS3
        if self.type == ComboType.PAIR_SEQ and self.length == 4:
            return ChopCategory.PS4
        return None

    def same_shape(self, other: "Combo") -> bool:
        """Cùng loại và cùng số lá (ID 11, 21, 24)."""
        return self.type == other.type and self.length == other.length


def _consecutive(ranks: list[int]) -> bool:
    return all(b - a == 1 for a, b in pairwise(ranks))


def classify(cards: Iterable[int]) -> Combo | None:
    """Trả về bộ bài hợp lệ hoặc None. 4 lá cùng số luôn là tứ quý."""
    ordered = tuple(sorted(cards))
    n = len(ordered)
    if n == 0 or len(set(ordered)) != n:
        return None
    counts = Counter(rank(c) for c in ordered)
    if len(counts) == 1:
        kind = {1: ComboType.SINGLE, 2: ComboType.PAIR, 3: ComboType.TRIPLE, 4: ComboType.FOUR_KIND}[n]
        return Combo(kind, ordered, n)
    ranks = sorted(counts)
    if TWO_RANK in counts or not _consecutive(ranks):  # ID 23: không có 2, không vòng A-2-3
        return None
    if n >= 3 and all(v == 1 for v in counts.values()):
        return Combo(ComboType.STRAIGHT, ordered, n)
    if len(ranks) >= 3 and all(v == 2 for v in counts.values()):
        return Combo(ComboType.PAIR_SEQ, ordered, len(ranks))
    return None

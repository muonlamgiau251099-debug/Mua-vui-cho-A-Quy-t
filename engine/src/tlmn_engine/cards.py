"""Lá bài và bộ bài (ID 1, 5, 6).

card_id = rank_index * 4 + suit_index, trong đó
- rank_index: 3→0, 4→1, …, A→11, 2→12  (ID 5: 3 < 4 < … < A < 2)
- suit_index: ♠0, ♣1, ♦2, ♥3          (ID 6: Bích < Chuồn < Rô < Cơ)
So hai lá = so card_id. Lá nhỏ nhất 3♠ = 0, 3♣ = 1.
"""

from collections.abc import Iterable

DECK_SIZE = 52  # ID 1: 52 lá, không Joker
RANKS = ("3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2")
SUITS = ("S", "C", "D", "H")
SUIT_SYMBOLS = ("♠", "♣", "♦", "♥")
TWO_RANK = 12

THREE_SPADES = 0
THREE_CLUBS = 1


def rank(card: int) -> int:
    return card // 4


def suit(card: int) -> int:
    return card % 4


def is_two(card: int) -> bool:
    return rank(card) == TWO_RANK


def is_red(card: int) -> bool:
    return suit(card) >= 2


def card_name(card: int) -> str:
    return f"{RANKS[rank(card)]}{SUITS[suit(card)]}"


def card_label(card: int) -> str:
    return f"{RANKS[rank(card)]}{SUIT_SYMBOLS[suit(card)]}"


def parse_card(text: str) -> int:
    """'3C' → 1, '10H' → 31, '2S' → 48. Không phân biệt hoa thường."""
    text = text.strip().upper()
    r, s = text[:-1], text[-1]
    if r not in RANKS or s not in SUITS:
        raise ValueError(f"Lá bài không hợp lệ: {text!r}")
    return RANKS.index(r) * 4 + SUITS.index(s)


def parse_cards(text: str) -> list[int]:
    """'3C 4C 5H' → [1, 5, 11]."""
    return [parse_card(t) for t in text.split()]


def names(cards: Iterable[int]) -> str:
    return " ".join(card_name(c) for c in sorted(cards))


def full_deck() -> list[int]:
    return list(range(DECK_SIZE))

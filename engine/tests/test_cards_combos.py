import itertools

import pytest

from tlmn_engine.cards import (
    DECK_SIZE,
    THREE_CLUBS,
    THREE_SPADES,
    card_name,
    full_deck,
    parse_card,
    parse_cards,
)
from tlmn_engine.combos import ChopCategory, ComboType, classify
from tlmn_testkit import combo


@pytest.mark.rule(1)
def test_deck_has_52_unique_cards_without_jokers() -> None:
    deck = full_deck()
    assert len(deck) == DECK_SIZE == len(set(deck))
    assert {card_name(c)[-1] for c in deck} == {"S", "C", "D", "H"}


@pytest.mark.rule(5)
def test_rank_order_3_lowest_2_highest() -> None:
    order = ["3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2"]
    ids = [parse_card(f"{r}S") for r in order]
    assert ids == sorted(ids)


@pytest.mark.rule(6, 26)
def test_suit_order_spades_clubs_diamonds_hearts() -> None:
    assert parse_card("2S") < parse_card("2C") < parse_card("2D") < parse_card("2H")
    assert (parse_card("3S"), parse_card("3C")) == (THREE_SPADES, THREE_CLUBS)


@pytest.mark.rule(17)
def test_single_compares_rank_then_suit_for_all_pairs() -> None:
    for a, b in itertools.combinations(full_deck(), 2):
        bigger = classify([b]).top > classify([a]).top  # type: ignore[union-attr]
        expected = (a // 4, a % 4) < (b // 4, b % 4)
        assert bigger == expected


@pytest.mark.rule(18, 19)
def test_pairs_compare_by_rank_then_highest_suit() -> None:
    assert combo("5S 5H").top > combo("4D 4H").top
    assert combo("9C 9H").top > combo("9S 9D").top  # cùng số: lá cao nhất 9♥ > 9♦


@pytest.mark.rule(27)
def test_pair_of_twos_compares_highest_two() -> None:
    assert combo("2S 2H").top > combo("2C 2D").top


@pytest.mark.rule(21, 22)
def test_straights_compare_highest_card_same_length_only() -> None:
    assert combo("6S 7S 8S").top > combo("5H 6H 7H").top  # quân cao nhất 8 > 7
    assert combo("5S 6S 7H").top > combo("5H 6H 7S").top  # cùng giá trị: 7♥ > 7♠
    assert combo("8S 9S 10H").top > combo("8C 9C 10D").top  # 10♥ > 10♦
    assert not combo("3S 4S 5S").same_shape(combo("3C 4C 5C 6C"))


@pytest.mark.rule(23)
@pytest.mark.parametrize("cards", ["QS KS AS 2S", "AS 2S 3S", "KS AS 2D", "2S 3C 4C"])
def test_straight_cannot_contain_two_or_wrap(cards: str) -> None:
    assert classify(parse_cards(cards)) is None


@pytest.mark.parametrize(
    ("cards", "kind", "length"),
    [
        ("7H", ComboType.SINGLE, 1),
        ("7H 7S", ComboType.PAIR, 2),
        ("7H 7S 7C", ComboType.TRIPLE, 3),
        ("7H 7S 7C 7D", ComboType.FOUR_KIND, 4),
        ("3S 4D 5C", ComboType.STRAIGHT, 3),
        ("3S 4D 5C 6H 7H 8H 9H 10H JH QH KH AH", ComboType.STRAIGHT, 12),
        ("3S 3C 4S 4D 5H 5C", ComboType.PAIR_SEQ, 3),
        ("9S 9C 10S 10D JH JC QS QH", ComboType.PAIR_SEQ, 4),
        ("3S 3C 4S 4D 5H 5C 6S 6C 7S 7C", ComboType.PAIR_SEQ, 5),
    ],
)
def test_classify_valid_combinations(cards: str, kind: ComboType, length: int) -> None:
    result = combo(cards)
    assert (result.type, result.length) == (kind, length)


@pytest.mark.parametrize(
    "cards", ["3S 4S", "3S 5S 6S", "3S 3C 4S", "3S 3C 4S 4D 6S 6C", "3S 3C 3D 4S 4C 4D", ""]
)
def test_classify_rejects_invalid_combinations(cards: str) -> None:
    assert classify(parse_cards(cards)) is None


def test_duplicate_cards_are_invalid() -> None:
    assert classify([5, 5]) is None


def test_chop_categories() -> None:
    assert combo("2S").chop_category == ChopCategory.HEO_SINGLE
    assert combo("2S 2H").chop_category == ChopCategory.HEO_PAIR
    assert combo("5S 5C 5D 5H").chop_category == ChopCategory.FK
    assert combo("3S 3C 4S 4D 5H 5C").chop_category == ChopCategory.PS3
    assert combo("3S 3C 4S 4D 5H 5C 6S 6C").chop_category == ChopCategory.PS4
    assert combo("3S 3C 4S 4D 5H 5C 6S 6C 7S 7C").chop_category is None  # 5 đôi thông: không có quyền chặt
    assert combo("AS").chop_category is None

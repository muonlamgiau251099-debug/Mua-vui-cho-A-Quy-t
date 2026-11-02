"""Thối hàng, chuỗi chặt, điểm hạng (ID 72–77, 111–133; G1, G4)."""

import pytest

from tlmn_engine.cards import parse_cards
from tlmn_engine.rot import compute_rot
from tlmn_engine.scoring import settle_chain
from tlmn_engine.state import ChopLink
from tlmn_testkit import RULES, Table, make_game, rules_with


def rot(hand: str, rules=RULES) -> list[tuple[str, int]]:  # type: ignore[no-untyped-def]
    return [(i.kind, i.value) for i in compute_rot(parse_cards(hand), rules)]


@pytest.mark.rule(72, 73, 74, 117, 118)
def test_rot_twos_counted_per_card_black_100_red_200() -> None:
    assert rot("2S 2H 5C") == [("BLACK_TWO", 100), ("RED_TWO", 200)]  # đôi heo = tổng 2 heo


def test_four_twos_is_four_heo_not_four_kind() -> None:
    assert sum(v for _, v in rot("2S 2C 2D 2H")) == 600
    assert all(kind.endswith("_TWO") for kind, _ in rot("2S 2C 2D 2H"))


@pytest.mark.rule(75, 76, 77)
def test_rot_combos_200_each() -> None:
    assert rot("7S 7C 7D 7H") == [("FOUR_KIND", 200)]
    assert rot("5S 5C 6S 6C 7S 7C") == [("THREE_PAIR_SEQ", 200)]
    assert rot("5S 5C 6S 6C 7S 7C 8S 8C") == [("FOUR_PAIR_SEQ", 200)]  # không tính thêm 3 đôi thông bên trong


def test_six_pair_run_is_split_into_two_three_pair_seqs() -> None:
    assert rot("3S 3C 4S 4C 5S 5C 6S 6C 7S 7C 8S 8C") == [
        ("THREE_PAIR_SEQ", 200),
        ("THREE_PAIR_SEQ", 200),
    ]  # G4


def test_rot_cards_are_not_counted_twice() -> None:
    items = compute_rot(parse_cards("5S 5C 5D 5H 6S 6C 7S 7C"), RULES)
    assert sum(i.value for i in items) == 200  # tứ quý 5 HOẶC 3 đôi thông 5-6-7, không cả hai
    used = [c for i in items for c in i.cards]
    assert len(used) == len(set(used))


def test_disabled_rot_kinds_are_not_charged() -> None:
    rules = rules_with(**{"penalty.rot.redTwo": False, "penalty.rot.fourKind": False})
    assert rot("2H 2S 9S 9C 9D 9H", rules) == [("BLACK_TWO", 100)]


@pytest.mark.rule(41, 83)
def test_settle_chain_sums_all_links_last_victim_pays_last_chopper() -> None:
    transfer = settle_chain([ChopLink(1, 0, 200), ChopLink(2, 1, 200), ChopLink(3, 2, 400)])
    assert transfer is not None
    assert (transfer.from_seat, transfer.to_seat, transfer.amount) == (2, 3, 800)
    assert settle_chain([]) is None


@pytest.mark.rule(112, 113, 114, 115, 80, 132)
def test_custom_rank_points_are_used() -> None:
    rules = rules_with(
        **{
            "scoring.rank.first": 300,
            "scoring.rank.last": -300,
            "scoring.rank.second": 50,
            "scoring.rank.third": -50,
        }
    )
    t = Table(make_game(["3C", "4S", "5S", "6S 7S"]), rules)
    t.play(0, "3C")
    t.play(1, "4S")
    t.play(2, "5S")
    assert t.net == [300, 50, -50, -300]


@pytest.mark.rule(111, 127, 128, 133)
def test_scores_start_at_zero_can_go_negative_and_always_sum_to_zero() -> None:
    t = Table(make_game(["3C", "4S", "5S", "6S 2H 2D 2C"]))
    assert t.net == [0, 0, 0, 0]
    t.play(0, "3C")
    t.play(1, "4S")
    t.play(2, "5S")
    assert min(t.net) < 0 and sum(t.net) == 0

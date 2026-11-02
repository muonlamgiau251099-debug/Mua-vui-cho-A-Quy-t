"""Chia bài, tới trắng, chia lại, cách mở ván (ID 3, 7, 9, 49–67, 107, 124)."""

import pytest

from tlmn_engine.cards import THREE_CLUBS, parse_cards
from tlmn_engine.dealing import (
    DealResult,
    InstantWinKind,
    check_instant_win,
    deal,
    detect_redeal,
    next_opening,
    qualifies,
    start_game,
)
from tlmn_engine.invariants import check_invariants
from tlmn_engine.state import EndType, OpeningMode, Phase
from tlmn_testkit import RULES, deck_with, rules_with

FOUR_TWOS = "2S 2C 2D 2H"
SIX_PAIRS = "4S 4C 6S 6C 8S 8C 10S 10C QS QC AS AC"
DRAGON = "3D 4D 5D 6D 7D 8D 9D 10D JD QD KD AD"
NO_SPECIAL = "4S 5C 6S 7H 9S 10C JH QH KS KC 8C"  # 11 lá, không có ♦, không tạo được tới trắng


def no_instant_win(hands: list[list[int]]) -> bool:
    return check_instant_win(hands, 0, RULES) is None and detect_redeal(hands, RULES) is None


def normal_deck() -> list[int]:
    return deck_with(["", "", "", ""], no_instant_win)


@pytest.mark.rule(3)
def test_each_player_gets_13_cards() -> None:
    hands = deal(normal_deck())
    assert [len(h) for h in hands] == [13, 13, 13, 13]
    with pytest.raises(ValueError, match="52 lá"):
        deal([*range(51), 0])


@pytest.mark.rule(7)
def test_three_clubs_holder_leads_three_clubs_game() -> None:
    deck = normal_deck()
    outcome = start_game(deck, OpeningMode.THREE_CLUBS, RULES, now=0)
    holder = next(s for s, h in enumerate(deal(deck)) if THREE_CLUBS in h)
    assert outcome.result == DealResult.PLAYING
    assert outcome.state is not None
    assert (outcome.state.current, outcome.state.first_move_pending) == (holder, True)
    check_invariants(outcome.state)


@pytest.mark.rule(9)
def test_previous_winner_leads_next_game() -> None:
    outcome = start_game(normal_deck(), OpeningMode.WINNER_LEADS, RULES, now=0, previous_winner=2)
    assert outcome.state is not None and outcome.state.current == 2


@pytest.mark.rule(60, 9)
def test_next_opening_mode() -> None:
    assert next_opening(None, None) == OpeningMode.THREE_CLUBS  # ván đầu (D5)
    assert next_opening(EndType.INSTANT_WIN, 1) == OpeningMode.THREE_CLUBS  # ID 60
    assert next_opening(EndType.CANCELLED, 1) == OpeningMode.THREE_CLUBS  # G8
    assert next_opening(EndType.NORMAL, 1) == OpeningMode.WINNER_LEADS
    assert next_opening(EndType.BLIND_THREE_SPADES, 3) == OpeningMode.WINNER_LEADS


@pytest.mark.rule(49, 52, 53)
def test_instant_win_conditions() -> None:
    assert qualifies(parse_cards(f"{FOUR_TWOS} 3S"), InstantWinKind.FOUR_TWOS)
    assert qualifies(parse_cards(f"{SIX_PAIRS} 3S"), InstantWinKind.SIX_PAIRS)
    assert qualifies(
        parse_cards("5S 5C 5D 5H 7S 7C 9S 9C JS JC KS KC 3S"), InstantWinKind.SIX_PAIRS
    )  # tứ quý = 2 đôi
    assert qualifies(parse_cards(f"{DRAGON} 2S"), InstantWinKind.DRAGON)  # 3 → A, không cần đồng chất
    assert not qualifies(parse_cards(f"{NO_SPECIAL} 2S 2C"), InstantWinKind.SIX_PAIRS)


@pytest.mark.rule(65, 66, 107, 124)
def test_instant_win_ends_game_right_after_dealing() -> None:
    deck = deck_with(
        [NO_SPECIAL, f"{DRAGON} 3S", "", ""], lambda h: check_instant_win(h, 0, RULES) is not None
    )
    outcome = start_game(deck, OpeningMode.WINNER_LEADS, RULES, now=0, previous_winner=0)
    assert outcome.result == DealResult.INSTANT_WIN
    state = outcome.state
    assert state is not None
    assert (state.phase, state.end_type) == (Phase.FINISHED, EndType.INSTANT_WIN)
    assert [p.rank for p in state.players] == [4, 1, 4, 4]  # D4: những người còn lại về thứ 4
    assert state.net() == [-200, 600, -200, -200]  # 200 × 3 (ID 124), không xét thối
    assert outcome.events[0] == {"type": "INSTANT_WIN", "kind": "DRAGON", "winners": [1]}


@pytest.mark.rule(62, 64)
def test_priority_four_twos_over_dragon_over_six_pairs() -> None:
    hands = [
        parse_cards(f"{SIX_PAIRS} 3S"),
        parse_cards(f"{DRAGON} 3C"),
        parse_cards("2S 2C 2D 2H 3H 5S 7S 9C JH KH 5H 7C 9H"),
        [],
    ]
    win = check_instant_win(hands, 0, RULES)
    assert win is not None and (win.kind, win.winners) == (InstantWinKind.FOUR_TWOS, [2])
    win = check_instant_win([*hands[:2], [], []], 0, RULES)
    assert win is not None and (win.kind, win.winners) == (InstantWinKind.DRAGON, [1])
    custom = rules_with(**{"instantWin.priorityOrder": ["SIX_PAIRS", "DRAGON", "FOUR_TWOS"]})
    win = check_instant_win(hands, 0, custom)
    assert win is not None and win.kind == InstantWinKind.SIX_PAIRS


@pytest.mark.rule(63)
def test_same_kind_instant_win_splits_money() -> None:
    six_a = "4S 4C 6S 6C 8S 8C 10S 10C QS QC AS AC"
    six_b = "4D 4H 6D 6H 8D 8H 10D 10H QD QH AD AH"
    deck = deck_with(
        ["", six_a, "", six_b],
        lambda h: (w := check_instant_win(h, 0, RULES)) is not None and w.winners == [1, 3],
    )
    outcome = start_game(deck, OpeningMode.WINNER_LEADS, RULES, now=0, previous_winner=0)
    assert outcome.state is not None
    assert outcome.state.net() == [-200, 200, -200, 200]  # N2: chia đều tiền
    first_only = rules_with(**{"instantWin.tieBreak": "FIRST_IN_TURN_ORDER"})
    win = check_instant_win(deal(deck), 2, first_only)
    assert win is not None and win.winners == [3]  # ai đi trước (tính từ ghế 2) thắng


def test_uneven_split_gives_remainder_to_first_winner() -> None:
    from tlmn_engine.scoring import instant_win_transfers

    transfers = instant_win_transfers([1, 2, 3], RULES, 200, "INSTANT_WIN")
    totals = [0, 0, 0, 0]
    for t in transfers:
        totals[t.from_seat] -= t.amount
        totals[t.to_seat] += t.amount
    assert totals == [-200, 68, 66, 66]


def test_disabled_instant_win_kind_is_ignored() -> None:
    hands = [parse_cards(f"{DRAGON} 3C"), [], [], []]
    assert check_instant_win(hands, 0, rules_with(**{"instantWin.dragonStraight": False})) is None


@pytest.mark.rule(58)
def test_redeal_when_three_clubs_holder_has_four_threes() -> None:
    deck = deck_with(["3S 3C 3D 3H", "", "", ""], lambda h: check_instant_win(h, 0, RULES) is None)
    assert start_game(deck, OpeningMode.THREE_CLUBS, RULES, now=0).result == DealResult.REDEAL
    off = rules_with(**{"redeal.fourThrees": False})
    assert start_game(deck, OpeningMode.THREE_CLUBS, off, now=0).result == DealResult.PLAYING


@pytest.mark.rule(59)
def test_redeal_when_three_clubs_holder_has_pair_seq_from_threes() -> None:
    deck = deck_with(
        ["3C 3D 4S 4H 5C 5D", "", "", ""],
        lambda h: (
            check_instant_win(h, 0, RULES) is None and detect_redeal(h, RULES) == "PAIR_SEQ_WITH_THREE_CLUBS"
        ),
    )
    assert start_game(deck, OpeningMode.THREE_CLUBS, RULES, now=0).result == DealResult.REDEAL
    other_holder = deck_with(["3S 3D 4S 4H 5C 5D", "3C", "", ""], no_instant_win)
    assert detect_redeal(deal(other_holder), RULES) is None  # 3♣ ở người khác → không chia lại


@pytest.mark.rule(58, 59)
def test_redeal_only_applies_to_three_clubs_games() -> None:
    deck = deck_with(["3S 3C 3D 3H", "", "", ""], lambda h: check_instant_win(h, 0, RULES) is None)
    outcome = start_game(deck, OpeningMode.WINNER_LEADS, RULES, now=0, previous_winner=1)
    assert outcome.result == DealResult.PLAYING


@pytest.mark.rule(67)
def test_instant_win_checked_before_redeal() -> None:
    # R7: người giữ 3♣ có tứ quý 3, người khác có 6 đôi → tới trắng, không chia lại.
    deck = deck_with(["3S 3C 3D 3H", "4S 4C 6S 6C 8S 8C 10S 10C QS QC AS AC", "", ""])
    assert start_game(deck, OpeningMode.THREE_CLUBS, RULES, now=0).result == DealResult.INSTANT_WIN

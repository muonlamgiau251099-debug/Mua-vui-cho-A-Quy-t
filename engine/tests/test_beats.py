"""Bảng quyết định đè / chặt (docs/gd2/03 §3)."""

import pytest

from tlmn_engine.beats import BeatKind, MoveRejected, can_beat, can_interrupt
from tlmn_engine.combos import Combo
from tlmn_testkit import RULES, combo, rules_with

PS3 = "6S 6C 7S 7C 8S 8C"
PS3_BIG = "9S 9C 10S 10C JS JC"
PS4 = "3D 3H 4D 4H 5D 5H 6D 6H"
PS4_BIG = "9D 9H 10D 10H JD JH QD QH"
FK = "KS KC KD KH"
FK_SMALL = "4S 4C 4D 4H"


def beat(top: str | None, play: str, rules=RULES, *, top_is_chop: bool = False, finished: bool = False):  # type: ignore[no-untyped-def]
    top_combo: Combo | None = combo(top) if top else None
    return can_beat(
        rules,
        top_combo,
        combo(play),
        must_include_three_clubs=False,
        top_is_chop=top_is_chop,
        someone_finished=finished,
    )


def rejected(top: str, play: str, rules=RULES, **kw: bool) -> str:  # type: ignore[no-untyped-def]
    with pytest.raises(MoveRejected) as exc:
        beat(top, play, rules, **kw)
    return exc.value.code


@pytest.mark.rule(11, 24)
def test_must_beat_with_same_type_same_count_and_higher() -> None:
    assert beat("7S", "7H").kind == BeatKind.BEAT
    assert rejected("7H", "7S") == "CANNOT_BEAT"
    assert rejected("7S", "8S 8H") == "CANNOT_BEAT"  # khác loại
    assert rejected("3S 4S 5S", "6S 7S 8S 9S") == "CANNOT_BEAT"  # sảnh khác số lá
    assert beat("3S 4S 5S 6S", "4D 5D 6D 7D").kind == BeatKind.BEAT


def test_lead_requires_three_clubs_on_first_move() -> None:
    with pytest.raises(MoveRejected, match="3♣"):
        can_beat(
            RULES, None, combo("4S"), must_include_three_clubs=True, top_is_chop=False, someone_finished=False
        )
    result = can_beat(
        RULES,
        None,
        combo("3C 4D 5H"),
        must_include_three_clubs=True,
        top_is_chop=False,
        someone_finished=False,
    )
    assert result.kind == BeatKind.LEAD


@pytest.mark.rule(26)
def test_single_two_beaten_by_higher_two_is_not_a_chop() -> None:
    result = beat("2S", "2H")
    assert (result.kind, result.scores_as_chop) == (BeatKind.BEAT, False)


@pytest.mark.rule(25, 29, 31, 35)
@pytest.mark.parametrize(
    ("attacker", "value_red", "value_black"), [(PS3, 200, 100), (FK, 200, 100), (PS4, 200, 100)]
)
def test_single_two_can_be_chopped(attacker: str, value_red: int, value_black: int) -> None:
    red, black = beat("2H", attacker), beat("2S", attacker)
    assert (red.kind, red.scores_as_chop, red.target_value) == (BeatKind.CHOP, True, value_red)
    assert black.target_value == value_black  # ID 117, 118, 119–121: tính theo heo bị chặt


@pytest.mark.rule(32, 36)
@pytest.mark.parametrize("attacker", [FK, PS4])
def test_pair_of_twos_chopped_by_four_kind_or_four_pair_seq(attacker: str) -> None:
    assert beat("2S 2H", attacker).target_value == 300  # đen 100 + đỏ 200


def test_three_pair_seq_cannot_chop_pair_of_twos() -> None:
    assert rejected("2S 2H", PS3) == "CANNOT_BEAT"


@pytest.mark.rule(33, 38)
@pytest.mark.parametrize("attacker", [FK, PS4])
def test_three_pair_seq_chopped_by_four_kind_or_four_pair_seq(attacker: str) -> None:
    result = beat(PS3, attacker)
    assert (result.kind, result.target_value) == (BeatKind.CHOP, 200)


@pytest.mark.rule(30, 120)
def test_bigger_three_pair_seq_over_three_pair_seq_scores_one_red_two() -> None:
    result = beat(PS3, PS3_BIG)
    assert (result.kind, result.scores_as_chop, result.target_value) == (BeatKind.BEAT, True, 200)


@pytest.mark.rule(34, 119)
def test_bigger_four_kind_over_four_kind_scores_two_red_twos() -> None:
    result = beat(FK_SMALL, FK)
    assert (result.kind, result.scores_as_chop, result.target_value) == (BeatKind.BEAT, True, 400)
    assert rejected(FK, FK_SMALL) == "CANNOT_BEAT"


@pytest.mark.rule(37, 121)
def test_four_pair_seq_chops_four_kind() -> None:
    assert beat(FK, PS4).target_value == 400
    assert rejected(PS4, FK) == "CANNOT_BEAT"  # tứ quý không chặt được 4 đôi thông


@pytest.mark.rule(39, 121)
def test_bigger_four_pair_seq_over_four_pair_seq() -> None:
    assert beat(PS4, PS4_BIG).target_value == 400


@pytest.mark.rule(44)
def test_pair_of_twos_over_pair_of_twos_scores_like_chop_when_enabled() -> None:
    on = beat("2S 2C", "2D 2H")
    assert (on.kind, on.scores_as_chop, on.target_value) == (BeatKind.BEAT, True, 200)  # 2♠ + 2♣
    off = beat("2S 2C", "2D 2H", rules_with(**{"chop.pairTwoOverPairTwoScoresAsChop": False}))
    assert off.scores_as_chop is False


@pytest.mark.rule(29, 31, 32, 33, 35, 36, 37, 38)
@pytest.mark.parametrize(
    ("flag", "target", "attacker"),
    [
        ("chop.threePairSeq.vsSingleTwo", "2H", PS3),
        ("chop.fourKind.vsSingleTwo", "2H", FK),
        ("chop.fourKind.vsPairTwo", "2S 2H", FK),
        ("chop.fourKind.vsThreePairSeq", PS3, FK),
        ("chop.fourPairSeq.vsSingleTwo", "2H", PS4),
        ("chop.fourPairSeq.vsPairTwo", "2S 2H", PS4),
        ("chop.fourPairSeq.vsFourKind", FK, PS4),
        ("chop.fourPairSeq.vsThreePairSeq", PS3, PS4),
    ],
)
def test_each_chop_cell_can_be_disabled_by_admin(flag: str, target: str, attacker: str) -> None:
    assert beat(target, attacker).kind == BeatKind.CHOP
    assert rejected(target, attacker, rules_with(**{flag: False})) == "CANNOT_BEAT"


@pytest.mark.rule(41)
def test_chain_chop_can_be_disabled() -> None:
    rules = rules_with(**{"chop.allowChain": False})
    assert rejected(PS3, FK, rules, top_is_chop=True) == "CHAIN_NOT_ALLOWED"
    assert beat(PS3, FK, rules, top_is_chop=False).kind == BeatKind.CHOP  # 3 đôi thông được đánh thường


@pytest.mark.rule(48)
def test_chop_after_first_finisher_can_be_disabled() -> None:
    assert beat("2H", FK, finished=True).kind == BeatKind.CHOP
    rules = rules_with(**{"chop.allowAfterFirstFinisher": False})
    assert rejected("2H", FK, rules, finished=True) == "CHOP_NOT_ALLOWED"
    assert beat("7S", "7H", rules, finished=True).kind == BeatKind.BEAT  # đè thường vẫn được


@pytest.mark.rule(42, 43)
def test_only_four_pair_seq_may_interrupt_out_of_turn() -> None:
    assert can_interrupt(RULES, combo(PS4), beat("2H", PS4))
    assert can_interrupt(RULES, combo(PS4_BIG), beat(PS4, PS4_BIG))
    assert not can_interrupt(RULES, combo(FK), beat("2H", FK))  # D6: tứ quý cần đúng vòng
    assert not can_interrupt(RULES, combo(PS3), beat("2H", PS3))
    off = rules_with(**{"chop.fourPairSeq.outOfTurn": False})
    assert not can_interrupt(off, combo(PS4), beat("2H", PS4, off))

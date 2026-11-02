import pytest

from tlmn_engine.cards import parse_cards
from tlmn_engine.projection import project_private, project_public
from tlmn_testkit import Table, make_game


@pytest.mark.rule(152)
def test_private_view_contains_only_own_hand_while_playing() -> None:
    t = Table(make_game(["3S 9S", "4S 10S", "5S JS", "6S QS"]))
    t.play(0, "3S")
    public = project_public(t.state)
    assert "hands" not in public
    assert [p["cardCount"] for p in public["players"]] == [1, 2, 2, 2]  # chỉ thấy số lá đối thủ
    private = project_private(t.state, 1)
    assert private["yourHand"] == sorted(parse_cards("4S 10S"))
    assert not set(parse_cards("9S 5S JS 6S QS")) & set(private["yourHand"])  # không chứa bài người khác
    assert public["trick"]["top"] == parse_cards("3S")  # bài trên bàn là công khai


def test_all_hands_revealed_after_game_ends() -> None:
    t = Table(make_game(["3C", "4S", "5S", "6S 7S"]))
    t.play(0, "3C")
    t.play(1, "4S")
    t.play(2, "5S")
    public = project_public(t.state)
    assert public["phase"] == "FINISHED"
    assert public["hands"][3] == sorted(parse_cards("6S 7S"))
    assert public["net"] == [200, 100, -100, -200]

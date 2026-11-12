"""Diễn biến ván qua reducer, với bài trên tay được dựng sẵn. Ghế 0–3 = A, B, C, D (chiều kim đồng hồ)."""

import pytest

from tlmn_engine.beats import MoveRejected
from tlmn_engine.cards import parse_cards
from tlmn_engine.state import EndType, OpeningMode, Phase, PlayerStatus
from tlmn_testkit import RULES, Table, make_game, rules_with

A, B, C, D = 0, 1, 2, 3
PS3 = "6S 6C 7S 7C 8S 8C"
PS4 = "9D 9H 10D 10H JD JH QD QH"
FK = "KS KC KD KH"


def rejected(table: Table, seat: int, cards: str | None) -> str:
    with pytest.raises(MoveRejected) as exc:
        table.play(seat, cards) if cards is not None else table.pass_(seat)
    return exc.value.code


@pytest.mark.rule(4, 12, 13, 14)
def test_clockwise_turns_pass_locks_until_new_trick() -> None:
    t = Table(make_game(["3S 9S KS", "4S 10S AS", "5S JS 2S", "6S QS 7D"]))
    t.play(A, "3S")
    assert t.state.current == B
    t.play(B, "4S")
    t.pass_(C)
    t.play(D, "6S")
    t.play(A, "9S")
    assert t.state.current == B  # C đã bỏ lượt nên bị bỏ qua (ID 13)
    assert rejected(t, C, "JS") == "NOT_YOUR_TURN"
    t.pass_(B)
    t.pass_(D)
    closed = t.of_type("TRICK_CLOSED")[-1]
    assert (closed["winner"], closed["nextLeader"]) == (A, A)  # ID 14: người đánh cuối mở vòng mới
    assert (t.state.current, t.state.trick.top, t.state.trick.passed) == (A, None, set())


@pytest.mark.rule(12)
def test_leader_cannot_pass() -> None:
    t = Table(make_game(["3S 9S", "4S 10S", "5S JS", "6S QS"]))
    assert rejected(t, A, None) == "LEADER_CANNOT_PASS"


def test_cannot_play_cards_not_in_hand_or_invalid_combination() -> None:
    t = Table(make_game(["3S 9S", "4S 10S", "5S JS", "6S QS"]))
    assert rejected(t, A, "4S") == "CARDS_NOT_IN_HAND"
    assert rejected(t, A, "3S 9S") == "INVALID_COMBINATION"
    assert rejected(t, B, "4S") == "NOT_YOUR_TURN"


@pytest.mark.rule(7, 8)
def test_first_move_of_three_clubs_game_must_contain_three_clubs() -> None:
    hands = ["3C 4D 5H 9S", "3S 10S", "5S JS", "6S QS"]
    t = Table(make_game(hands, opening=OpeningMode.THREE_CLUBS, first_move=True))
    assert rejected(t, A, "9S") == "MUST_INCLUDE_THREE_CLUBS"
    t.play(A, "3C 4D 5H")  # 3♣ nằm trong sảnh vẫn hợp lệ
    assert t.state.first_move_pending is False
    free = Table(
        make_game(hands, opening=OpeningMode.THREE_CLUBS, first_move=True),
        rules_with(**{"opening.mustIncludeThreeClubs": False}),
    )
    free.play(A, "9S")


def test_three_clubs_holder_forfeiting_before_first_move_frees_next_leader() -> None:
    # Hồi quy: trước đây người kế tiếp bị bắt phải đánh 3♣ mà không có → ván kẹt vĩnh viễn.
    t = Table(
        make_game(["3C 9S", "4S 10S", "5S JS", "6S QS"], opening=OpeningMode.THREE_CLUBS, first_move=True)
    )
    t.forfeit(A)
    assert t.state.current == B
    assert t.timeout()[0]["cards"] == parse_cards("4S")  # hết giờ: tự đánh lá nhỏ nhất của B
    t2 = Table(
        make_game(["3C 9S", "4S 10S", "5S JS", "6S QS"], opening=OpeningMode.THREE_CLUBS, first_move=True)
    )
    t2.forfeit(A)
    t2.play(B, "10S")


@pytest.mark.rule(9)
def test_winner_leads_game_has_no_three_clubs_requirement() -> None:
    t = Table(
        make_game(["3C 9S", "3S 10S", "5S JS", "6S QS"], opening=OpeningMode.WINNER_LEADS, first_move=True)
    )
    t.play(A, "9S")


@pytest.mark.rule(10, 141)
def test_each_turn_gets_deadline_from_rules() -> None:
    t = Table(make_game(["3S 9S", "4S 10S", "5S JS", "6S QS"]), now=1000.0)
    events = t.play(A, "3S")
    assert events[-1] == {"type": "TURN_STARTED", "seat": B, "deadline": 1030.0}
    custom = Table(
        make_game(["3S 9S", "4S 10S", "5S JS", "6S QS"]), rules_with(**{"turn.timeLimitSeconds": 45})
    )
    assert custom.play(A, "3S")[-1]["deadline"] == 45.0


@pytest.mark.rule(13, 88, 142)
def test_timeout_of_responder_is_a_pass() -> None:
    t = Table(make_game(["3S 9S", "4S 10S", "5S JS", "6S QS"]))
    t.play(A, "3S")
    with pytest.raises(MoveRejected, match="Chưa hết giờ"):
        t.do(__import__("tlmn_engine.reducer", fromlist=["Timeout"]).Timeout())
    events = t.timeout()
    assert events[0] == {"type": "PASSED", "seat": B, "auto": True}
    assert B in t.state.trick.passed


@pytest.mark.rule(142)
def test_timeout_of_leader_auto_plays_lowest_single() -> None:
    t = Table(make_game(["3S 9S", "4S 10S", "5S JS", "6S QS"], current=B))
    played = t.timeout()[0]
    assert (played["type"], played["seat"], played["cards"], played["auto"]) == (
        "PLAYED",
        B,
        [parse_cards("4S")[0]],
        True,
    )


def test_timeout_on_first_move_auto_plays_three_clubs_even_with_three_spades() -> None:
    t = Table(
        make_game(["3S 3C 9S", "4S 10S", "5S JS", "6S QS"], opening=OpeningMode.THREE_CLUBS, first_move=True)
    )
    assert t.timeout()[0]["cards"] == parse_cards("3C")


@pytest.mark.rule(15, 16, 99, 100, 101, 102, 103, 104, 106, 80)
def test_players_ranked_by_finish_order_and_game_plays_until_one_left() -> None:
    t = Table(make_game(["3C", "4S", "5S", "6S 7S"]))
    t.play(A, "3C")
    assert t.state.phase == Phase.PLAYING  # ID 103 = Không: chưa kết thúc khi có người nhất
    assert t.state.current == B  # ID 106: A đã hết bài, không còn lượt
    t.play(B, "4S")
    t.play(C, "5S")
    assert t.state.phase == Phase.FINISHED
    assert [p.rank for p in t.state.players] == [1, 2, 3, 4]
    assert t.state.finish_order == [A, B, C, D]
    assert t.net == [200, 100, -100, -200]  # ID 112–115 (điểm hạng mặc định)


@pytest.mark.rule(105)
def test_huong_sai_when_nobody_beats_the_finishers_last_card() -> None:
    t = Table(make_game(["3C", "4S 5S", "6S 7S", "8S 9S"]))
    t.play(A, "3C")
    t.pass_(B)
    t.pass_(C)
    t.pass_(D)
    closed = t.of_type("TRICK_CLOSED")[-1]
    assert (closed["winner"], closed["nextLeader"], t.state.current) == (A, B, B)  # D2


@pytest.mark.rule(105)
def test_catching_the_finishers_last_card_continues_the_trick() -> None:
    t = Table(make_game(["3C", "4S 5S", "6S 7S", "8S 9S"]))
    t.play(A, "3C")
    t.play(B, "5S")
    t.pass_(C)
    t.pass_(D)
    assert t.of_type("TRICK_CLOSED")[-1]["nextLeader"] == B


def test_player_who_passed_cannot_catch_a_later_finishing_card() -> None:
    t = Table(make_game(["8S", "4S 5S", "9H 7D", "6S 10S"], current=B))
    t.play(B, "4S")
    t.pass_(C)
    t.play(D, "6S")
    t.play(A, "8S")  # A hết bài
    assert rejected(t, C, "9H") == "NOT_YOUR_TURN"
    t.pass_(B)
    t.pass_(D)
    assert t.of_type("TRICK_CLOSED")[-1]["nextLeader"] == B  # hưởng sái: người kế tiếp sau A


@pytest.mark.rule(42)
def test_four_pair_seq_interrupts_out_of_turn_even_after_passing() -> None:
    t = Table(make_game(["2S 3S", "4S 5S", f"{PS4} 3D", "7H 8H"]))
    t.play(A, "2S")
    t.pass_(B)
    t.pass_(C)  # C bỏ lượt dù có 4 đôi thông
    assert t.state.current == D
    events = t.play(C, PS4)
    assert events[0]["interrupt"] is True and events[0]["kind"] == "CHOP"
    assert C not in t.state.trick.passed  # G12
    assert t.state.current == D  # lượt tiếp theo tính từ người chặt
    t.pass_(D)
    t.pass_(A)
    chop = t.of_type("TRICK_CLOSED")[-1]["chop"]
    assert (chop["from"], chop["to"], chop["amount"]) == (A, C, 100)  # ID 81, 82: bị chặt heo đen


@pytest.mark.rule(42)
def test_heo_trick_gives_four_pair_seq_holder_a_turn_before_closing() -> None:
    # A mở 5, B và C bỏ (mất vòng), D đè heo, A bỏ → vòng chưa đóng, tặng lượt cho C (có 4 đôi thông)
    t = Table(make_game(["5S 3S", "4S 6S", f"{PS4} 3D", "2S 7H"]))
    t.play(A, "5S")
    t.pass_(B)
    t.pass_(C)
    t.play(D, "2S")
    t.pass_(A)
    assert t.of_type("TRICK_CLOSED") == []
    assert t.state.current == C
    events = t.play(C, PS4)
    assert events[0]["kind"] == "CHOP"
    t.pass_(D)  # A, B đã bỏ lượt từ trước → chỉ còn D đáp lại
    chop = t.of_type("TRICK_CLOSED")[-1]["chop"]
    assert (chop["from"], chop["to"], chop["amount"]) == (D, C, 100)


@pytest.mark.rule(42)
def test_gifted_chop_turn_is_given_once_and_may_be_declined() -> None:
    t = Table(make_game(["5S 3S", "4S 6S", f"{PS4} 3D", "2S 7H"]))
    t.play(A, "5S")
    t.pass_(B)
    t.pass_(C)
    t.play(D, "2S")
    t.pass_(A)
    assert t.state.current == C
    t.pass_(C)  # C không chặt
    closed = t.of_type("TRICK_CLOSED")[-1]
    assert (closed["winner"], closed["chop"]) == (D, None)
    assert t.state.current == D


@pytest.mark.rule(42)
@pytest.mark.parametrize("target", [PS3, FK])
def test_three_pair_seq_and_four_kind_tricks_also_gift_a_chop_turn(target: str) -> None:
    t = Table(make_game([f"{target} 3S", "4S 5S", f"{PS4} 3D", "7H 8H"]))
    t.play(A, target)
    t.pass_(B)
    t.pass_(C)
    t.pass_(D)
    assert t.state.current == C
    assert t.play(C, PS4)[0]["kind"] == "CHOP"


@pytest.mark.rule(42)
def test_no_gifted_turn_for_plain_cards_bigger_four_pair_seq_or_rule_off() -> None:
    small = "3D 3H 4D 4H 5D 5H 6D 6H"
    t = Table(make_game(["9S 3S", "4S 6S", f"{small} 7C", f"{PS4} 7H"]))
    t.play(A, "9S")  # bài thường → đóng vòng như cũ
    t.pass_(B)
    t.pass_(C)
    t.pass_(D)
    assert t.of_type("TRICK_CLOSED")[-1]["winner"] == A

    t = Table(make_game([f"{small} 3S", "4S 5S", f"{PS4} 7C", "7H 8H"]))
    t.play(A, small)  # 4 đôi thông trên bàn: không nằm trong danh sách tặng lượt
    t.pass_(B)
    t.pass_(C)
    t.pass_(D)
    assert t.of_type("TRICK_CLOSED")[-1]["winner"] == A

    off = rules_with(**{"chop.fourPairSeq.outOfTurn": False})
    t = Table(make_game(["5S 3S", "4S 6S", f"{PS4} 3D", "2S 7H"]), rules=off)
    t.play(A, "5S")
    t.pass_(B)
    t.pass_(C)
    t.play(D, "2S")
    t.pass_(A)
    assert t.of_type("TRICK_CLOSED")[-1]["winner"] == D


@pytest.mark.rule(43)
def test_four_kind_and_three_pair_seq_cannot_interrupt() -> None:
    t = Table(make_game(["2S 3S", "4S 5S", f"{FK} {PS3}", "7H 8H"]))
    t.play(A, "2S")
    t.pass_(B)
    t.pass_(C)
    assert rejected(t, C, FK) == "NOT_YOUR_TURN"
    assert rejected(t, C, PS3) == "NOT_YOUR_TURN"


@pytest.mark.rule(41, 81, 82, 83, 122)
def test_chain_chop_is_cumulative_last_victim_pays_all() -> None:
    t = Table(make_game(["2H 3S", f"{PS3} 3D", f"{FK} 4D", "7H 8H"]))
    t.play(A, "2H")
    t.play(B, PS3)
    t.play(C, FK)
    t.pass_(D)
    t.pass_(A)
    t.pass_(B)
    chop = t.of_type("TRICK_CLOSED")[-1]["chop"]
    assert (chop["from"], chop["to"], chop["amount"]) == (B, C, 400)  # D3: 200 (heo đỏ) + 200 (3 đôi thông)
    assert t.net == [0, -400, 400, 0]  # A không mất điểm (ví dụ 4, docs/gd2/03 §7)


@pytest.mark.rule(81, 82, 83, 117, 118)
def test_chopping_heo_over_heo_takes_every_heo_last_victim_pays() -> None:
    t = Table(make_game(["2S 3S", "2H 3D", f"{PS3} 4D", "7H 8H"]))
    t.play(A, "2S")
    t.play(B, "2H")  # heo đỏ đè heo đen
    t.play(C, PS3)
    t.pass_(D)
    t.pass_(A)
    t.pass_(B)
    chop = t.of_type("TRICK_CLOSED")[-1]["chop"]
    assert (chop["from"], chop["to"], chop["amount"]) == (B, C, 300)  # 100 (heo đen) + 200 (heo đỏ)
    assert t.net == [0, -300, 300, 0]


def test_heo_over_heo_without_chop_scores_nothing() -> None:
    t = Table(make_game(["2S 3S", "2H 3D", "4D 5D", "7H 8H"]))
    t.play(A, "2S")
    t.play(B, "2H")
    t.pass_(C)
    t.pass_(D)
    t.pass_(A)
    assert t.of_type("TRICK_CLOSED")[-1]["chop"] is None
    assert t.state.trick.heo_carry == 0


@pytest.mark.rule(41, 83, 119, 120, 121, 122)
def test_four_level_chain_last_victim_pays_800() -> None:
    t = Table(make_game(["2H 3S", f"{PS3} 3D", f"{FK} 4D", f"{PS4} 5D"]))
    t.play(A, "2H")
    t.play(B, PS3)
    t.play(C, FK)
    t.play(D, PS4)
    t.pass_(A)
    t.pass_(B)
    t.pass_(C)
    chop = t.of_type("TRICK_CLOSED")[-1]["chop"]
    # 200 (heo đỏ) + 200 (3 đôi thông) + 400 (tứ quý) → C gánh hết cho D
    assert (chop["from"], chop["to"], chop["amount"]) == (C, D, 800)
    assert t.net == [0, 0, -800, 800]


@pytest.mark.rule(46, 48, 105)
def test_finishing_with_heo_then_chopped_costs_nothing() -> None:
    t = Table(make_game(["5S 4S", "2S", f"{PS3} 3D", "9H 10H"]))
    t.play(A, "5S")
    t.play(B, "2S")  # B về nhất bằng heo đen
    t.play(C, PS3)
    t.pass_(D)
    t.pass_(A)
    closed = t.of_type("TRICK_CLOSED")[-1]
    assert (closed["winner"], closed["nextLeader"], closed["chop"]) == (C, C, None)
    assert t.state.transfers == []


@pytest.mark.rule(46, 48)
def test_finishing_with_pair_of_heo_then_chopped_costs_nothing() -> None:
    t = Table(make_game(["5S 5C 4S", "2S 2H", f"{FK} 3D", "9H 10H"]))
    t.play(A, "5S 5C")
    t.play(B, "2S 2H")  # B về nhất bằng đôi heo
    t.play(C, FK)
    t.pass_(D)
    t.pass_(A)
    assert t.of_type("TRICK_CLOSED")[-1]["chop"] is None
    assert t.state.transfers == []


@pytest.mark.rule(41, 46, 48)
def test_finishing_with_chop_then_chopped_back_costs_nothing() -> None:
    t = Table(make_game(["2H 3S", PS3, f"{FK} 4D", "7H 8H"]))
    t.play(A, "2H")
    t.play(B, PS3)  # B chặt heo bằng lá cuối → về nhất
    t.play(C, FK)  # C chặt chồng người đã về
    t.pass_(D)
    t.pass_(A)
    assert t.of_type("TRICK_CLOSED")[-1]["chop"] is None
    assert t.state.transfers == []


@pytest.mark.rule(46)
def test_heo_chopped_while_owner_still_has_cards_still_pays() -> None:
    t = Table(make_game(["5S 4S", "2S 3D", f"{PS3} 3H", "9H 10H"]))
    t.play(A, "5S")
    t.play(B, "2S")  # B vẫn còn bài
    t.play(C, PS3)
    t.pass_(D)
    t.pass_(A)
    t.pass_(B)
    chop = t.of_type("TRICK_CLOSED")[-1]["chop"]
    assert (chop["from"], chop["to"], chop["amount"]) == (B, C, 100)


def test_chopped_player_can_chop_back_in_turn() -> None:
    t = Table(make_game([f"2H {FK}", f"{PS3} 3D", "4D 5D", "7H 8H"]))
    t.play(A, "2H")
    t.play(B, PS3)
    t.pass_(C)
    t.pass_(D)
    t.play(A, FK)  # A chặt lại 3 đôi thông của B
    t.pass_(B)  # C, D đã bỏ lượt từ trước → vòng đóng
    chop = t.of_type("TRICK_CLOSED")[-1]["chop"]
    assert (chop["from"], chop["to"], chop["amount"]) == (B, A, 400)


CONG_HAND = "2S 2H 7S 7C 7D 7H 8S 9S 10S JS QS KS AS"  # 13 lá: heo đen + heo đỏ + tứ quý 7


@pytest.mark.rule(68, 70, 71, 84, 123, 72, 73, 75)
def test_one_cong_player_pays_first_and_others_keep_playing() -> None:
    t = Table(make_game(["3C", "4S 4C", "5S 5C", CONG_HAND], played_counts=[12, 11, 11, 0]))
    t.play(A, "3C")
    assert t.of_type("CONG")[-1] == {"type": "CONG", "seats": [D], "allTable": False}
    assert (t.state.players[D].status, t.state.players[D].rank) == (PlayerStatus.CONG, 4)
    assert t.state.phase == Phase.PLAYING  # D15: 2 người còn lại đánh tiếp phân nhì/ba
    t.play(B, "4S")
    t.play(C, "5S")
    t.pass_(B)
    t.play(C, "5C")
    assert [p.rank for p in t.state.players] == [1, 3, 2, 4]
    # D7, D11, D12: D trả A 200 (cóng) + 100 + 200 + 200 (thối) ; B (ba) trả C (nhì) 100
    assert t.net == [700, -100, 100, -700]


@pytest.mark.rule(69)
def test_whole_table_cong_pays_first_with_rot() -> None:
    hands = [
        "3C",
        "4S 5S 6S 8C 9C 10C JC QC KC AC 4C 6D 9D",
        "3H 4H 5H 6H 8H 9H 10H JH QH KH AH 2D 3D",
        CONG_HAND,
    ]
    t = Table(make_game(hands, played_counts=[12, 0, 0, 0]))
    t.play(A, "3C")
    assert t.of_type("CONG")[-1]["allTable"] is True
    assert t.state.phase == Phase.FINISHED
    # B: 200; C: 200 + heo đỏ 2♦ 200; D: 200 + 500 thối
    assert t.net == [1300, -200, -400, -700]


def test_two_cong_players_remaining_player_gets_nothing() -> None:
    hands = ["3C", "4S", "4C 5C 6C 7C 8C 9C 10C JC QC KC AC 2C 3D", "4H 5H 6H 7H 8H 9H 10H JH QH KH AH 3H 5D"]
    t = Table(make_game(hands, played_counts=[12, 12, 0, 0]))
    t.play(A, "3C")
    assert t.state.phase == Phase.FINISHED
    assert t.state.players[B].rank == 2
    assert t.net == [500, 0, -300, -200]  # C: 200 + heo đen 2♣ 100; D: 200


@pytest.mark.rule(87, 145)
def test_forfeits_take_lowest_free_rank_and_rot_goes_to_first_when_third_also_left() -> None:
    t = Table(make_game(["3S 4S", "5S 6S", "7S 8S 2D", "9S 2S"]))
    t.forfeit(D)
    t.forfeit(C)
    assert (t.state.players[D].rank, t.state.players[C].rank) == (4, 3)  # D9
    t.play(A, "3S")
    t.play(B, "5S")
    t.pass_(A)
    t.play(B, "6S")
    assert t.state.phase == Phase.FINISHED
    assert [p.rank for p in t.state.players] == [2, 1, 3, 4]
    # D→B 200 (bét → nhất), thối 2♠ của D → B (vì hạng 3 là người thoát, G10); C→A 100
    assert t.net == [100, 300, -100, -300]


def test_forfeit_of_current_player_moves_turn_and_everyone_leaving_cancels() -> None:
    t = Table(make_game(["3S 4S", "5S 6S", "7S 8S", "9S 10S"]))
    t.forfeit(A)
    assert (t.state.current, t.state.trick.leader) == (B, B)
    t.forfeit(B)
    t.forfeit(C)
    assert t.state.phase == Phase.FINISHED  # còn 1 người → kết thúc
    assert t.state.players[D].rank == 1


@pytest.mark.rule(89, 90, 125)
def test_blind_three_spades_ends_game_immediately() -> None:
    t = Table(make_game(["3S", "4S 5S", "6S 7S", "8S 9S"]))
    t.play(A, "3S")
    assert (t.state.phase, t.state.end_type) == (Phase.FINISHED, EndType.BLIND_THREE_SPADES)
    assert t.net == [600, -200, -200, -200]


def test_three_spades_inside_a_combo_or_not_first_is_not_blind() -> None:
    t = Table(make_game(["3S 4C 5D", "6S 7S", "8S 9S", "10S JS"]))
    t.play(A, "3S 4C 5D")
    assert t.state.end_type is None
    t2 = Table(make_game(["4S", "3S", "8S 9S", "10S JS"]))
    t2.play(A, "4S")
    t2.pass_(B)
    t2.pass_(C)
    t2.pass_(D)
    t2.play(B, "3S")  # về nhì bằng 3♠: không phải đút mù
    assert t2.state.end_type != EndType.BLIND_THREE_SPADES
    disabled = Table(
        make_game(["3S", "4S 5S", "6S 7S", "8S 9S"]), rules_with(**{"special.blindThreeSpades": False})
    )
    disabled.play(A, "3S")
    assert disabled.state.end_type is None


def test_trapped_three_spades_pays_every_other_player() -> None:
    t = Table(make_game(["4S", "5S", "6S", "3S"]))
    t.play(A, "4S")
    t.play(B, "5S")
    t.play(C, "6S")
    assert t.net == [400, 300, 100, -800]  # ví dụ 8 (docs/gd2/03 §7)


@pytest.mark.rule(72, 73, 74, 85)
def test_rot_of_last_player_goes_to_third() -> None:
    t = Table(make_game(["3C", "4S", "5S", "6S 2H 2C"]))
    t.play(A, "3C")
    t.play(B, "4S")
    t.play(C, "5S")
    # D bét: 200 cho A; thối 2♥ 200 + 2♣ 100 cho C (người về 3); C trả B 100
    assert t.net == [200, 100, 200, -500]


def test_game_not_active_after_end() -> None:
    t = Table(make_game(["3C", "4S", "5S", "6S"]))
    t.play(A, "3C")
    t.play(B, "4S")
    t.play(C, "5S")
    with pytest.raises(MoveRejected) as exc:
        t.play(D, "6S")
    assert exc.value.code == "GAME_NOT_ACTIVE"


def test_reducer_does_not_mutate_input_state() -> None:
    state = make_game(["3S 9S", "4S 10S", "5S JS", "6S QS"])
    before = (list(state.players[0].hand), state.current, state.seq)
    Table(state, RULES).play(A, "3S")
    assert (state.players[0].hand, state.current, state.seq) == before


@pytest.mark.rule(46)
def test_player_may_finish_with_a_two_as_last_card() -> None:
    t = Table(make_game(["2S", "4S 5S", "6S 7S", "8S 9S"]))
    t.play(A, "2S")
    assert (t.state.players[A].status, t.state.players[A].rank) == (PlayerStatus.FINISHED, 1)


@pytest.mark.rule(47)
def test_chop_allowed_when_target_player_has_one_card_left() -> None:
    t = Table(make_game(["2H 3D", f"{FK} 3H", "4D 5D", "7H 8H"]))
    t.play(A, "2H")  # A còn đúng 1 lá
    t.play(B, FK)
    assert t.events[-2]["kind"] == "CHOP"

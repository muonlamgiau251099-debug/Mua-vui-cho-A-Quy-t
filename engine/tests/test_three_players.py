"""Ván 3 người: chia bài, người đánh đầu khi 3♣ không được chia (loại 3♠), tính điểm 300 / −100 / −200."""

import random

import pytest

from tlmn_engine.cards import THREE_CLUBS, THREE_SPADES, card_name, parse_card, parse_cards
from tlmn_engine.codec import state_from_json, state_hash, state_to_json
from tlmn_engine.dealing import (
    DealOutcome,
    DealResult,
    check_instant_win,
    deal,
    detect_redeal,
    determine_opener,
    start_game,
    undealt_cards,
)
from tlmn_engine.invariants import check_invariants
from tlmn_engine.projection import project_private, project_public
from tlmn_engine.reducer import MoveRejected, Play, Timeout, apply, must_include_three_clubs
from tlmn_engine.state import EndType, OpeningMode, Phase, PlayerStatus
from tlmn_testkit import RULES, Table, make_game, rules_with

A, B, C = 0, 1, 2


def deck_with(hands: list[str], undealt: str = "", *, allow_special: bool = False) -> list[int]:
    """Bộ 52 lá: các tay chỉ định (mỗi tay ≤ 13 lá), phần thiếu được điền ngẫu nhiên có seed; `undealt` là lá
    chắc chắn không được chia (nằm cuối bộ). Mặc định tự chọn seed sao cho không có tới trắng / chia lại."""
    fixed = [parse_cards(h) for h in hands]
    kept_back = parse_cards(undealt) if undealt else []
    used = {c for h in fixed for c in h} | set(kept_back)
    assert len(used) == sum(map(len, fixed)) + len(kept_back), "Có lá bị trùng"
    for seed in range(2000):
        pool = [c for c in range(52) if c not in used]
        random.Random(seed).shuffle(pool)
        deck: list[int] = []
        for h in fixed:
            deck.extend(sorted(h + [pool.pop() for _ in range(13 - len(h))]))
        deck.extend(kept_back)
        deck.extend(pool)  # phần còn lại nằm cuối bộ → là bài thừa
        assert sorted(deck) == list(range(52))
        players = len(fixed)
        dealt = deal(deck, players)
        if allow_special or (
            check_instant_win(dealt, 0, RULES) is None and detect_redeal(dealt, RULES) is None
        ):
            return deck
    raise AssertionError("Không dựng được bộ bài thỏa điều kiện")


def playing_deck(players: int) -> list[int]:
    """Bộ bài xáo (seed cố định) cho ra ván chơi bình thường: không tới trắng, không phải chia lại."""
    for seed in range(1000):
        deck = list(range(52))
        random.Random(seed).shuffle(deck)
        outcome = start_game(deck, OpeningMode.THREE_CLUBS, RULES, now=0.0, players=players)
        if outcome.result == DealResult.PLAYING:
            return deck
    raise AssertionError("Không tìm được bộ bài thỏa điều kiện")


def start3(
    deck: list[int], opening: OpeningMode = OpeningMode.THREE_CLUBS, previous_winner: int | None = None
) -> DealOutcome:
    return start_game(deck, opening, RULES, now=0.0, previous_winner=previous_winner, players=3)


# --- Chia bài 3 người ---------


def test_three_players_get_13_cards_each_and_13_are_left_undealt() -> None:
    deck = list(range(52))
    hands = deal(deck, 3)
    assert [len(h) for h in hands] == [13, 13, 13]
    assert undealt_cards(deck, 3) == deck[39:]
    assert sorted(c for h in hands for c in h) + undealt_cards(deck, 3) == sorted(deck)
    with pytest.raises(ValueError):
        deal(deck, 2)
    with pytest.raises(ValueError):
        deal(deck, 5)


def test_three_player_game_keeps_all_52_cards_and_hides_the_undealt_cards() -> None:
    outcome = start3(playing_deck(3))
    state = outcome.state
    assert state is not None and len(state.players) == 3 and len(state.undealt) == 13
    check_invariants(state)  # held + undealt + played = 52
    public = project_public(state)
    assert len(public["players"]) == 3 and "undealt" not in public
    private = project_private(state, 1)
    assert "undealt" not in private and private["yourHand"] == state.players[1].hand
    dealt = {c for p in state.players for c in p.hand}
    assert not dealt & set(state.undealt)


# --- Người đánh đầu (loại 3♠) ---------


def test_three_clubs_holder_still_leads_when_dealt() -> None:
    """Giữ nguyên luật cũ: có 3♣ thì người giữ 3♣ đánh đầu, kể cả khi 3♠ nằm ở người khác."""
    deck = deck_with(["4S 5S", "3S 6S", "3C 7S"])
    state = start3(deck).state
    assert state is not None
    assert (state.current, state.opening_card) == (C, THREE_CLUBS)
    assert state.opening_mode == OpeningMode.THREE_CLUBS
    assert must_include_three_clubs(state, RULES, C)


def test_only_three_spades_dealt_no_three_clubs_three_spades_never_decides_the_opener() -> None:
    """3♣ không được chia, 3♠ có người giữ: 3♠ bị loại; người giữ lá nhỏ nhất còn lại (3♦) đánh đầu."""
    deck = deck_with(["3S 9S", "3D 8S", "3H 7S"], undealt="3C")
    outcome = start3(deck)
    state = outcome.state
    assert state is not None
    holder_of_3s = next(s for s, p in enumerate(state.players) if THREE_SPADES in p.hand)
    assert holder_of_3s == A and state.current == B  # người giữ 3♠ KHÔNG được đánh đầu
    assert state.opening_card == parse_card("3D")
    assert state.opening_mode == OpeningMode.THREE_CLUBS and state.first_move_pending
    assert outcome.events[0]["openingCard"] == parse_card("3D") and outcome.events[0]["leader"] == B


def test_first_move_must_include_the_opening_card() -> None:
    deck = deck_with(["3S 9S", "3D 8S", "3H 7S"], undealt="3C")
    state = start3(deck).state
    assert state is not None and state.current == B
    with pytest.raises(MoveRejected) as exc:
        apply(state, Play(B, (parse_card("8S"),)), RULES, 1.0)  # không chứa 3♦
    assert exc.value.code == "MUST_INCLUDE_OPENING_CARD" and "3♦" in str(exc.value)
    with pytest.raises(MoveRejected) as other:
        apply(state, Play(A, (THREE_SPADES,)), RULES, 1.0)  # người giữ 3♠ không có quyền đánh đầu
    assert other.value.code == "NOT_YOUR_TURN"
    after, _ = apply(state, Play(B, (parse_card("3D"),)), RULES, 1.0)
    assert not after.first_move_pending and parse_card("3D") not in after.players[B].hand


def test_leader_may_open_with_a_combo_containing_the_opening_card() -> None:
    deck = deck_with(["4S 9S", "3D 3H 8S", "5S 7S"], undealt="3C 3S")
    state = start3(deck).state
    assert state is not None and state.current == B and state.opening_card == parse_card("3D")
    after, _ = apply(state, Play(B, tuple(parse_cards("3D 3H"))), RULES, 1.0)  # đôi có chứa lá bắt buộc
    assert after.trick.top is not None and len(after.trick.top.cards) == 2


def test_neither_three_clubs_nor_three_spades_dealt() -> None:
    """Cả 3♣ và 3♠ đều không được chia: lá nhỏ nhất đã chia (3♦) quyết định người đánh đầu."""
    deck = deck_with(["3H 9S", "3D 8S", "4S 7S"], undealt="3C 3S")
    state = start3(deck).state
    assert state is not None
    assert (state.current, state.opening_card) == (B, parse_card("3D"))


def test_opener_falls_through_ranks_when_all_threes_are_undealt() -> None:
    deck = deck_with(["5S 9S", "4C 8S", "4S 7S"], undealt="3S 3C 3D 3H")
    state = start3(deck).state
    assert state is not None
    # Nhỏ nhất đã chia là 4♠ (hạng 4, chất ♠ nhỏ hơn ♣): ghế C.
    assert (state.current, state.opening_card) == (C, parse_card("4S"))


def test_determine_opener_compares_by_current_card_order_and_ignores_three_spades() -> None:
    hands = [sorted(parse_cards("3S 4D")), sorted(parse_cards("4H 9S")), sorted(parse_cards("4C 8S"))]
    assert determine_opener(hands) == (parse_card("4C"), C)  # 3♠ bị bỏ; 4♣ < 4♦ < 4♥
    with_3c = [sorted(parse_cards("3S 4D")), sorted(parse_cards("4H 3C")), sorted(parse_cards("4C 8S"))]
    assert determine_opener(with_3c) == (THREE_CLUBS, B)


def test_only_three_spades_among_all_dealt_cards_still_does_not_make_that_player_lead() -> None:
    hands = [sorted(parse_cards("3S 9S")), sorted(parse_cards("5D 6S")), sorted(parse_cards("4S 8S"))]
    card, seat = determine_opener(hands)
    assert (card, seat) == (parse_card("4S"), C)  # 3♠ ở ghế A nhưng không dùng để xác định


def test_timeout_on_first_move_autoplays_the_opening_card_not_three_spades() -> None:
    deck = deck_with(["3S 9S", "3D 8S", "3H 7S"], undealt="3C")
    state = start3(deck).state
    assert state is not None
    after, events = apply(state, Timeout(), RULES, state.turn_deadline or 0.0)
    played = next(e for e in events if e["type"] == "PLAYED")
    assert played["cards"] == [parse_card("3D")] and played["auto"] is True and played["seat"] == B
    assert after.players[B].hand.count(parse_card("3D")) == 0


def test_opening_card_rule_respects_the_admin_toggle() -> None:
    rules = rules_with(**{"opening.mustIncludeThreeClubs": False})
    deck = deck_with(["3S 9S", "3D 8S", "3H 7S"], undealt="3C")
    state = start_game(deck, OpeningMode.THREE_CLUBS, rules, now=0.0, players=3).state
    assert state is not None
    assert not must_include_three_clubs(state, rules, B)
    apply(state, Play(B, (parse_card("8S"),)), rules, 1.0)  # luật tắt: đánh tự do


# --- Ván sau: người thắng ván trước ---------


def test_previous_winner_leads_the_next_game_when_still_playing() -> None:
    deck = deck_with(["3S 9S", "3D 8S", "3C 7S"])
    state = start3(deck, OpeningMode.WINNER_LEADS, previous_winner=A).state
    assert state is not None
    assert state.current == A and state.opening_mode == OpeningMode.WINNER_LEADS
    assert not must_include_three_clubs(state, RULES, A)  # người thắng ván trước đánh tự do


@pytest.mark.parametrize("previous_winner", [None, 3, -1])
def test_absent_previous_winner_falls_back_to_the_opener_rule(previous_winner: int | None) -> None:
    """Người thắng ván trước vắng mặt (không có ghế) → xác định lại bằng quy tắc 3♣ / lá nhỏ nhất."""
    deck = deck_with(["3S 9S", "3D 8S", "3H 7S"], undealt="3C")
    outcome = start3(deck, OpeningMode.WINNER_LEADS, previous_winner=previous_winner)
    state = outcome.state
    assert state is not None  # không bị kẹt, không ném lỗi
    assert state.opening_mode == OpeningMode.THREE_CLUBS
    assert (state.current, state.opening_card) == (B, parse_card("3D"))


def test_absent_previous_winner_with_three_clubs_dealt_uses_three_clubs() -> None:
    deck = deck_with(["3S 9S", "3D 8S", "3C 7S"])
    state = start3(deck, OpeningMode.WINNER_LEADS, previous_winner=None).state
    assert state is not None and (state.current, state.opening_card) == (C, THREE_CLUBS)


# --- Tới trắng / chia lại không đổi ---------


def test_redeal_is_only_checked_for_the_three_clubs_holder() -> None:
    four_threes_without_clubs = [sorted(parse_cards("3S 3D 3H 5S")), sorted(parse_cards("4S 6S"))]
    assert detect_redeal(four_threes_without_clubs, RULES) is None  # không ai giữ 3♣ → không có gì để xét
    holder = [sorted(parse_cards("3S 3C 3D 3H")), sorted(parse_cards("4S 6S"))]
    assert detect_redeal(holder, RULES) == "FOUR_THREES"


def test_instant_win_unchanged_with_three_players_and_pays_two_losers() -> None:
    four_twos = "2S 2C 2D 2H 4S 5S 6S 7S 8S 9S 10S JS QS"
    deck = deck_with([four_twos, "3S 3C", "3D 3H"], allow_special=True)
    outcome = start3(deck)
    assert outcome.result == DealResult.INSTANT_WIN
    state = outcome.state
    assert state is not None and state.end_type == EndType.INSTANT_WIN
    assert sorted(p.rank or 0 for p in state.players) == [1, 3, 3]  # người còn lại về hạng cuối (3)
    assert state.net() == [400, -200, -200]  # mỗi người thua trả 200


def test_blind_three_spades_unchanged_with_three_players() -> None:
    state = make_game(
        ["3S", "4S 5S", "6S 7S"], first_move=True, undealt="8S 9S 10S JS QS KS AS 2S 4C 5C 6C 7C 8C"
    )
    t = Table(state)
    t.play(A, "3S")  # về nhất bằng đúng 3♠ đánh đơn
    assert t.state.end_type == EndType.BLIND_THREE_SPADES
    assert t.net == [400, -200, -200]


# --- Điểm 300 / −100 / −200 ---------

UNDEALT13 = "3C 3D 3H 4C 4D 4H 5C 5D 5H 6C 6D 6H 7C"


def test_three_player_rank_points_first_300_second_minus_100_third_minus_200() -> None:
    t = Table(make_game(["4S", "5S", "9S 10S"], undealt=UNDEALT13, played_counts=[12, 12, 11]))
    t.play(A, "4S")  # nhất
    t.play(B, "5S")  # nhì; còn lại C xếp ba
    assert t.state.phase == Phase.FINISHED and t.state.end_type == EndType.NORMAL
    assert [p.rank for p in t.state.players] == [1, 2, 3]
    assert t.net == [300, -100, -200]
    ranks = [x for x in t.state.transfers if x.reason == "RANK"]
    assert {(x.from_seat, x.to_seat, x.amount) for x in ranks} == {(C, A, 200), (B, A, 100)}
    check_invariants(t.state)


def test_three_player_ranks_follow_finishing_order_not_seat_order() -> None:
    t = Table(make_game(["7S 8S", "4S", "5S"], current=B, undealt=UNDEALT13, played_counts=[11, 12, 12]))
    t.play(B, "4S")  # B nhất
    t.play(C, "5S")  # C nhì; A bét
    assert [p.rank for p in t.state.players] == [3, 1, 2]
    assert t.net == [-200, 300, -100]


def test_three_player_points_follow_the_admin_rank_values() -> None:
    rules = rules_with(
        **{
            "scoring.rank.first": 300,
            "scoring.rank.last": -300,
            "scoring.rank.second": 100,
            "scoring.rank.third": -100,
        }
    )
    t = Table(make_game(["4S", "5S", "9S 10S"], undealt=UNDEALT13, played_counts=[12, 12, 11]), rules)
    t.play(A, "4S")
    t.play(B, "5S")
    assert t.net == [400, -100, -300]  # bét trả nhất rank.first (300), nhì trả nhất rank.second (100)


def test_three_player_cong_both_losers_pay_the_cong_value_and_total_is_zero() -> None:
    """Người nhất đi hết bài khi cả hai người kia chưa đánh lá nào → cả hai bị cóng, mỗi người trả 200."""
    hand_b = "3S 3C 4C 5D 6H 7S 8C 9D 10H JS QC KD AH"  # không có heo, tứ quý hay đôi thông → không có thối
    hand_c = "3D 4H 5C 6D 7H 8D 9H 10D JH QD KH AD 9C"
    held = ["4S", hand_b, hand_c]
    used = {c for h in held for c in parse_cards(h)}
    assert len(used) == 27
    rest = [c for c in range(52) if c not in used][:13]
    t = Table(make_game(held, undealt=" ".join(card_name(c) for c in rest), played_counts=[12, 0, 0]))
    t.play(A, "4S")
    assert t.state.phase == Phase.FINISHED
    assert [p.status for p in t.state.players][1:] == [PlayerStatus.CONG, PlayerStatus.CONG]
    assert t.net == [400, -200, -200]
    assert sorted(p.rank or 0 for p in t.state.players) == [1, 2, 3]


def test_three_player_trapped_three_spades_pays_each_other_player() -> None:
    """Người bét còn đúng 1 lá 3♠ phải đền làng cho cả hai người kia (luật cũ, áp dụng theo số người)."""
    state = make_game(["4S", "5S", "3S"], current=A, undealt=UNDEALT13, played_counts=[12, 12, 12])
    t = Table(state)
    t.play(A, "4S")
    t.play(B, "5S")
    reasons = {x.reason for x in t.state.transfers}
    assert "TRAPPED_THREE_SPADES" in reasons
    assert sum(t.net) == 0 and t.net[C] < -200  # tiền bét cộng tiền đền làng


# --- Lưu trữ ---------


def test_three_player_state_roundtrips_through_json_with_undealt_and_opening_card() -> None:
    deck = deck_with(["3S 9S", "3D 8S", "3H 7S"], undealt="3C")
    state = start3(deck).state
    assert state is not None
    data = state_to_json(state)
    assert data["openingCard"] == parse_card("3D") and len(data["undealt"]) == 13
    restored = state_from_json(data)
    assert restored.opening_card == state.opening_card and restored.undealt == state.undealt
    assert state_hash(restored) == state_hash(state)


def test_four_player_snapshots_are_unchanged_so_old_games_keep_their_hash() -> None:
    state = start_game(playing_deck(4), OpeningMode.THREE_CLUBS, RULES, now=0.0).state
    assert state is not None
    data = state_to_json(state)
    assert "openingCard" not in data and "undealt" not in data  # 4 người, mở bằng 3♣: JSON y hệt trước đây
    legacy = {k: v for k, v in data.items()}
    restored = state_from_json(legacy)
    assert restored.opening_card == THREE_CLUBS and restored.undealt == [] and len(restored.players) == 4
    assert state_hash(restored) == state_hash(state)

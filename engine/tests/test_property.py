"""Property test: chơi ván ngẫu nhiên với nước đi hợp lệ ngẫu nhiên (AC2, docs/gd2/06 §3).

Số ván mặc định 300 (chạy nhanh trong CI). Chạy đủ 10.000 ván: TLMN_PROPERTY_GAMES=10000 uv run pytest ...
"""

import itertools
import os
import random
from collections import defaultdict

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tlmn_engine.beats import MoveRejected, can_beat, can_interrupt
from tlmn_engine.cards import TWO_RANK, rank
from tlmn_engine.combos import Combo, classify
from tlmn_engine.dealing import DealResult, start_game
from tlmn_engine.invariants import check_invariants
from tlmn_engine.projection import project_private, project_public
from tlmn_engine.reducer import Action, Forfeit, Pass, Play, Timeout, apply, must_include_three_clubs
from tlmn_engine.rules_config import RuleConfig
from tlmn_engine.state import EndType, GameState, OpeningMode, Phase, PlayerStatus
from tlmn_testkit import RULES, rules_with

GAMES = int(os.environ.get("TLMN_PROPERTY_GAMES", "300"))
MAX_ACTIONS = 3000


def candidate_combos(hand: list[int], rng: random.Random) -> list[Combo]:
    """Một tập con đại diện các bộ có thể đánh từ bài trên tay."""
    by_rank: dict[int, list[int]] = defaultdict(list)
    for c in hand:
        by_rank[rank(c)].append(c)
    raw: list[tuple[int, ...]] = [(c,) for c in hand]
    for cards in by_rank.values():
        for size in (2, 3, 4):
            raw.extend(itertools.combinations(cards, size))
    ranks = sorted(r for r in by_rank if r != TWO_RANK)
    for i, start in enumerate(ranks):
        run = [start]
        for r in ranks[i + 1 :]:
            if r != run[-1] + 1:
                break
            run.append(r)
            if len(run) >= 3:
                raw.append(tuple(rng.choice(by_rank[x]) for x in run))  # sảnh
                if all(len(by_rank[x]) >= 2 for x in run):
                    raw.append(tuple(c for x in run for c in sorted(by_rank[x])[:2]))  # đôi thông
    combos = [classify(cards) for cards in raw]
    return [c for c in combos if c is not None]


def legal_for(state: GameState, seat: int, rules: RuleConfig, rng: random.Random) -> list[Combo]:
    out = []
    for combo in candidate_combos(state.players[seat].hand, rng):
        try:
            can_beat(
                rules,
                state.trick.top,
                combo,
                must_include_three_clubs=must_include_three_clubs(state, rules, seat),
                opening_card=state.opening_card,
                top_is_chop=state.trick.top_is_chop,
                someone_finished=state.someone_finished(),
            )
        except MoveRejected:
            continue
        out.append(combo)
    return out


def interrupters(state: GameState, rules: RuleConfig, rng: random.Random) -> list[Play]:
    if state.trick.top is None:
        return []
    moves = []
    for seat in state.active_seats():
        if seat in (state.current, state.trick.top_seat):
            continue
        for combo in legal_for(state, seat, rules, rng):
            result = can_beat(
                rules,
                state.trick.top,
                combo,
                must_include_three_clubs=False,
                top_is_chop=state.trick.top_is_chop,
                someone_finished=state.someone_finished(),
            )
            if can_interrupt(rules, combo, result):
                moves.append(Play(seat, combo.cards))
    return moves


def choose_action(state: GameState, rules: RuleConfig, rng: random.Random, forfeits: int) -> Action:
    roll = rng.random()
    if roll < 0.01 and forfeits < len(state.players) - 2:  # luôn còn ít nhất 2 người để ván tiếp diễn
        return Forfeit(rng.choice(state.active_seats()))
    if roll < 0.08:
        return Timeout()
    if roll < 0.15:
        cuts = interrupters(state, rules, rng)
        if cuts:
            return rng.choice(cuts)
    legal = legal_for(state, state.current, rules, rng)
    if state.trick.top is not None and (not legal or rng.random() < 0.25):
        return Pass(state.current)
    assert legal, "Người mở vòng luôn phải có nước đi hợp lệ"
    return Play(state.current, rng.choice(legal).cards)


def assert_no_leak(state: GameState) -> None:
    """ID 152: khi đang chơi, dữ liệu gửi cho mỗi người chỉ chứa bài của chính họ."""
    public = project_public(state)
    if state.phase == Phase.PLAYING:
        assert "hands" not in public
        for seat in range(len(state.players)):
            private = project_private(state, seat)
            assert private["yourHand"] == state.players[seat].hand
            others = {c for s, p in enumerate(state.players) if s != seat for c in p.hand}
            assert not others & set(private["yourHand"])
            assert all(key != "hands" for key in private)


def play_random_game(
    seed: int, rules: RuleConfig = RULES, players: int = 4
) -> tuple[GameState, list[tuple[Action, float]], GameState]:
    rng = random.Random(seed)
    deck = list(range(52))
    for _ in range(100):
        rng.shuffle(deck)
        opening = rng.choice([OpeningMode.THREE_CLUBS, OpeningMode.WINNER_LEADS])
        winner = rng.randrange(players)
        outcome = start_game(deck, opening, rules, now=0.0, previous_winner=winner, players=players)
        if outcome.result != DealResult.REDEAL:
            break
    assert outcome.state is not None
    initial = outcome.state
    check_invariants(initial)
    state, now, history, forfeits = initial, 0.0, [], 0
    while state.phase == Phase.PLAYING:
        assert len(history) < MAX_ACTIONS, "Ván không kết thúc"
        action = choose_action(state, rules, rng, forfeits)
        if isinstance(action, Timeout):
            now = max(now, state.turn_deadline or now)
        else:
            now += rng.uniform(0.1, 5.0)
        try:
            state, _ = apply(state, action, rules, now)
        except MoveRejected:
            continue  # nước đi ngẫu nhiên có thể bị từ chối (vd hết giờ chưa tới) — trạng thái không đổi
        history.append((action, now))
        forfeits += isinstance(action, Forfeit)
        check_invariants(state)
        assert_no_leak(state)
    return initial, history, state


def check_final(final: GameState) -> None:
    assert final.phase in (Phase.FINISHED, Phase.CANCELLED)
    assert sum(final.net()) == 0  # ID 133
    if final.end_type == EndType.NORMAL:
        assert sorted(p.rank or 0 for p in final.players) == list(range(1, len(final.players) + 1))
        first = next(s for s, p in enumerate(final.players) if p.rank == 1)
        assert final.players[first].status == PlayerStatus.FINISHED
        assert not final.players[first].hand
    project_public(final)


@pytest.mark.rule(1, 2, 3, 4, 133, 151, 152)
@settings(max_examples=GAMES, deadline=None, derandomize=True)
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_random_games_keep_invariants_and_replay_identically(seed: int) -> None:
    initial, history, final = play_random_game(seed)
    check_final(final)
    # Replay deterministic: áp lại đúng chuỗi action → đúng trạng thái cuối (P5).
    state = initial
    for action, now in history:
        state, _ = apply(state, action, RULES, now)
    assert project_public(state) == project_public(final)
    assert [p.hand for p in state.players] == [p.hand for p in final.players]


@settings(max_examples=max(50, GAMES // 4), deadline=None, derandomize=True)
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_random_games_with_admin_variations_end_and_stay_zero_sum(seed: int) -> None:
    rules = rules_with(
        **{
            "chop.allowChain": seed % 2 == 0,
            "chop.fourPairSeq.outOfTurn": seed % 3 != 0,
            "penalty.cong.enabled": seed % 5 != 0,
            "scoring.rank.first": 300,
            "scoring.rank.last": -300,
        }
    )
    _, _, final = play_random_game(seed, rules)
    assert final.phase in (Phase.FINISHED, Phase.CANCELLED)
    assert sum(final.net()) == 0


def test_timeouts_alone_always_finish_the_game() -> None:
    """P6: kể cả khi không ai thao tác, server tự pass / tự đánh lá nhỏ nhất → ván luôn kết thúc."""
    for seed in range(50):
        rng = random.Random(seed)
        deck = list(range(52))
        rng.shuffle(deck)
        outcome = start_game(deck, OpeningMode.WINNER_LEADS, RULES, now=0.0, previous_winner=0)
        state = outcome.state
        assert state is not None
        steps = 0
        while state.phase == Phase.PLAYING:
            state, _ = apply(state, Timeout(), RULES, state.turn_deadline or 0.0)
            check_invariants(state)
            steps += 1
            assert steps < 400
        assert sum(state.net()) == 0


@settings(max_examples=GAMES, deadline=None, derandomize=True)
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_random_three_player_games_keep_invariants_and_replay_identically(seed: int) -> None:
    """Ván 3 người: 39 lá chia + 13 lá thừa đủ 52 lá, không lộ bài, zero-sum, hạng 1–3, replay giống hệt."""
    initial, history, final = play_random_game(seed, players=3)
    assert len(initial.players) == 3 and len(initial.undealt) == 13
    check_final(final)
    state = initial
    for action, now in history:
        state, _ = apply(state, action, RULES, now)
    assert project_public(state) == project_public(final)
    assert [p.hand for p in state.players] == [p.hand for p in final.players]


@settings(max_examples=max(50, GAMES // 4), deadline=None, derandomize=True)
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_random_three_player_games_with_admin_variations_stay_zero_sum(seed: int) -> None:
    rules = rules_with(
        **{
            "chop.allowChain": seed % 2 == 0,
            "penalty.cong.enabled": seed % 5 != 0,
            "scoring.rank.first": 300,
            "scoring.rank.last": -300,
        }
    )
    _, _, final = play_random_game(seed, rules, players=3)
    assert final.phase in (Phase.FINISHED, Phase.CANCELLED)
    assert sum(final.net()) == 0


def test_three_player_timeouts_alone_always_finish_the_game() -> None:
    for seed in range(50):
        rng = random.Random(seed)
        deck = list(range(52))
        for _ in range(100):
            rng.shuffle(deck)
            outcome = start_game(deck, OpeningMode.THREE_CLUBS, RULES, now=0.0, players=3)
            if outcome.result != DealResult.REDEAL:
                break
        state = outcome.state
        assert state is not None  # luôn có người đánh đầu, kể cả khi 3♣ không được chia
        steps = 0
        while state.phase == Phase.PLAYING:
            state, _ = apply(state, Timeout(), RULES, state.turn_deadline or 0.0)
            check_invariants(state)
            steps += 1
            assert steps < 400
        assert sum(state.net()) == 0

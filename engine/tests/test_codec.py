import random

import pytest

from test_property import play_random_game
from tlmn_engine.codec import action_from_json, action_to_json, state_from_json, state_hash, state_to_json
from tlmn_engine.reducer import Forfeit, Pass, Play, ResumeTimer, Timeout, apply
from tlmn_testkit import RULES, Table, make_game


def test_state_roundtrips_through_json_mid_game() -> None:
    t = Table(make_game(["2H 3S", "6S 6C 7S 7C 8S 8C 3D", "KS KC KD KH 4D", "7H 8H"]))
    t.play(0, "2H")
    t.play(1, "6S 6C 7S 7C 8S 8C")  # chặt → chuỗi chặt đang mở
    t.pass_(2)
    restored = state_from_json(state_to_json(t.state))
    assert state_to_json(restored) == state_to_json(t.state)
    assert state_hash(restored) == state_hash(t.state)
    assert restored.trick.chain == t.state.trick.chain


@pytest.mark.rule(149)
def test_snapshot_plus_replay_reproduces_every_random_game() -> None:
    """Khôi phục = snapshot bất kỳ + áp lại các action sau đó → đúng trạng thái cuối (ADR-005)."""
    for seed in range(40):
        initial, history, final = play_random_game(seed)
        cut = random.Random(seed).randrange(len(history) + 1)
        state = initial
        for action, now in history[:cut]:
            state, _ = apply(state, action, RULES, now)
        state = state_from_json(state_to_json(state))  # "ghi DB rồi đọc lại"
        for action, now in history[cut:]:
            stored = action_from_json(action_to_json(action))
            state, _ = apply(state, stored, RULES, now)
        assert state_hash(state) == state_hash(final)


def test_resume_timer_grants_full_turn_and_is_replayable() -> None:
    t = Table(make_game(["3S 9S", "4S 10S", "5S JS", "6S QS"]), now=100.0)
    t.now = 500.0  # server khởi động lại sau một lúc lâu
    events = t.do(ResumeTimer())
    assert events == [{"type": "TURN_RESUMED", "seat": 0, "deadline": 530.0}]
    assert t.state.turn_deadline == 530.0


@pytest.mark.parametrize("action", [Play(1, (4, 9)), Pass(2), Timeout(), Forfeit(3), ResumeTimer()])
def test_actions_roundtrip(action: object) -> None:
    assert action_from_json(action_to_json(action)) == action  # type: ignore[arg-type]

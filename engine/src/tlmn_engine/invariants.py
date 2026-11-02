"""Bất biến của ván — kiểm tra sau mỗi action trong test (docs/gd2/03 §5)."""

from tlmn_engine.cards import DECK_SIZE
from tlmn_engine.state import GameState, Phase, PlayerStatus


class InvariantViolation(AssertionError):
    pass


def check_invariants(state: GameState) -> None:
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise InvariantViolation(message)

    held = [c for p in state.players for c in p.hand]
    everything = held + state.played
    require(
        len(everything) == DECK_SIZE and set(everything) == set(range(DECK_SIZE)), "52 lá bị trùng hoặc mất"
    )
    require(sum(p.played_count for p in state.players) == len(state.played), "Số lá đã đánh không khớp")
    require(all(p.hand == sorted(p.hand) for p in state.players), "Bài trên tay phải được sắp xếp")
    require(sum(state.net()) == 0, "Tổng điểm của ván phải bằng 0")
    require(all(t.amount > 0 and t.from_seat != t.to_seat for t in state.transfers), "Khoản chuyển điểm sai")
    require(
        (state.trick.top is None) == (state.trick.top_seat is None), "Bài trên bàn và người đánh không khớp"
    )

    if state.phase == Phase.PLAYING:
        require(
            state.players[state.current].status == PlayerStatus.ACTIVE, "Người giữ lượt không còn trong ván"
        )
        require(state.current not in state.trick.passed, "Người giữ lượt đã bỏ lượt")
        ranks = [p.rank for p in state.players if p.rank is not None]
        require(len(ranks) == len(set(ranks)), "Thứ hạng bị trùng")
        require(
            all((p.rank is None) == (p.status == PlayerStatus.ACTIVE) for p in state.players),
            "Người còn chơi không được có thứ hạng",
        )
        require(len(state.active_seats()) >= 2, "Ván đang chơi phải còn ít nhất 2 người")
    elif state.phase == Phase.FINISHED and state.end_type == "NORMAL":
        require(sorted(p.rank or 0 for p in state.players) == [1, 2, 3, 4], "Thứ hạng cuối ván phải là 1–4")

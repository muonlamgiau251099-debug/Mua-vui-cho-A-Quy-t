"""Trạng thái một ván (docs/gd2/03 §4). Reducer luôn làm việc trên bản sao (clone)."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from tlmn_engine.combos import Combo

SEATS = 4  # ID 2


class Phase(StrEnum):
    PLAYING = "PLAYING"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class PlayerStatus(StrEnum):
    ACTIVE = "ACTIVE"
    FINISHED = "FINISHED"  # đã hết bài
    CONG = "CONG"  # bị cóng (bị nhốt): dừng ngay, xếp bét (D7)
    FORFEITED = "FORFEITED"  # thoát giữa ván (D9)


class OpeningMode(StrEnum):
    THREE_CLUBS = "THREE_CLUBS"  # ván đầu / sau tới trắng / sau ván hủy: 3♣ đi đầu (ID 7, 60)
    WINNER_LEADS = "WINNER_LEADS"  # người nhất ván trước đi đầu (ID 9)


class EndType(StrEnum):
    NORMAL = "NORMAL"
    INSTANT_WIN = "INSTANT_WIN"
    BLIND_THREE_SPADES = "BLIND_THREE_SPADES"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class ChopLink:
    chopper: int
    victim: int
    value: int


@dataclass(frozen=True, slots=True)
class Transfer:
    """Một khoản chuyển điểm. Tổng mọi transfer của ván luôn bằng 0 (ID 132, 133)."""

    from_seat: int
    to_seat: int
    amount: int
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "from": self.from_seat,
            "to": self.to_seat,
            "amount": self.amount,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass(slots=True)
class Trick:
    leader: int
    top: Combo | None = None
    top_seat: int | None = None
    top_is_chop: bool = False  # bài trên bàn là một nước chặt / hàng đè hàng
    passed: set[int] = field(default_factory=set)
    chain: list[ChopLink] = field(default_factory=list)

    def clone(self) -> "Trick":
        return Trick(
            self.leader, self.top, self.top_seat, self.top_is_chop, set(self.passed), list(self.chain)
        )


@dataclass(slots=True)
class PlayerState:
    hand: list[int]
    played_count: int = 0
    status: PlayerStatus = PlayerStatus.ACTIVE
    rank: int | None = None

    def clone(self) -> "PlayerState":
        return PlayerState(list(self.hand), self.played_count, self.status, self.rank)


@dataclass(slots=True)
class GameState:
    players: list[PlayerState]
    opening_mode: OpeningMode
    current: int
    trick: Trick
    first_move_pending: bool  # nước đầu tiên của ván chưa được đánh
    turn_deadline: float | None = None
    phase: Phase = Phase.PLAYING
    end_type: EndType | None = None
    played: list[int] = field(default_factory=list)
    finish_order: list[int] = field(default_factory=list)
    transfers: list[Transfer] = field(default_factory=list)
    seq: int = 0  # số action đã áp dụng

    def clone(self) -> "GameState":
        return GameState(
            players=[p.clone() for p in self.players],
            opening_mode=self.opening_mode,
            current=self.current,
            trick=self.trick.clone(),
            first_move_pending=self.first_move_pending,
            turn_deadline=self.turn_deadline,
            phase=self.phase,
            end_type=self.end_type,
            played=list(self.played),
            finish_order=list(self.finish_order),
            transfers=list(self.transfers),
            seq=self.seq,
        )

    def active_seats(self) -> list[int]:
        return [s for s, p in enumerate(self.players) if p.status == PlayerStatus.ACTIVE]

    def someone_finished(self) -> bool:
        return any(p.status == PlayerStatus.FINISHED for p in self.players)

    def net(self) -> list[int]:
        totals = [0] * SEATS
        for t in self.transfers:
            totals[t.from_seat] -= t.amount
            totals[t.to_seat] += t.amount
        return totals


def clockwise_after(seat: int) -> list[int]:
    """Ba ghế kế tiếp theo chiều kim đồng hồ (ID 4)."""
    return [(seat + step) % SEATS for step in range(1, SEATS)]


def clockwise_from(seat: int) -> list[int]:
    return [seat, *clockwise_after(seat)]

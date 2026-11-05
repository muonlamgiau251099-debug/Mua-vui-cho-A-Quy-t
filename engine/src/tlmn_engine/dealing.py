"""Chia bài, tới trắng, chia lại, bắt đầu ván (ID 3, 7–9, 49–67, 107, 124; D4, D5, R7, N1, N2).

Engine không tự xáo bài: server truyền vào bộ bài đã xáo (ADR-007, ADR-008).
"""

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from tlmn_engine.cards import DECK_SIZE, THREE_CLUBS, THREE_SPADES, TWO_RANK, rank
from tlmn_engine.rules_config import RuleConfig
from tlmn_engine.scoring import instant_win_transfers
from tlmn_engine.state import (
    PLAYER_COUNTS,
    SEATS,
    EndType,
    GameState,
    OpeningMode,
    Phase,
    PlayerState,
    PlayerStatus,
    Trick,
    clockwise_from,
)

CARDS_PER_PLAYER = 13  # ID 3


class InstantWinKind(StrEnum):
    FOUR_TWOS = "FOUR_TWOS"  # ID 49: tứ quý 2
    SIX_PAIRS = "SIX_PAIRS"  # ID 52: 6 đôi bất kỳ (tứ quý tính 2 đôi — Q-P1-5)
    DRAGON = "DRAGON"  # ID 53: sảnh rồng 3 → A


def deal(deck: list[int], players: int = SEATS) -> list[list[int]]:
    """Chia 13 lá cho mỗi người (ID 3). Ván 3 người chia 39 lá, 13 lá còn lại không chia (`undealt_cards`)."""
    if sorted(deck) != list(range(DECK_SIZE)):
        raise ValueError("Bộ bài phải gồm đúng 52 lá khác nhau")
    if players not in PLAYER_COUNTS:
        raise ValueError(f"Ván chỉ có {PLAYER_COUNTS[0]} hoặc {PLAYER_COUNTS[-1]} người chơi")
    return [sorted(deck[s * CARDS_PER_PLAYER : (s + 1) * CARDS_PER_PLAYER]) for s in range(players)]


def undealt_cards(deck: list[int], players: int = SEATS) -> list[int]:
    """Bài thừa không chia cho ai; không bao giờ được dùng để xác định người đánh đầu."""
    return sorted(deck[players * CARDS_PER_PLAYER :])


def determine_opener(hands: list[list[int]]) -> tuple[int, int]:
    """Trả về (lá mở ván, ghế đánh đầu) cho ván không do người thắng ván trước mở (ID 7).

    - Có người giữ 3♣ → người đó đánh đầu, lá bắt buộc là 3♣ (giữ nguyên luật cũ).
    - Không ai giữ 3♣ (ván 3 người có thể không chia 3♣) → người giữ lá nhỏ nhất trong các lá ĐÃ CHIA, loại 3♠
      khỏi việc xét: 3♠ không bao giờ được dùng để xác định quyền đánh đầu. So lá theo hạng rồi chất hiện tại.
    """
    holder = next((seat for seat, hand in enumerate(hands) if THREE_CLUBS in hand), None)
    if holder is not None:
        return THREE_CLUBS, holder
    card, seat = min((c, s) for s, hand in enumerate(hands) for c in hand if c != THREE_SPADES)
    return card, seat


def qualifies(hand: list[int], kind: InstantWinKind) -> bool:
    counts = Counter(rank(c) for c in hand)
    if kind == InstantWinKind.FOUR_TWOS:
        return counts[TWO_RANK] == 4
    if kind == InstantWinKind.SIX_PAIRS:
        return sum(v // 2 for v in counts.values()) >= 6
    return all(counts[r] >= 1 for r in range(TWO_RANK))  # DRAGON: đủ 12 số 3..A


def _enabled(rules: RuleConfig, kind: InstantWinKind) -> bool:
    iw = rules.instantWin
    return {
        InstantWinKind.FOUR_TWOS: iw.fourTwos,
        InstantWinKind.SIX_PAIRS: iw.sixPairs,
        InstantWinKind.DRAGON: iw.dragonStraight,
    }[kind]


@dataclass(frozen=True, slots=True)
class InstantWin:
    kind: InstantWinKind
    winners: list[int]  # theo thứ tự đi từ người mở ván


def check_instant_win(hands: list[list[int]], leader: int, rules: RuleConfig) -> InstantWin | None:
    for name in rules.instantWin.priorityOrder:  # ID 62/64 (N1: 4 heo > sảnh rồng > 6 đôi)
        kind = InstantWinKind(name)
        if not _enabled(rules, kind):
            continue
        seats = [s for s in clockwise_from(leader, len(hands)) if qualifies(hands[s], kind)]
        if seats:
            if rules.instantWin.tieBreak == "FIRST_IN_TURN_ORDER":  # ID 63
                seats = seats[:1]
            return InstantWin(kind, seats)  # N2: cùng loại → chia tiền
    return None


def detect_redeal(hands: list[list[int]], rules: RuleConfig) -> str | None:
    """ID 58, 59: chỉ xét ở ván mở bằng 3♣, cho người đang giữ 3♣ (không ai giữ 3♣ thì không xét)."""
    holder = next((s for s, hand in enumerate(hands) if THREE_CLUBS in hand), None)
    if holder is None:
        return None
    counts = Counter(rank(c) for c in hands[holder])
    if rules.redeal.fourThrees and counts[0] == 4:
        return "FOUR_THREES"
    if rules.redeal.pairSeqWithThreeClubs and counts[0] >= 2 and counts[1] >= 2 and counts[2] >= 2:
        return "PAIR_SEQ_WITH_THREE_CLUBS"
    return None


class DealResult(StrEnum):
    PLAYING = "PLAYING"
    INSTANT_WIN = "INSTANT_WIN"
    REDEAL = "REDEAL"


@dataclass(frozen=True, slots=True)
class DealOutcome:
    result: DealResult
    state: GameState | None
    events: list[dict[str, Any]]


def start_game(
    deck: list[int],
    opening: OpeningMode,
    rules: RuleConfig,
    now: float,
    previous_winner: int | None = None,
    players: int = SEATS,
) -> DealOutcome:
    """Chia bài và xác định ván: chơi bình thường, tới trắng (kết thúc ngay) hoặc phải chia lại.

    Người đánh đầu: người thắng ván trước nếu còn tham gia (ID 9); ngược lại (ván đầu phiên, sau tới trắng,
    đút mù hoặc ván hủy, hay người thắng ván trước vắng mặt) → `determine_opener`: người giữ 3♣, không có thì
    người giữ lá nhỏ nhất đã chia (loại 3♠). Luôn có người đánh đầu và lá bắt buộc nên ván không bị kẹt.
    """
    hands = deal(deck, players)
    opening_card = THREE_CLUBS
    if opening == OpeningMode.WINNER_LEADS and previous_winner is not None and 0 <= previous_winner < players:
        leader = previous_winner  # ID 9
    else:
        opening = OpeningMode.THREE_CLUBS  # xác định lại bằng quy tắc 3♣ (vd người thắng ván trước vắng mặt)
        opening_card, leader = determine_opener(hands)  # ID 7
    seats = [PlayerState(hand) for hand in hands]
    state = GameState(
        players=seats,
        opening_mode=opening,
        current=leader,
        trick=Trick(leader),
        first_move_pending=True,
        undealt=undealt_cards(deck, players),
        opening_card=opening_card,
    )

    win = check_instant_win(hands, leader, rules)  # R7: xét tới trắng trước chia lại
    if win is not None:  # ID 66: tới trắng kết thúc ngay sau khi chia bài
        for seat, player in enumerate(seats):
            player.rank = 1 if seat in win.winners else players  # D4, ID 107: người còn lại về hạng cuối
            player.status = PlayerStatus.FINISHED
        state.phase = Phase.FINISHED
        state.end_type = EndType.INSTANT_WIN
        state.current = win.winners[0]
        state.transfers = instant_win_transfers(
            win.winners, rules, rules.scoring.instantWinPerLoser, "INSTANT_WIN", players
        )
        event = {"type": "INSTANT_WIN", "kind": win.kind.value, "winners": win.winners}
        return DealOutcome(DealResult.INSTANT_WIN, state, [event])

    if opening == OpeningMode.THREE_CLUBS:
        reason = detect_redeal(hands, rules)
        if reason is not None:
            return DealOutcome(DealResult.REDEAL, None, [{"type": "REDEAL", "reason": reason}])

    state.turn_deadline = now + rules.turn.timeLimitSeconds
    events: list[dict[str, Any]] = [
        {
            "type": "GAME_STARTED",
            "openingMode": opening.value,
            "openingCard": opening_card,
            "leader": leader,
            "players": players,
        },
        {"type": "TURN_STARTED", "seat": leader, "deadline": state.turn_deadline},
    ]
    return DealOutcome(DealResult.PLAYING, state, events)


def next_opening(previous_end_type: EndType | None, previous_winner: int | None) -> OpeningMode:
    """3♣ đi đầu ở ván đầu phiên, sau tới trắng (ID 60), sau đút mù 3♠ (yêu cầu mới, ghi đè D10) và sau
    ván bị hủy (G8); còn lại người nhất đi đầu."""
    special_end = (None, EndType.INSTANT_WIN, EndType.BLIND_THREE_SPADES, EndType.CANCELLED)
    if previous_end_type in special_end or previous_winner is None:
        return OpeningMode.THREE_CLUBS
    return OpeningMode.WINNER_LEADS

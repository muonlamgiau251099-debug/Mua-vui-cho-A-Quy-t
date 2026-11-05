"""Dữ liệu gửi cho client. CHỈ được tạo dữ liệu gửi đi qua hai hàm này (ID 152; docs/gd2/06 §1).

Bài trên tay người khác không bao giờ có trong payload khi ván đang chơi; hết ván mới lộ toàn bộ.
"""

from typing import Any

from tlmn_engine.state import GameState, Phase


def project_public(state: GameState) -> dict[str, Any]:
    trick = state.trick
    data: dict[str, Any] = {
        "phase": state.phase.value,
        "openingMode": state.opening_mode.value,
        "current": state.current if state.phase == Phase.PLAYING else None,
        "turnDeadline": state.turn_deadline,
        "firstMovePending": state.first_move_pending,
        "openingCard": state.opening_card,  # lá người đánh đầu phải có (3♣ hoặc lá thay thế)
        "trick": {
            "leader": trick.leader,
            "top": list(trick.top.cards) if trick.top else None,
            "topCombo": trick.top.type.value if trick.top else None,
            "topSeat": trick.top_seat,
            "topIsChop": trick.top_is_chop,
            "passed": sorted(trick.passed),
            "chainValue": sum(link.value for link in trick.chain),
        },
        "players": [
            {
                "seat": seat,
                "cardCount": len(p.hand),
                "playedCount": p.played_count,
                "status": p.status.value,
                "rank": p.rank,
            }
            for seat, p in enumerate(state.players)
        ],
        "finishOrder": list(state.finish_order),
        "endType": state.end_type.value if state.end_type else None,
        "transfers": [t.to_json() for t in state.transfers],
        "net": state.net(),
    }
    if state.phase != Phase.PLAYING:
        data["hands"] = [list(p.hand) for p in state.players]  # hết ván: lộ bài để đối chiếu thối
    return data


def project_private(state: GameState, seat: int) -> dict[str, Any]:
    return {**project_public(state), "yourSeat": seat, "yourHand": list(state.players[seat].hand)}

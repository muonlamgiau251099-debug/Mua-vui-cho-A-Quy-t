"""Sổ điểm: mọi biến động là một Transfer (docs/gd2/03 §7; ID 80–90, 111–133; D3, D4, D7–D12, N2, N6).

Điểm hạng là các cặp chuyển (ván 4 người): bét → nhất (rank.first), ba → nhì (rank.second) — V1 bảo đảm
rank.first = −rank.last và rank.second = −rank.third. Người cóng trả congValue cho người nhất thay
cho điểm bét. Vì mọi khoản đều là chuyển từ người này sang người kia nên tổng mỗi ván luôn bằng 0.
"""

from tlmn_engine.cards import THREE_SPADES
from tlmn_engine.rot import compute_rot
from tlmn_engine.rules_config import RuleConfig
from tlmn_engine.state import SEATS, ChopLink, GameState, PlayerStatus, Transfer, clockwise_from

CONG_STATUS = PlayerStatus.CONG


def settle_chain(chain: list[ChopLink]) -> Transfer | None:
    """Chặt chồng cộng dồn (D3): người bị chặt cuối cùng trả tổng giá trị cả chuỗi cho người chặt cuối."""
    if not chain:
        return None
    last = chain[-1]
    total = sum(link.value for link in chain)
    if total <= 0:
        return None
    links = [{"chopper": link.chopper, "victim": link.victim, "value": link.value} for link in chain]
    return Transfer(last.victim, last.chopper, total, "CHOP_CHAIN", {"links": links})


def _seat_with_rank(state: GameState, wanted: int) -> int | None:
    return next((s for s, p in enumerate(state.players) if p.rank == wanted), None)


def _add(out: list[Transfer], src: int, dst: int, amount: int, reason: str, **detail: object) -> None:
    if amount > 0 and src != dst:
        out.append(Transfer(src, dst, amount, reason, dict(detail)))


def _rot_transfers(
    state: GameState, rules: RuleConfig, seat: int, recipient: int, out: list[Transfer]
) -> None:
    for item in compute_rot(state.players[seat].hand, rules):
        _add(out, seat, recipient, item.value, f"ROT_{item.kind}", cards=list(item.cards))


def normal_end_transfers(state: GameState, rules: RuleConfig) -> list[Transfer]:
    """Kết thúc bình thường: cóng, điểm hạng, thối, bị nhốt 3♠.

    Ván 4 người: bét → nhất (rank.first), ba → nhì (rank.second).
    Ván 3 người (yêu cầu mới): bét (hạng 3) → nhất rank.first và nhì → nhất rank.second; mặc định 200 / 100 là
    nhất +300, nhì −100, ba −200. Vẫn chỉ là các khoản chuyển nên tổng bằng 0.
    """
    out: list[Transfer] = []
    players = state.players
    count = len(players)
    first = _seat_with_rank(state, 1)
    second = _seat_with_rank(state, 2)
    last = _seat_with_rank(state, count)
    assert first is not None
    rank_points = rules.scoring.rank

    cong = [s for s in clockwise_from(first, count) if players[s].status == PlayerStatus.CONG]
    for seat in cong:  # D7, D11: người cóng trả cho người nhất, cộng thối heo + hàng
        _add(out, seat, first, rules.scoring.congValue, "CONG")
        _rot_transfers(state, rules, seat, first, out)  # D12: thối của người cóng → người nhất

    # Người xếp ngay trên bét (hạng 3 khi 4 người, hạng 2 khi 3 người) nhận thối của bét nếu hết bài thường.
    above_last = _seat_with_rank(state, count - 1)
    if last is not None and players[last].status != PlayerStatus.CONG:
        _add(out, last, first, rank_points.first, "RANK", rank=count)
        # D8, D12, G10: thối của người bét → người xếp ngay trên bét nếu người đó hết bài bình thường,
        # không thì → người nhất
        above_finished = above_last is not None and players[above_last].status == PlayerStatus.FINISHED
        receiver = above_last if above_finished and above_last is not None else first
        _rot_transfers(state, rules, last, receiver, out)
        trapped = rules.special.trappedThreeSpades
        if trapped.enabled and players[last].hand == [THREE_SPADES]:  # ảnh luật §3.3 (N6): đền làng
            for seat in range(count):
                _add(out, last, seat, trapped.perPlayer, "TRAPPED_THREE_SPADES")
    if second is not None and players[second].status != CONG_STATUS:
        if count == 3:
            _add(out, second, first, rank_points.second, "RANK", rank=2)  # nhì trả nhất
        elif above_last is not None and players[above_last].status != CONG_STATUS:
            _add(out, above_last, second, rank_points.second, "RANK", rank=3)  # ba trả nhì
    return out


def instant_win_transfers(
    winners: list[int], rules: RuleConfig, per_loser: int, reason: str, players: int = SEATS
) -> list[Transfer]:
    """Tới trắng / đút mù: mỗi người thua trả per_loser, chia đều cho người thắng (N2); phần dư trả hết cho
    người thắng gần người mở ván nhất (winners đã xếp theo thứ tự đi từ người mở ván)."""
    out: list[Transfer] = []
    losers = [s for s in range(players) if s not in winners]
    base, remainder = divmod(per_loser, len(winners))
    for loser in losers:
        for i, winner in enumerate(winners):
            _add(out, loser, winner, base + (remainder if i == 0 else 0), reason)
    return out

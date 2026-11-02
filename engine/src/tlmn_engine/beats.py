"""Bảng quyết định đè / chặt (docs/gd2/03 §3; ID 11, 24, 25, 29–48, D6, R8, Q-P1-8)."""

from dataclasses import dataclass
from enum import StrEnum

from tlmn_engine.cards import THREE_CLUBS, is_red
from tlmn_engine.combos import ChopCategory, Combo
from tlmn_engine.rules_config import RuleConfig


class BeatKind(StrEnum):
    LEAD = "LEAD"  # mở vòng
    BEAT = "BEAT"  # đè cùng loại
    CHOP = "CHOP"  # chặt khác loại


class MoveRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class BeatResult:
    kind: BeatKind
    scores_as_chop: bool = False  # có tính điểm chặt (chuỗi chặt chồng)
    target_value: int = 0


def chop_allowed(rules: RuleConfig, attacker: ChopCategory | None, target: ChopCategory | None) -> bool:
    """Ma trận chặt khác loại: attacker → target, mỗi ô ứng với một cờ trong luật."""
    c = rules.chop
    matrix = {
        (ChopCategory.PS3, ChopCategory.HEO_SINGLE): c.threePairSeq.vsSingleTwo,  # 29
        (ChopCategory.FK, ChopCategory.HEO_SINGLE): c.fourKind.vsSingleTwo,  # 31
        (ChopCategory.FK, ChopCategory.HEO_PAIR): c.fourKind.vsPairTwo,  # 32
        (ChopCategory.FK, ChopCategory.PS3): c.fourKind.vsThreePairSeq,  # 33
        (ChopCategory.PS4, ChopCategory.HEO_SINGLE): c.fourPairSeq.vsSingleTwo,  # 35
        (ChopCategory.PS4, ChopCategory.HEO_PAIR): c.fourPairSeq.vsPairTwo,  # 36
        (ChopCategory.PS4, ChopCategory.FK): c.fourPairSeq.vsFourKind,  # 37
        (ChopCategory.PS4, ChopCategory.PS3): c.fourPairSeq.vsThreePairSeq,  # 38
    }
    return attacker is not None and target is not None and matrix.get((attacker, target), False)


def target_value(rules: RuleConfig, target: Combo) -> int:
    """Điểm chặt tính theo bộ BỊ chặt (ID 117–122)."""
    s = rules.scoring
    cat = target.chop_category
    if cat in (ChopCategory.HEO_SINGLE, ChopCategory.HEO_PAIR):
        return sum(s.redTwoValue if is_red(c) else s.blackTwoValue for c in target.cards)
    if cat == ChopCategory.PS3:
        return s.chopTargetValue.threePairSeq
    if cat == ChopCategory.FK:
        return s.chopTargetValue.fourKind
    if cat == ChopCategory.PS4:
        return s.chopTargetValue.fourPairSeq
    return 0


def can_beat(
    rules: RuleConfig,
    top: Combo | None,
    play: Combo,
    *,
    must_include_three_clubs: bool,
    top_is_chop: bool,
    someone_finished: bool,
) -> BeatResult:
    """Không xét lượt — lượt kiểm tra ở reducer (can_interrupt cho 4 đôi thông)."""
    if top is None:
        if must_include_three_clubs and THREE_CLUBS not in play.cards:  # ID 8
            raise MoveRejected("MUST_INCLUDE_THREE_CLUBS", "Nước đầu tiên của ván phải có 3♣")
        return BeatResult(BeatKind.LEAD)

    target = top.chop_category
    if play.same_shape(top):
        if play.top <= top.top:
            raise MoveRejected("CANNOT_BEAT", "Bài chưa đủ lớn để chặn")
        scores = target in (ChopCategory.PS3, ChopCategory.FK, ChopCategory.PS4) or (
            target == ChopCategory.HEO_PAIR and rules.chop.pairTwoOverPairTwoScoresAsChop  # ID 44
        )
        result = BeatResult(BeatKind.BEAT, scores, target_value(rules, top) if scores else 0)
    elif chop_allowed(rules, play.chop_category, target):
        result = BeatResult(BeatKind.CHOP, True, target_value(rules, top))
    else:
        raise MoveRejected("CANNOT_BEAT", "Không được đè khác loại bài")  # ID 24

    if result.scores_as_chop and top_is_chop and not rules.chop.allowChain:  # ID 41
        raise MoveRejected("CHAIN_NOT_ALLOWED", "Luật hiện tại không cho chặt chồng")
    if result.scores_as_chop and someone_finished and not rules.chop.allowAfterFirstFinisher:  # ID 48
        raise MoveRejected("CHOP_NOT_ALLOWED", "Luật hiện tại không cho chặt sau khi đã có người về nhất")
    return result


def can_interrupt(rules: RuleConfig, play: Combo, result: BeatResult) -> bool:
    """ID 42, R8: chỉ 4 đôi thông được chặt ngoài lượt (kể cả đã bỏ lượt).

    3 đôi thông và tứ quý phải đúng lượt (ID 43, D6).
    """
    return (
        rules.chop.fourPairSeq.outOfTurn and play.chop_category == ChopCategory.PS4 and result.scores_as_chop
    )

"""RuleConfig GLOBAL do Admin quản lý (thiết kế: docs/gd2/02-ruleconfig.md).

Chỉ chứa giá trị boolean / enum / số nguyên có giới hạn / danh sách thứ tự — không có biểu thức hay script.
Tên field dùng camelCase vì đây chính là hợp đồng JSON lưu trong DB và gửi cho client.
Mỗi field mang `x-excel-ids` (Excel ID nguồn) và `x-label` (nhãn tiếng Việt) trong json_schema_extra.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal, get_args, get_origin

import annotated_types
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.fields import FieldInfo

from tlmn_engine import __version__ as ENGINE_VERSION

SCHEMA_VERSION = 1

InstantWinKind = Literal["FOUR_TWOS", "DRAGON", "SIX_PAIRS"]

OPTION_LABELS: dict[str, str] = {
    "LOSE_TURN": "Mất lượt (người đang mở vòng: server tự đánh lá đơn nhỏ nhất)",
    "CUMULATIVE": "Cộng dồn — người bị chặt cuối cùng trả toàn bộ chuỗi",
    "SPLIT_EQUALLY": "Chia đều tiền cho những người tới trắng cùng loại",
    "FIRST_IN_TURN_ORDER": "Ai đi trước (gần người mở ván nhất) thì thắng",
    "FOUR_TWOS": "Tứ quý 2 (4 heo)",
    "DRAGON": "Sảnh rồng (3 → A)",
    "SIX_PAIRS": "6 đôi",
}

GROUP_LABELS: dict[str, str] = {
    "turn": "Lượt chơi",
    "opening": "Mở ván",
    "chop": "Chặt hàng",
    "instantWin": "Tới trắng",
    "redeal": "Chia lại",
    "penalty": "Phạt (cóng, thối)",
    "special": "Thưởng / phạt đặc biệt",
    "scoring": "Điểm số",
    "room": "Phòng online",
}


def _meta(excel_ids: list[int], label: str) -> dict[str, Any]:
    ids: list[Any] = list(excel_ids)
    return {"x-excel-ids": ids, "x-label": label}


def _f(default: Any, excel_ids: list[int], label: str, **constraints: Any) -> Any:
    return Field(default, json_schema_extra=_meta(excel_ids, label), **constraints)


def _sub(model: type[BaseModel], excel_ids: list[int], label: str) -> Any:
    return Field(default_factory=model, json_schema_extra=_meta(excel_ids, label))


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


Points = int  # điểm luôn là số nguyên


class TurnConfig(_Model):
    timeLimitSeconds: int = _f(30, [141, 10, 13], "Thời gian mỗi lượt (giây)", ge=10, le=120)
    timeoutAction: Literal["LOSE_TURN"] = _f("LOSE_TURN", [142, 88], "Khi hết giờ")


class OpeningConfig(_Model):
    mustIncludeThreeClubs: bool = _f(True, [8], "Nước đầu ván mở bằng 3♣ phải chứa 3♣")


class ThreePairSeqChop(_Model):
    vsSingleTwo: bool = _f(True, [29], "3 đôi thông chặt 1 heo")


class FourKindChop(_Model):
    vsSingleTwo: bool = _f(True, [31], "Tứ quý chặt 1 heo")
    vsPairTwo: bool = _f(True, [32], "Tứ quý chặt đôi heo")
    vsThreePairSeq: bool = _f(True, [33], "Tứ quý chặt 3 đôi thông")


class FourPairSeqChop(_Model):
    vsSingleTwo: bool = _f(True, [35], "4 đôi thông chặt 1 heo")
    vsPairTwo: bool = _f(True, [36], "4 đôi thông chặt đôi heo")
    vsFourKind: bool = _f(True, [37], "4 đôi thông chặt tứ quý")
    vsThreePairSeq: bool = _f(True, [38], "4 đôi thông chặt 3 đôi thông")
    outOfTurn: bool = _f(True, [42], "4 đôi thông được chặt ngoài lượt")


class ChopConfig(_Model):
    threePairSeq: ThreePairSeqChop = _sub(ThreePairSeqChop, [29], "3 đôi thông")
    fourKind: FourKindChop = _sub(FourKindChop, [31, 32, 33], "Tứ quý")
    fourPairSeq: FourPairSeqChop = _sub(FourPairSeqChop, [35, 36, 37, 38, 42], "4 đôi thông")
    allowChain: bool = _f(True, [41], "Cho phép chặt chồng")
    pairTwoOverPairTwoScoresAsChop: bool = _f(True, [44], "Đôi 2 lớn đè đôi 2 nhỏ tính tiền như chặt đôi heo")
    allowAfterFirstFinisher: bool = _f(True, [48], "Cho phép chặt sau khi đã có người về nhất")
    chainSettlement: Literal["CUMULATIVE"] = _f("CUMULATIVE", [83], "Cách tính chặt chồng")


class InstantWinConfig(_Model):
    fourTwos: bool = _f(True, [49], "Tới trắng: tứ quý 2")
    sixPairs: bool = _f(True, [52], "Tới trắng: 6 đôi")
    dragonStraight: bool = _f(True, [53], "Tới trắng: sảnh rồng 3 → A")
    priorityOrder: list[InstantWinKind] = _f(
        ["FOUR_TWOS", "DRAGON", "SIX_PAIRS"], [62, 64], "Thứ tự ưu tiên khi nhiều người tới trắng"
    )
    tieBreak: Literal["SPLIT_EQUALLY", "FIRST_IN_TURN_ORDER"] = _f(
        "SPLIT_EQUALLY", [63], "Nhiều người tới trắng cùng loại"
    )
    checkDuringPlay: bool = _f(False, [67], "Xét tới trắng cả trong lúc đang chơi")


class RedealConfig(_Model):
    fourThrees: bool = _f(True, [58], "Chia lại khi có tứ quý 3 (ván mở bằng 3♣)")
    pairSeqWithThreeClubs: bool = _f(True, [59], "Chia lại khi có 3/4 đôi thông chứa 3♣ (ván mở bằng 3♣)")


class CongConfig(_Model):
    enabled: bool = _f(True, [68, 70, 71], "Áp dụng luật cóng (bị nhốt)")
    allTable: bool = _f(True, [69], "Hiển thị nhãn cóng toàn bàn")


class RotConfig(_Model):
    blackTwo: bool = _f(True, [72, 74], "Thối heo đen")
    redTwo: bool = _f(True, [73, 74], "Thối heo đỏ")
    fourKind: bool = _f(True, [75], "Thối tứ quý")
    threePairSeq: bool = _f(True, [76], "Thối 3 đôi thông")
    fourPairSeq: bool = _f(True, [77], "Thối 4 đôi thông")


class PenaltyConfig(_Model):
    cong: CongConfig = _sub(CongConfig, [68, 69], "Cóng")
    rot: RotConfig = _sub(RotConfig, [72, 73, 74, 75, 76, 77], "Thối")


class TrappedThreeSpadesConfig(_Model):
    enabled: bool = _f(True, [], "Áp dụng luật bị nhốt 3♠ (ảnh luật §3.3)")
    perPlayer: Points = _f(200, [], "Bị nhốt 3♠: trả mỗi người còn lại", ge=0, le=10_000)


class SpecialConfig(_Model):
    blindThreeSpades: bool = _f(True, [89, 90], "Đút mù: về nhất bằng 3♠ đánh đơn")
    trappedThreeSpades: TrappedThreeSpadesConfig = _sub(TrappedThreeSpadesConfig, [], "Bị nhốt 3♠")


class RankPoints(_Model):
    first: Points = _f(200, [112], "Điểm về nhất", ge=0, le=10_000)
    second: Points = _f(100, [113], "Điểm về nhì", ge=0, le=10_000)
    third: Points = _f(-100, [114], "Điểm về ba", ge=-10_000, le=0)
    last: Points = _f(-200, [115], "Điểm về bét", ge=-10_000, le=0)


class ChopTargetValue(_Model):
    threePairSeq: Points = _f(200, [120, 122], "Bị chặt 3 đôi thông", ge=0, le=10_000)
    fourKind: Points = _f(400, [119, 122], "Bị chặt tứ quý", ge=0, le=10_000)
    fourPairSeq: Points = _f(400, [121, 122], "Bị chặt 4 đôi thông", ge=0, le=10_000)


class RotComboValue(_Model):
    fourKind: Points = _f(200, [75], "Thối tứ quý", ge=0, le=10_000)
    threePairSeq: Points = _f(200, [76], "Thối 3 đôi thông", ge=0, le=10_000)
    fourPairSeq: Points = _f(200, [77], "Thối 4 đôi thông", ge=0, le=10_000)


class ScoringConfig(_Model):
    rank: RankPoints = _sub(RankPoints, [80, 112, 113, 114, 115], "Điểm theo thứ hạng")
    blackTwoValue: Points = _f(100, [117], "Giá trị heo đen (2♠, 2♣)", ge=0, le=10_000)
    redTwoValue: Points = _f(200, [118], "Giá trị heo đỏ (2♦, 2♥)", ge=0, le=10_000)
    chopTargetValue: ChopTargetValue = _sub(ChopTargetValue, [119, 120, 121, 122], "Điểm chặt hàng")
    rotComboValue: RotComboValue = _sub(RotComboValue, [75, 76, 77], "Điểm thối hàng")
    congValue: Points = _f(200, [123, 70, 71], "Điểm cóng (trả cho người về nhất)", ge=0, le=10_000)
    instantWinPerLoser: Points = _f(200, [124, 65], "Tới trắng: mỗi người thua trả", ge=0, le=10_000)
    blindThreeSpadesPerLoser: Points = _f(200, [125, 90], "Đút mù: mỗi người thua trả", ge=0, le=10_000)


class RoomConfig(_Model):
    seatHoldSeconds: int = _f(120, [144], "Giữ ghế khi mất kết nối (giây)", ge=30, le=600)


class RuleConfig(_Model):
    turn: TurnConfig = Field(default_factory=TurnConfig)
    opening: OpeningConfig = Field(default_factory=OpeningConfig)
    chop: ChopConfig = Field(default_factory=ChopConfig)
    instantWin: InstantWinConfig = Field(default_factory=InstantWinConfig)
    redeal: RedealConfig = Field(default_factory=RedealConfig)
    penalty: PenaltyConfig = Field(default_factory=PenaltyConfig)
    special: SpecialConfig = Field(default_factory=SpecialConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    room: RoomConfig = Field(default_factory=RoomConfig)


# Luật cố định (fixedInvariant) — chỉ xem, không chỉnh; được chép vào snapshot mỗi ván.
INVARIANTS: dict[str, Any] = {
    "deckSize": 52,
    "playerCount": 4,
    "cardsPerPlayer": 13,
    "turnDirection": "CLOCKWISE",
    "rankOrder": ["3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2"],
    "suitOrder": ["SPADES", "CLUBS", "DIAMONDS", "HEARTS"],
    "openingCard": "3C",
    "straightAllowsTwo": False,
    "passLocksUntilNewTrick": True,
    "leadAfterFinisher": "CATCH_CONTINUES_ELSE_NEXT_CLOCKWISE",
    "threePairSeqAndFourKindRequireTurn": True,
    "instantWinEndsImmediately": True,
    "instantWinOthersRank": "ALL_FOURTH",
    "openingAfterInstantWin": "THREE_CLUBS",
    "rotAppliesToCong": True,
    "rotCheckTiming": "AT_GAME_END_LAST_PLACE",
    "endMode": "LAST_ONE_REMAINING",
    "allowNegativeScore": True,
    "zeroSum": True,
    "sessionScoreLimit": None,
    "sessionInitialScore": 0,
    "allowTwoAsLastCard": True,
    "allowChopWhenTargetHasOneCard": True,
    "rulesSnapshotPerGame": True,
}


# ---------------------------------------------------------------------------
# Metadata field cho UI Admin
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FieldSpec:
    path: str
    group: str
    label: str
    kind: Literal["bool", "int", "enum", "order"]
    excel_ids: tuple[int, ...]
    minimum: int | None = None
    maximum: int | None = None
    options: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "group": self.group,
            "groupLabel": GROUP_LABELS[self.group],
            "label": self.label,
            "kind": self.kind,
            "excelIds": list(self.excel_ids),
            "min": self.minimum,
            "max": self.maximum,
            "options": [{"value": o, "label": OPTION_LABELS.get(o, o)} for o in self.options],
        }


def _extra(info: FieldInfo) -> dict[str, Any]:
    extra = info.json_schema_extra
    return extra if isinstance(extra, dict) else {}


def _walk(model: type[BaseModel], prefix: str, group: str) -> Iterator[FieldSpec]:
    for name, info in model.model_fields.items():
        path = f"{prefix}{name}"
        annotation = info.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            yield from _walk(annotation, f"{path}.", group or name)
            continue
        extra = _extra(info)
        excel_ids = tuple(int(i) for i in extra.get("x-excel-ids", []))
        label = str(extra.get("x-label", name))
        if annotation is bool:
            yield FieldSpec(path, group, label, "bool", excel_ids)
        elif annotation is int:
            lo = next((m.ge for m in info.metadata if isinstance(m, annotated_types.Ge)), None)
            hi = next((m.le for m in info.metadata if isinstance(m, annotated_types.Le)), None)
            yield FieldSpec(path, group, label, "int", excel_ids, _as_int(lo), _as_int(hi))
        elif get_origin(annotation) is Literal:
            yield FieldSpec(path, group, label, "enum", excel_ids, options=tuple(get_args(annotation)))
        elif get_origin(annotation) is list:
            (item,) = get_args(annotation)
            yield FieldSpec(path, group, label, "order", excel_ids, options=tuple(get_args(item)))
        else:  # pragma: no cover - bảo vệ khi thêm kiểu mới mà quên hỗ trợ
            raise TypeError(f"Kiểu field chưa hỗ trợ: {path}: {annotation}")


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def field_specs() -> tuple[FieldSpec, ...]:
    return tuple(_walk(RuleConfig, "", ""))


def _excel_ids_by_path() -> dict[str, tuple[int, ...]]:
    return {spec.path: spec.excel_ids for spec in field_specs()}


# ---------------------------------------------------------------------------
# Validation V1–V11
# ---------------------------------------------------------------------------

Level = Literal["error", "warning", "info"]


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    level: Level
    path: str
    excel_ids: tuple[int, ...]
    message: str

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "level": self.level,
            "path": self.path,
            "excelIds": list(self.excel_ids),
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[Issue, ...]
    config: RuleConfig | None

    @property
    def errors(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.level == "error")

    @property
    def warnings(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.level == "warning")

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [i.to_json() for i in self.errors],
            "warnings": [i.to_json() for i in self.warnings],
            "infos": [i.to_json() for i in self.issues if i.level == "info"],
            "configHash": config_hash(self.config) if self.config is not None else None,
        }


def parse_rule_config(data: Mapping[str, Any]) -> RuleConfig:
    """Parse cấu trúc/kiểu (V10). Ném pydantic.ValidationError nếu sai."""
    return RuleConfig.model_validate(dict(data))


def _structural_issues(exc: ValidationError) -> list[Issue]:
    ids = _excel_ids_by_path()
    issues = []
    for err in exc.errors():
        path = ".".join(str(p) for p in err["loc"])
        issues.append(Issue("V10", "error", path, ids.get(path, ()), f"{path}: {err['msg']}"))
    return issues


def _semantic_issues(c: RuleConfig) -> list[Issue]:
    ids = _excel_ids_by_path()
    out: list[Issue] = []

    def add(code: str, level: Level, path: str, message: str, extra_ids: tuple[int, ...] = ()) -> None:
        out.append(Issue(code, level, path, tuple(dict.fromkeys(ids.get(path, ()) + extra_ids)), message))

    rank = c.scoring.rank
    if rank.first != -rank.last or rank.second != -rank.third:
        add(
            "V1",
            "error",
            "scoring.rank",
            "Điểm hạng phải đối xứng: nhất = −bét và nhì = −ba (để tổng điểm luôn bằng 0 khi có cóng).",
            (112, 113, 114, 115, 133),
        )
    if not rank.first > rank.second:
        add("V2", "error", "scoring.rank.first", "Điểm về nhất phải lớn hơn điểm về nhì.", (113,))

    order = c.instantWin.priorityOrder
    if sorted(order) != sorted(get_args(InstantWinKind)):
        add(
            "V3",
            "error",
            "instantWin.priorityOrder",
            "Thứ tự ưu tiên tới trắng phải gồm đúng 3 loại, không trùng.",
        )
    enabled = {"FOUR_TWOS": c.instantWin.fourTwos, "SIX_PAIRS": c.instantWin.sixPairs}
    enabled["DRAGON"] = c.instantWin.dragonStraight
    for kind in order:
        if not enabled.get(kind, True):
            add(
                "V4",
                "warning",
                "instantWin.priorityOrder",
                f"Loại tới trắng '{OPTION_LABELS[kind]}' đang tắt nên sẽ bị bỏ qua khi xét ưu tiên.",
            )

    if not c.chop.allowChain:
        add(
            "V5",
            "warning",
            "chop.allowChain",
            "Đã tắt chặt chồng: các luật hàng đè hàng (30, 33, 34, 37–39) chỉ áp dụng khi bài trên bàn "
            "không phải là một nước chặt.",
            (30, 33, 34, 37, 38, 39),
        )
    if c.penalty.cong.allTable and not c.penalty.cong.enabled:
        add("V6", "error", "penalty.cong.allTable", "Cóng toàn bàn yêu cầu bật luật cóng.", (68,))
    chop_value = c.scoring.chopTargetValue
    if chop_value.fourKind < chop_value.threePairSeq:
        add(
            "V7",
            "warning",
            "scoring.chopTargetValue.fourKind",
            "Điểm bị chặt tứ quý đang nhỏ hơn điểm bị chặt 3 đôi thông.",
        )
    rot = c.penalty.rot
    combo = c.scoring.rotComboValue
    if not (rot.fourKind or rot.threePairSeq or rot.fourPairSeq) and (
        combo.fourKind or combo.threePairSeq or combo.fourPairSeq
    ):
        add(
            "V8", "info", "scoring.rotComboValue", "Mọi luật thối hàng đang tắt nên điểm thối hàng không dùng"
        )
    if c.room.seatHoldSeconds < 2 * c.turn.timeLimitSeconds:
        add(
            "V9",
            "warning",
            "room.seatHoldSeconds",
            "Thời gian giữ ghế nên ít nhất gấp đôi thời gian một lượt.",
            (141,),
        )
    if c.instantWin.checkDuringPlay:
        add(
            "V11",
            "error",
            "instantWin.checkDuringPlay",
            "Chưa hỗ trợ xét tới trắng trong lúc đang chơi; tới trắng chỉ xét ngay sau khi chia bài.",
        )
    return out


def validate_rule_config(data: Mapping[str, Any]) -> ValidationReport:
    try:
        config = parse_rule_config(data)
    except ValidationError as exc:
        return ValidationReport(tuple(_structural_issues(exc)), None)
    return ValidationReport(tuple(_semantic_issues(config)), config)


# ---------------------------------------------------------------------------
# Hash, diff, snapshot
# ---------------------------------------------------------------------------


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def config_hash(config: RuleConfig) -> str:
    return sha256_hex(config.model_dump(mode="json"))


def default_config() -> RuleConfig:
    return RuleConfig()


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out.update(_flatten(item, f"{prefix}{key}."))
        return out
    return {prefix.rstrip("."): value}


@dataclass(frozen=True, slots=True)
class Change:
    path: str
    before: Any
    after: Any
    excel_ids: tuple[int, ...]
    label: str

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "label": self.label,
            "before": self.before,
            "after": self.after,
            "excelIds": list(self.excel_ids),
        }


def diff_configs(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[Change]:
    """So sánh hai config (dạng JSON) theo từng field lá; trả về theo thứ tự field trong schema."""
    specs = {s.path: s for s in field_specs()}
    a, b = _flatten(before), _flatten(after)
    ordered = [p for p in specs if p in a or p in b] + sorted((set(a) | set(b)) - set(specs))
    changes = []
    for path in ordered:
        if a.get(path) != b.get(path):
            spec = specs.get(path)
            changes.append(
                Change(
                    path,
                    a.get(path),
                    b.get(path),
                    spec.excel_ids if spec else (),
                    spec.label if spec else path,
                )
            )
    return changes


def build_rules_snapshot(config: RuleConfig, rule_version: int) -> dict[str, Any]:
    """Snapshot bất biến chép vào mỗi ván (ID 136, 156): gồm cả config và invariants."""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "engineVersion": ENGINE_VERSION,
        "ruleVersion": rule_version,
        "config": config.model_dump(mode="json"),
        "invariants": INVARIANTS,
    }

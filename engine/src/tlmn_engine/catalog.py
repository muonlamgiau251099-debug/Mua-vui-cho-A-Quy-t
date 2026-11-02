"""Truy cập rule catalog sinh từ file Excel (tools/gen_rule_catalog.py)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources


@dataclass(frozen=True, slots=True)
class RuleEntry:
    excel_id: int | None
    group: str
    name: str
    description: str | None
    excel_value: str | None
    rule_key: str
    rule_class: str
    default: str
    status: str


@cache
def raw_catalog() -> dict[str, object]:
    """Nội dung catalog.json (dùng cho API xem luật). Không sửa đối tượng trả về."""
    text = resources.files("tlmn_engine").joinpath("catalog.json").read_text(encoding="utf-8")
    data: dict[str, object] = json.loads(text)
    return data


def _entry(item: dict[str, object]) -> RuleEntry:
    def opt(key: str) -> str | None:
        value = item.get(key)
        return None if value is None else str(value)

    excel_id = item.get("excelId")
    return RuleEntry(
        excel_id=excel_id if isinstance(excel_id, int) else None,
        group=str(item["group"]),
        name=str(item["name"]),
        description=opt("description"),
        excel_value=opt("excelValue"),
        rule_key=str(item["ruleKey"]),
        rule_class=str(item["class"]),
        default=str(item["default"]),
        status=str(item["status"]),
    )


@cache
def excel_rules() -> tuple[RuleEntry, ...]:
    """Các luật có Excel ID, theo thứ tự hàng trong file Excel."""
    rules = raw_catalog()["rules"]
    assert isinstance(rules, list)
    return tuple(_entry(r) for r in rules)


@cache
def extension_rules() -> tuple[RuleEntry, ...]:
    """Các luật bổ sung ngoài Excel (excel_id = None)."""
    extensions = raw_catalog()["extensions"]
    assert isinstance(extensions, list)
    return tuple(_entry(r) for r in extensions)


def excel_ids() -> frozenset[int]:
    return frozenset(r.excel_id for r in excel_rules() if r.excel_id is not None)

"""Sinh rule catalog từ file Excel luật + mapping đã duyệt.

Đầu ra:
- engine/src/tlmn_engine/catalog.json  (dùng cho tooltip, trang xem luật, trace test)
- docs/gd1/A-rule-inventory.md          (Phụ lục A, khi có --appendix)

Usage: uv run python tools/gen_rule_catalog.py [--appendix] [--check]
  --check: không ghi file, chỉ báo lỗi nếu file hiện tại khác kết quả sinh ra.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
EXCEL = ROOT / "Cau_hinh_luat_Tien_Len_Mien_Nam.xlsx"
SHEET = "Cấu hình luật"
HEADER_ROW = 4
MAPPING = ROOT / "tools" / "rule_mapping.json"
EXTENSIONS = ROOT / "tools" / "rule_extensions.json"
CATALOG = ROOT / "engine" / "src" / "tlmn_engine" / "catalog.json"
APPENDIX = ROOT / "docs" / "gd1" / "A-rule-inventory.md"
EXPECTED_HEADER = ["ID", "Nhóm", "Tên luật", "Mô tả / điều kiện", "Giá trị / tham số", "Ghi chú Admin"]
CLASS_SHORT = {
    "fixedInvariant": "FIX",
    "adminConfigurable": "ADM",
    "derivedRule": "DER",
    "operationalPolicy": "OPS",
}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def read_excel(path: Path = EXCEL) -> list[dict[str, Any]]:
    """Đọc mọi hàng có ID ở cột A; giữ nguyên văn cột B-F."""
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)[SHEET]
    rows = list(ws.iter_rows(values_only=True))
    header = [_text(v) for v in rows[HEADER_ROW - 1][:6]]
    if header != EXPECTED_HEADER:
        raise ValueError(f"Header Excel không đúng định dạng: {header}")
    out: list[dict[str, Any]] = []
    for row_no, values in enumerate(rows[HEADER_ROW:], start=HEADER_ROW + 1):
        cells = list(values[:6]) + [None] * (6 - len(values[:6]))
        if cells[0] is None:
            continue
        if not isinstance(cells[0], int):
            raise ValueError(f"ID ở hàng {row_no} không phải số nguyên: {cells[0]!r}")
        out.append(
            {
                "excelId": cells[0],
                "row": row_no,
                "group": _text(cells[1]),
                "name": _text(cells[2]),
                "description": _text(cells[3]),
                "excelValue": _text(cells[4]),
                "adminNote": _text(cells[5]),
            }
        )
    ids: list[int] = [r["excelId"] for r in out]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"Excel có ID trùng: {dupes}")
    return out


def build_catalog(
    excel_rows: list[dict[str, Any]], mapping: dict[str, dict[str, str]], extensions: list[dict[str, Any]]
) -> dict[str, Any]:
    excel_ids = {r["excelId"] for r in excel_rows}
    mapped_ids = {int(k) for k in mapping}
    if excel_ids != mapped_ids:
        raise ValueError(
            f"Mapping lệch với Excel. Thiếu mapping: {sorted(excel_ids - mapped_ids)}; "
            f"mapping thừa: {sorted(mapped_ids - excel_ids)}"
        )
    rules = [{**r, **mapping[str(r["excelId"])]} for r in excel_rows]
    return {
        "source": EXCEL.name,
        "ruleCount": len(rules),
        "missingIds": [i for i in range(1, max(excel_ids) + 1) if i not in excel_ids],
        "rules": rules,
        "extensions": extensions,
    }


def _md(value: Any) -> str:
    return "" if value is None else str(value).replace("\n", " / ").replace("|", "\\|").strip()


def render_appendix(catalog: dict[str, Any]) -> str:
    lines = [
        "# Phụ lục A — Inventory rule ID (sinh từ Excel)",
        "",
        "Cột *Excel D/E* chép nguyên văn file. Các cột còn lại là mapping đã duyệt qua GĐ1–GĐ2.",
        "Phân loại: FIX=fixedInvariant, ADM=adminConfigurable, DER=derivedRule, OPS=operationalPolicy.",
        "File này được sinh bởi `tools/gen_rule_catalog.py --appendix`; không sửa tay.",
        "",
        "| ID | Hàng | Nhóm | Tên | Excel D | Excel E | ruleKey | Loại | Kiểu | Default | Nguồn default "
        "| Trạng thái | Phụ thuộc/xung đột | Runtime/Test |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in catalog["rules"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(r["excelId"]),
                    str(r["row"]),
                    _md(r["group"]),
                    _md(r["name"]),
                    _md(r["description"]),
                    _md(r["excelValue"]),
                    f"`{r['ruleKey']}`",
                    CLASS_SHORT[r["class"]],
                    _md(r["type"]),
                    _md(r["default"]),
                    _md(r["defaultSource"]),
                    _md(r["status"]),
                    _md(r["dependencies"]),
                    _md(r["notes"]),
                ]
            )
            + " |"
        )
    count = Counter(r["class"] for r in catalog["rules"])
    lines += [
        "",
        "**Thống kê phân loại:** "
        + ", ".join(f"{k}: {v}" for k, v in sorted(count.items()))
        + f" — tổng {catalog['ruleCount']}.",
        "",
        "## Luật bổ sung ngoài Excel (không có Excel ID)",
        "",
        "| Nguồn | Tên | ruleKey | Loại | Default | Mô tả |",
        "|---|---|---|---|---|---|",
    ]
    for e in catalog["extensions"]:
        lines.append(
            f"| {_md(e['source'])} | {_md(e['name'])} | `{e['ruleKey']}` | "
            f"{CLASS_SHORT[e['class']]} | {_md(e['default'])} | {_md(e['description'])} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--appendix", action="store_true", help="ghi thêm Phụ lục A")
    parser.add_argument("--check", action="store_true", help="chỉ kiểm tra file hiện tại có đúng không")
    args = parser.parse_args(argv)

    catalog = build_catalog(
        read_excel(),
        json.loads(MAPPING.read_text(encoding="utf-8")),
        json.loads(EXTENSIONS.read_text(encoding="utf-8")),
    )
    outputs = {CATALOG: json.dumps(catalog, ensure_ascii=False, indent=1) + "\n"}
    if args.appendix:
        outputs[APPENDIX] = render_appendix(catalog)

    stale = []
    for path, content in outputs.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == content:
            continue
        if args.check:
            stale.append(path.relative_to(ROOT).as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
            print(f"Đã ghi {path.relative_to(ROOT).as_posix()}")
    if stale:
        print("File chưa cập nhật theo Excel/mapping: " + ", ".join(stale), file=sys.stderr)
        return 1
    print(f"OK: {catalog['ruleCount']} rule ID, {len(catalog['extensions'])} luật bổ sung.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

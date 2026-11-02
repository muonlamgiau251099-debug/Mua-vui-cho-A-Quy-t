"""Kiểm tra mỗi Excel rule ID có ít nhất một test đánh dấu `@pytest.mark.rule(<id>, ...)`.

Usage: uv run python tools/check_rule_trace.py [--strict]
  Mặc định chỉ báo cáo. --strict: trả mã lỗi 1 nếu có ID chưa có test mà cũng không nằm trong
  tools/rule_trace_pending.json (ID thuộc slice sau), hoặc ID trong danh sách chờ đã có test
  (cần xóa khỏi danh sách).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "engine" / "src" / "tlmn_engine" / "catalog.json"
TEST_DIRS = [ROOT / "engine" / "tests", ROOT / "backend" / "tests"]
PENDING = ROOT / "tools" / "rule_trace_pending.json"
MARKER = re.compile(r"pytest\.mark\.rule\(([^)]*)\)")


def traced_ids() -> dict[int, list[str]]:
    found: dict[int, list[str]] = {}
    for test_dir in TEST_DIRS:
        for path in sorted(test_dir.rglob("test_*.py")):
            for match in MARKER.finditer(path.read_text(encoding="utf-8")):
                for token in match.group(1).split(","):
                    token = token.strip()
                    if token.isdigit():
                        found.setdefault(int(token), []).append(path.relative_to(ROOT).as_posix())
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    catalog_ids = {r["excelId"] for r in json.loads(CATALOG.read_text(encoding="utf-8"))["rules"]}
    found = traced_ids()
    pending = {int(k): v for k, v in json.loads(PENDING.read_text(encoding="utf-8")).items() if k.isdigit()}
    unknown = sorted(set(found) - catalog_ids)
    missing = sorted(catalog_ids - set(found))
    unplanned = [i for i in missing if i not in pending]
    stale = sorted(set(pending) & set(found))
    print(f"Rule trace: {len(catalog_ids) - len(missing)}/{len(catalog_ids)} Excel ID đã có test.")
    for i in missing:
        print(
            f"  chờ #{i}: {pending[i]}"
            if i in pending
            else f"  THIẾU TEST #{i} (không có trong danh sách chờ)"
        )
    if unknown:
        print(f"Marker tham chiếu ID không có trong Excel: {unknown}")
    if stale:
        print(f"ID đã có test nhưng vẫn nằm trong danh sách chờ (hãy xóa): {stale}")
    return 1 if args.strict and (unplanned or unknown or stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())

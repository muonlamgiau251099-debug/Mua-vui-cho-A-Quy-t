import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gen_rule_catalog as gen


def test_excel_is_read_with_130_unique_ids() -> None:
    rows = gen.read_excel()
    ids = [r["excelId"] for r in rows]
    assert len(ids) == 130
    assert len(set(ids)) == 130
    assert all(r["adminNote"] is None for r in rows)  # cột F trống toàn bộ


def test_excel_row_60_is_the_new_rule_added_on_review() -> None:
    row = next(r for r in gen.read_excel() if r["excelId"] == 60)
    assert row["description"] == "Sau khi tới trắng thì ván tiếp theo 3 chuồn đánh trước"


def test_mapping_mismatch_is_rejected() -> None:
    rows = gen.read_excel()
    mapping = json.loads(gen.MAPPING.read_text(encoding="utf-8"))
    del mapping["60"]
    with pytest.raises(ValueError, match="Thiếu mapping: \\[60\\]"):
        gen.build_catalog(rows, mapping, [])


def test_committed_catalog_and_appendix_are_up_to_date() -> None:
    assert gen.main(["--appendix", "--check"]) == 0

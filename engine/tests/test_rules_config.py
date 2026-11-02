import copy
from typing import Any

import pytest

from tlmn_engine.rules_config import (
    INVARIANTS,
    build_rules_snapshot,
    config_hash,
    default_config,
    diff_configs,
    field_specs,
    validate_rule_config,
)


def default_json() -> dict[str, Any]:
    return default_config().model_dump(mode="json")


def codes(data: dict[str, Any], level: str = "error") -> set[str]:
    return {i.code for i in validate_rule_config(data).issues if i.level == level}


def set_path(data: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    out = copy.deepcopy(data)
    node = out
    *parents, leaf = path.split(".")
    for key in parents:
        node = node[key]
    node[leaf] = value
    return out


def test_default_config_matches_approved_values() -> None:
    c = default_config()
    assert c.turn.timeLimitSeconds == 30  # ID 141
    assert c.room.seatHoldSeconds == 120  # ID 144
    assert (c.scoring.rank.first, c.scoring.rank.second, c.scoring.rank.third, c.scoring.rank.last) == (
        200,
        100,
        -100,
        -200,
    )  # ID 112–115
    assert (c.scoring.blackTwoValue, c.scoring.redTwoValue, c.scoring.congValue) == (100, 200, 200)
    assert c.instantWin.priorityOrder == ["FOUR_TWOS", "DRAGON", "SIX_PAIRS"]  # ảnh luật §6 (N1)
    assert c.instantWin.tieBreak == "SPLIT_EQUALLY"  # ảnh luật §6 (N2)
    assert c.chop.chainSettlement == "CUMULATIVE"  # D3
    assert c.special.trappedThreeSpades.perPlayer == 200  # ảnh luật §3.3 (N6)


def test_default_config_is_valid_without_warnings() -> None:
    report = validate_rule_config(default_json())
    assert report.ok
    assert report.issues == ()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("turn.timeLimitSeconds", 5),
        ("turn.timeLimitSeconds", 121),
        ("turn.timeLimitSeconds", "30"),
        ("chop.allowChain", "yes"),
        ("scoring.rank.third", 50),
        ("instantWin.tieBreak", "RANDOM"),
        ("instantWin.priorityOrder", ["FOUR_TWOS", "TEN_PAIRS", "SIX_PAIRS"]),
    ],
)
def test_wrong_type_or_out_of_range_is_rejected_as_v10(path: str, value: Any) -> None:
    report = validate_rule_config(set_path(default_json(), path, value))
    assert not report.ok
    assert {i.code for i in report.errors} == {"V10"}
    assert report.errors[0].path.startswith(path)


def test_unknown_field_is_rejected_no_scripts_allowed() -> None:
    data = default_json()
    data["turn"]["onTimeout"] = "lambda: exec('rm -rf /')"
    assert codes(data) == {"V10"}


def test_v1_rank_points_must_be_symmetric() -> None:
    data = set_path(default_json(), "scoring.rank.first", 300)
    report = validate_rule_config(data)
    assert {i.code for i in report.errors} == {"V1"}
    assert 133 in report.errors[0].excel_ids


def test_v2_first_must_be_greater_than_second() -> None:
    data = set_path(set_path(default_json(), "scoring.rank.second", 200), "scoring.rank.third", -200)
    assert "V2" in codes(data)


def test_v3_priority_order_must_not_repeat() -> None:
    data = set_path(default_json(), "instantWin.priorityOrder", ["FOUR_TWOS", "FOUR_TWOS", "SIX_PAIRS"])
    assert codes(data) == {"V3"}


def test_v4_disabled_instant_win_kind_in_priority_is_warning() -> None:
    data = set_path(default_json(), "instantWin.dragonStraight", False)
    assert validate_rule_config(data).ok
    assert codes(data, "warning") == {"V4"}


def test_v5_disabling_chain_warns_about_hang_over_hang_rules() -> None:
    data = set_path(default_json(), "chop.allowChain", False)
    warning = validate_rule_config(data).warnings[0]
    assert warning.code == "V5"
    assert {30, 33, 34, 37, 38, 39} <= set(warning.excel_ids)


def test_v6_cong_all_table_requires_cong() -> None:
    data = set_path(default_json(), "penalty.cong.enabled", False)
    assert codes(data) == {"V6"}


def test_v7_four_kind_chop_value_lower_than_three_pair_seq_is_warning() -> None:
    data = set_path(default_json(), "scoring.chopTargetValue.fourKind", 100)
    assert codes(data, "warning") == {"V7"}


def test_v8_all_rot_combo_disabled_is_info() -> None:
    data = default_json()
    for key in ("fourKind", "threePairSeq", "fourPairSeq"):
        data = set_path(data, f"penalty.rot.{key}", False)
    assert codes(data, "info") == {"V8"}


def test_v9_seat_hold_shorter_than_two_turns_is_warning() -> None:
    data = set_path(default_json(), "turn.timeLimitSeconds", 90)
    assert codes(data, "warning") == {"V9"}


def test_v11_instant_win_during_play_is_not_supported() -> None:
    data = set_path(default_json(), "instantWin.checkDuringPlay", True)
    assert codes(data) == {"V11"}


def test_config_hash_is_stable_and_changes_with_values() -> None:
    a = default_config()
    assert config_hash(a) == config_hash(default_config())
    changed = validate_rule_config(set_path(default_json(), "turn.timeLimitSeconds", 45)).config
    assert changed is not None
    assert config_hash(changed) != config_hash(a)


def test_diff_lists_changed_fields_with_excel_ids() -> None:
    after = set_path(default_json(), "turn.timeLimitSeconds", 45)
    after = set_path(after, "chop.fourPairSeq.outOfTurn", False)
    changes = diff_configs(default_json(), after)
    assert [(c.path, c.before, c.after) for c in changes] == [
        ("turn.timeLimitSeconds", 30, 45),
        ("chop.fourPairSeq.outOfTurn", True, False),
    ]
    assert changes[1].excel_ids == (42,)


def test_field_specs_cover_every_leaf_and_carry_ui_metadata() -> None:
    specs = {s.path: s for s in field_specs()}
    assert specs["turn.timeLimitSeconds"].kind == "int"
    assert (specs["turn.timeLimitSeconds"].minimum, specs["turn.timeLimitSeconds"].maximum) == (10, 120)
    assert specs["instantWin.priorityOrder"].kind == "order"
    assert specs["instantWin.tieBreak"].options == ("SPLIT_EQUALLY", "FIRST_IN_TURN_ORDER")
    assert specs["special.trappedThreeSpades.perPlayer"].excel_ids == ()
    # mọi field lá đều có trong specs
    assert set(specs) == {c.path for c in diff_configs({}, default_json())}


def test_snapshot_contains_config_and_invariants() -> None:
    snapshot = build_rules_snapshot(default_config(), rule_version=3)
    assert snapshot["ruleVersion"] == 3
    assert snapshot["invariants"] == INVARIANTS
    assert snapshot["invariants"]["openingCard"] == "3C"
    assert snapshot["config"] == default_json()

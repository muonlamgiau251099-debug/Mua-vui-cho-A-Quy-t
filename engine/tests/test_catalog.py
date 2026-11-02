from tlmn_engine.catalog import excel_ids, excel_rules, extension_rules

# 26 ID khuyết trong file Excel (bản lưu 2026-10-29 16:19) — không được tự tạo.
MISSING_IDS = {
    20,
    28,
    40,
    45,
    50,
    51,
    54,
    55,
    56,
    57,
    61,
    78,
    79,
    86,
    91,
    92,
    93,
    94,
    95,
    96,
    97,
    98,
    108,
    110,
    116,
    126,
}
CLASSES = {"fixedInvariant", "adminConfigurable", "derivedRule", "operationalPolicy"}


def test_catalog_has_exactly_the_130_excel_ids() -> None:
    assert len(excel_rules()) == 130
    assert excel_ids() == set(range(1, 157)) - MISSING_IDS


def test_every_rule_has_rule_key_and_known_class() -> None:
    for rule in excel_rules():
        assert rule.rule_key, rule.excel_id
        assert rule.rule_class in CLASSES, rule.excel_id


def test_rule_134_is_overridden_to_system_admin_only() -> None:
    rule = next(r for r in excel_rules() if r.excel_id == 134)
    assert rule.excel_value is None
    assert rule.default == "SYSTEM_ADMIN_ONLY"


def test_extension_rules_have_no_excel_id() -> None:
    keys = {r.rule_key: r for r in extension_rules()}
    assert keys["special.trappedThreeSpades"].excel_id is None

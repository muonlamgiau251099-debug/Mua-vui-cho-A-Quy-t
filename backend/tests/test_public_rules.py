import httpx
import pytest


async def test_catalog_lists_130_excel_rules_and_extension(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/rules/catalog")).json()
    assert body["ruleCount"] == 130
    assert len(body["rules"]) == 130
    assert body["extensions"][0]["ruleKey"] == "special.trappedThreeSpades"


async def test_schema_describes_every_editable_field(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/rules/schema")).json()
    fields = {f["path"]: f for f in body["fields"]}
    assert fields["turn.timeLimitSeconds"]["min"] == 10
    assert fields["instantWin.priorityOrder"]["kind"] == "order"
    assert {g["key"] for g in body["groups"]} >= {"turn", "chop", "scoring"}
    assert body["invariants"]["openingCard"] == "3C"


@pytest.mark.rule(138)
async def test_players_can_read_active_rules_without_login(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/rules/active")).json()
    assert body["version"] == 1
    assert len(body["configHash"]) == 64


async def test_unknown_version_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/rules/versions/99")
    assert (response.status_code, response.json()["code"]) == (404, "VERSION_NOT_FOUND")

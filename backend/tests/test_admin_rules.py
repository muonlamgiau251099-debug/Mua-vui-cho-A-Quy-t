import asyncio
import copy
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.models import RuleAuditLog
from tests.support import login, make_client


async def create_draft(c: httpx.AsyncClient) -> dict[str, Any]:
    response = await c.post("/api/admin/rules/draft", json={})
    assert response.status_code == 201, response.text
    return dict(response.json())


async def save_draft(c: httpx.AsyncClient, draft: dict[str, Any], config: dict[str, Any]) -> httpx.Response:
    return await c.put(
        "/api/admin/rules/draft", json={"config": config}, headers={"If-Match": f'"{draft["lockVersion"]}"'}
    )


def with_value(config: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    out = copy.deepcopy(config)
    node = out
    *parents, leaf = path.split(".")
    for key in parents:
        node = node[key]
    node[leaf] = value
    return out


async def publish(
    c: httpx.AsyncClient, *, active_version: int = 1, ack: list[str] | None = None
) -> httpx.Response:
    report = (await c.post("/api/admin/rules/draft/validate")).json()
    return await c.post(
        "/api/admin/rules/draft/publish",
        json={
            "expectedHash": report["configHash"],
            "expectedActiveVersion": active_version,
            "note": "Đổi thời gian lượt",
            "acknowledgedWarnings": ack or [],
        },
    )


async def actions(app: object) -> list[str]:
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        return list(await session.scalars(select(RuleAuditLog.action).order_by(RuleAuditLog.id)))


async def test_seeded_v1_is_active_with_default_config(admin_client: httpx.AsyncClient) -> None:
    active = (await admin_client.get("/api/admin/rules/active")).json()
    assert active["version"] == 1
    assert active["config"]["turn"]["timeLimitSeconds"] == 30
    assert len(active["configHash"]) == 64


@pytest.mark.rule(134)
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/admin/rules/draft"),
        ("PUT", "/api/admin/rules/draft"),
        ("DELETE", "/api/admin/rules/draft"),
        ("POST", "/api/admin/rules/draft/publish"),
        ("POST", "/api/admin/rules/rollback"),
        ("GET", "/api/admin/rules/active"),
        ("GET", "/api/admin/audit"),
    ],
)
async def test_only_logged_in_system_admin_can_use_rule_admin_api(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    # ID 134 (override): chủ phòng / Guest không có quyền — mọi request không có phiên Admin bị 401.
    response = await client.request(method, path, json={})
    assert response.status_code == 401


async def test_create_draft_twice_conflicts(admin_client: httpx.AsyncClient) -> None:
    draft = await create_draft(admin_client)
    assert (draft["status"], draft["lockVersion"], draft["basedOnVersion"]) == ("DRAFT", 1, 1)
    response = await admin_client.post("/api/admin/rules/draft", json={})
    assert (response.status_code, response.json()["code"]) == (409, "DRAFT_EXISTS")


async def test_update_requires_matching_if_match(admin_client: httpx.AsyncClient) -> None:
    draft = await create_draft(admin_client)
    config = with_value(draft["config"], "turn.timeLimitSeconds", 45)
    saved = await save_draft(admin_client, draft, config)
    assert saved.status_code == 200
    assert saved.headers["ETag"] == '"2"'
    stale = await save_draft(admin_client, draft, config)  # vẫn gửi lockVersion 1
    assert (stale.status_code, stale.json()["code"]) == (409, "DRAFT_CHANGED")
    missing = await admin_client.put("/api/admin/rules/draft", json={"config": config})
    assert missing.status_code == 428


async def test_update_with_wrong_type_is_rejected_with_rule_path(admin_client: httpx.AsyncClient) -> None:
    draft = await create_draft(admin_client)
    response = await save_draft(admin_client, draft, with_value(draft["config"], "turn.timeLimitSeconds", 5))
    body = response.json()
    assert (response.status_code, body["code"]) == (422, "CONFIG_INVALID")
    assert body["errors"][0]["path"] == "turn.timeLimitSeconds"
    assert 141 in body["errors"][0]["excelIds"]


async def test_draft_with_semantic_error_can_be_saved_but_not_published(
    admin_client: httpx.AsyncClient,
) -> None:
    draft = await create_draft(admin_client)
    saved = await save_draft(admin_client, draft, with_value(draft["config"], "scoring.rank.first", 300))
    assert saved.status_code == 200
    report = (await admin_client.post("/api/admin/rules/draft/validate")).json()
    assert [e["code"] for e in report["errors"]] == ["V1"]
    response = await publish(admin_client)
    assert (response.status_code, response.json()["code"]) == (422, "CONFIG_INVALID")


async def test_diff_lists_changes_against_active(admin_client: httpx.AsyncClient) -> None:
    draft = await create_draft(admin_client)
    await save_draft(admin_client, draft, with_value(draft["config"], "turn.timeLimitSeconds", 45))
    diff = (await admin_client.get("/api/admin/rules/draft/diff")).json()
    assert diff["againstVersion"] == 1
    assert diff["changes"] == [
        {
            "path": "turn.timeLimitSeconds",
            "label": "Thời gian mỗi lượt (giây)",
            "before": 30,
            "after": 45,
            "excelIds": [141, 10, 13],
        }
    ]


@pytest.mark.rule(135, 137, 138)
async def test_publish_makes_new_global_version_visible_to_players(
    app: object, admin_client: httpx.AsyncClient, client: httpx.AsyncClient
) -> None:
    draft = await create_draft(admin_client)
    await save_draft(admin_client, draft, with_value(draft["config"], "turn.timeLimitSeconds", 45))
    response = await publish(admin_client)
    assert response.status_code == 200, response.text
    assert (response.json()["version"], response.json()["status"]) == (2, "ACTIVE")

    public = (await client.get("/api/rules/active")).json()  # người chơi (không đăng nhập) xem được
    assert (public["version"], public["config"]["turn"]["timeLimitSeconds"]) == (2, 45)
    versions = (await admin_client.get("/api/admin/rules/versions")).json()["items"]
    assert [(v["version"], v["status"]) for v in versions] == [(2, "ACTIVE"), (1, "SUPERSEDED")]
    assert (await admin_client.get("/api/admin/rules/draft")).status_code == 404
    assert (await actions(app))[-1] == "PUBLISH"
    # v1 cũ vẫn xem được (dùng cho snapshot / tranh chấp ván đã chơi)
    assert (await client.get("/api/rules/versions/1")).json()["config"]["turn"]["timeLimitSeconds"] == 30


async def test_publish_rejects_stale_hash_or_active_version(admin_client: httpx.AsyncClient) -> None:
    draft = await create_draft(admin_client)
    await save_draft(admin_client, draft, with_value(draft["config"], "turn.timeLimitSeconds", 45))
    report = (await admin_client.post("/api/admin/rules/draft/validate")).json()
    body = {"expectedHash": "0" * 64, "expectedActiveVersion": 1, "note": "abc"}
    wrong_hash = await admin_client.post("/api/admin/rules/draft/publish", json=body)
    assert wrong_hash.json()["code"] == "DRAFT_CHANGED"
    body = {"expectedHash": report["configHash"], "expectedActiveVersion": 7, "note": "abc"}
    wrong_active = await admin_client.post("/api/admin/rules/draft/publish", json=body)
    assert wrong_active.json()["code"] == "ACTIVE_CHANGED"


async def test_publish_requires_acknowledging_warnings(admin_client: httpx.AsyncClient) -> None:
    draft = await create_draft(admin_client)
    await save_draft(admin_client, draft, with_value(draft["config"], "chop.allowChain", False))
    refused = await publish(admin_client)
    assert (refused.status_code, refused.json()["missingWarnings"]) == (422, ["V5"])
    assert (await publish(admin_client, ack=["V5"])).status_code == 200


async def test_publish_without_changes_is_refused(admin_client: httpx.AsyncClient) -> None:
    await create_draft(admin_client)
    response = await publish(admin_client)
    assert (response.status_code, response.json()["code"]) == (409, "NO_CHANGES")


async def test_discard_draft(admin_client: httpx.AsyncClient) -> None:
    draft = await create_draft(admin_client)
    response = await admin_client.delete(
        "/api/admin/rules/draft", headers={"If-Match": str(draft["lockVersion"])}
    )
    assert response.status_code == 204
    assert (await admin_client.get("/api/admin/rules/draft")).status_code == 404


async def test_rollback_creates_new_version_with_old_config(
    app: object, admin_client: httpx.AsyncClient
) -> None:
    draft = await create_draft(admin_client)
    await save_draft(admin_client, draft, with_value(draft["config"], "turn.timeLimitSeconds", 45))
    await publish(admin_client)
    response = await admin_client.post(
        "/api/admin/rules/rollback",
        json={"targetVersion": 1, "expectedActiveVersion": 2, "note": "Quay lại v1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["version"], body["basedOnVersion"], body["config"]["turn"]["timeLimitSeconds"]) == (3, 1, 30)
    assert (await actions(app))[-1] == "ROLLBACK"


async def test_two_admins_publishing_at_once_only_one_wins(
    app: object, admin_client: httpx.AsyncClient
) -> None:
    draft = await create_draft(admin_client)
    await save_draft(admin_client, draft, with_value(draft["config"], "turn.timeLimitSeconds", 45))
    report = (await admin_client.post("/api/admin/rules/draft/validate")).json()
    body = {"expectedHash": report["configHash"], "expectedActiveVersion": 1, "note": "Đồng thời"}
    async with make_client(app) as second:
        await login(second)
        results = await asyncio.gather(
            admin_client.post("/api/admin/rules/draft/publish", json=body),
            second.post("/api/admin/rules/draft/publish", json=body),
        )
    statuses = sorted(r.status_code for r in results)
    assert statuses[0] == 200
    assert statuses[1] in (404, 409)  # người sau: bản nháp đã thành ACTIVE hoặc luật ACTIVE đã đổi
    versions = (await admin_client.get("/api/admin/rules/versions")).json()["items"]
    assert [v["status"] for v in versions].count("ACTIVE") == 1


async def test_audit_list_shows_admin_actions_newest_first(admin_client: httpx.AsyncClient) -> None:
    await create_draft(admin_client)
    items = (await admin_client.get("/api/admin/audit")).json()["items"]
    assert [i["action"] for i in items[:2]] == ["CREATE_DRAFT", "LOGIN"]
    assert items[0]["admin"] == "admin"

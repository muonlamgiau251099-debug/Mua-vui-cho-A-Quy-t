"""API Admin quản lý luật GLOBAL (docs/gd2/04 §1). Chỉ Admin hệ thống — ID 134."""

from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import AdminRead, AdminWrite, DbSession, Meta, parse_if_match
from app.models import GlobalRuleVersion
from app.realtime.hub import RoomHub
from app.services import rules
from tlmn_engine.rules_config import validate_rule_config

router = APIRouter(prefix="/api/admin", tags=["admin-rules"])


def version_json(row: GlobalRuleVersion, *, with_config: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "version": row.version,
        "status": row.status,
        "schemaVersion": row.schema_version,
        "configHash": row.config_hash,
        "basedOnVersion": row.based_on_version,
        "note": row.note,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "publishedAt": row.published_at.isoformat() if row.published_at else None,
    }
    if with_config:
        data["config"] = row.config
    return data


def draft_json(row: GlobalRuleVersion, response: Response) -> dict[str, Any]:
    response.headers["ETag"] = f'"{row.lock_version}"'
    return {
        **version_json(row),
        "lockVersion": row.lock_version,
        "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
    }


async def notify_rules_updated(request: Request, row: GlobalRuleVersion) -> None:
    """ID 137: luật mới áp dụng từ ván tiếp theo; báo cho mọi phòng đang mở."""
    hub: RoomHub = request.app.state.hub
    payload = {"version": row.version, "configHash": row.config_hash, "appliesFrom": "next_game"}
    await hub.broadcast_all("rules.updated", payload)


IfMatch = Annotated[str | None, Header(alias="If-Match")]


class CreateDraftBody(BaseModel):
    fromVersion: int | None = Field(default=None, ge=1)


class UpdateDraftBody(BaseModel):
    config: dict[str, Any]


class PublishBody(BaseModel):
    expectedHash: str = Field(min_length=64, max_length=64)
    expectedActiveVersion: int = Field(ge=1)
    note: str = Field(min_length=3, max_length=500)
    acknowledgedWarnings: list[str] = Field(default_factory=list, max_length=50)


class RollbackBody(BaseModel):
    targetVersion: int = Field(ge=1)
    expectedActiveVersion: int = Field(ge=1)
    note: str = Field(min_length=3, max_length=500)


@router.get("/rules/active")
async def active(_: AdminRead, db: DbSession) -> dict[str, Any]:
    return version_json(await rules.get_active(db))


@router.get("/rules/versions")
async def versions(_: AdminRead, db: DbSession) -> dict[str, Any]:
    return {"items": [version_json(v, with_config=False) for v in await rules.list_versions(db)]}


@router.get("/rules/versions/{version}")
async def version_detail(version: int, _: AdminRead, db: DbSession) -> dict[str, Any]:
    return version_json(await rules.get_version(db, version))


@router.get("/rules/draft")
async def get_draft(_: AdminRead, db: DbSession, response: Response) -> dict[str, Any]:
    return draft_json(await rules.require_draft(db), response)


@router.post("/rules/draft", status_code=201)
async def create_draft(
    body: CreateDraftBody, ctx: AdminWrite, db: DbSession, meta: Meta, response: Response
) -> dict[str, Any]:
    return draft_json(await rules.create_draft(db, meta, ctx.admin, body.fromVersion), response)


@router.put("/rules/draft")
async def update_draft(
    body: UpdateDraftBody,
    ctx: AdminWrite,
    db: DbSession,
    meta: Meta,
    response: Response,
    if_match: IfMatch = None,
) -> dict[str, Any]:
    draft = await rules.update_draft(db, meta, ctx.admin, parse_if_match(if_match), body.config)
    return draft_json(draft, response)


@router.delete("/rules/draft", status_code=204)
async def discard_draft(ctx: AdminWrite, db: DbSession, meta: Meta, if_match: IfMatch = None) -> None:
    await rules.discard_draft(db, meta, ctx.admin, parse_if_match(if_match))


@router.post("/rules/draft/validate")
async def validate_draft(_: AdminWrite, db: DbSession) -> dict[str, Any]:
    return validate_rule_config((await rules.require_draft(db)).config).to_json()


@router.get("/rules/draft/diff")
async def diff_draft(
    _: AdminRead, db: DbSession, against: Annotated[int | None, Query(ge=1)] = None
) -> dict[str, Any]:
    base, changes = await rules.diff_draft(db, against)
    return {"againstVersion": base.version, "changes": changes}


@router.post("/rules/draft/publish")
async def publish(
    body: PublishBody, request: Request, ctx: AdminWrite, db: DbSession, meta: Meta
) -> dict[str, Any]:
    row = await rules.publish(
        db,
        meta,
        ctx.admin,
        expected_hash=body.expectedHash,
        expected_active_version=body.expectedActiveVersion,
        note=body.note.strip(),
        acknowledged_warnings=body.acknowledgedWarnings,
    )
    await notify_rules_updated(request, row)
    return version_json(row)


@router.post("/rules/rollback")
async def rollback(
    body: RollbackBody, request: Request, ctx: AdminWrite, db: DbSession, meta: Meta
) -> dict[str, Any]:
    row = await rules.rollback(
        db,
        meta,
        ctx.admin,
        target_version=body.targetVersion,
        expected_active_version=body.expectedActiveVersion,
        note=body.note.strip(),
    )
    await notify_rules_updated(request, row)
    return version_json(row)


@router.get("/audit")
async def audit(
    _: AdminRead,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: Annotated[int | None, Query(ge=1)] = None,
) -> dict[str, Any]:
    items = [
        {
            "id": log.id,
            "action": log.action,
            "admin": username,
            "ruleVersionId": log.rule_version_id,
            "beforeHash": log.before_hash,
            "afterHash": log.after_hash,
            "diff": log.diff,
            "detail": log.detail,
            "ip": log.ip,
            "createdAt": log.created_at.isoformat(),
        }
        for log, username in await rules.list_audit(db, limit, before)
    ]
    return {"items": items, "nextBefore": items[-1]["id"] if len(items) == limit else None}

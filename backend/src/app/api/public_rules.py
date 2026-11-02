"""API xem luật công khai — Guest và chủ phòng chỉ được đọc (ID 134, 135, 138)."""

from typing import Any

from fastapi import APIRouter

from app.api.deps import DbSession
from app.errors import AppError
from app.services import rules
from tlmn_engine.catalog import raw_catalog
from tlmn_engine.rules_config import GROUP_LABELS, INVARIANTS, SCHEMA_VERSION, field_specs

router = APIRouter(prefix="/api/rules", tags=["rules"])


def public_version_json(
    version: int | None, config_hash: str, config: dict[str, Any], published_at: str | None
) -> dict[str, Any]:
    return {"version": version, "configHash": config_hash, "config": config, "publishedAt": published_at}


@router.get("/active")
async def active(db: DbSession) -> dict[str, Any]:
    row = await rules.get_active(db)
    return public_version_json(
        row.version, row.config_hash, row.config, row.published_at.isoformat() if row.published_at else None
    )


@router.get("/versions/{version}")
async def version_detail(version: int, db: DbSession) -> dict[str, Any]:
    row = await rules.get_version(db, version)
    if row.status not in ("ACTIVE", "SUPERSEDED"):
        raise AppError(404, "VERSION_NOT_FOUND", f"Không có phiên bản luật v{version}")
    return public_version_json(
        row.version, row.config_hash, row.config, row.published_at.isoformat() if row.published_at else None
    )


@router.get("/catalog")
async def catalog() -> dict[str, object]:
    return raw_catalog()


@router.get("/schema")
async def schema() -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "groups": [{"key": key, "label": label} for key, label in GROUP_LABELS.items()],
        "fields": [spec.to_json() for spec in field_specs()],
        "invariants": INVARIANTS,
    }

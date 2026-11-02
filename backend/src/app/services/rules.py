"""Quản lý RuleConfig GLOBAL: draft → validate → diff → publish → rollback (docs/gd2/02 §6).

Mọi hàm ghi đều tự commit; caller chỉ truyền session mới.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import AdminUser, GlobalRuleVersion, RuleAuditLog
from app.services.audit import RequestMeta, add_audit
from tlmn_engine.rules_config import (
    SCHEMA_VERSION,
    config_hash,
    default_config,
    diff_configs,
    parse_rule_config,
    validate_rule_config,
)

# Mọi thao tác ghi luật được tuần tự hóa bằng một advisory lock trong transaction, để hai Admin
# publish/rollback cùng lúc không chồng nhau (người sau thấy trạng thái mới và nhận 409).
_RULES_LOCK_KEY = 7_410_001


def _now() -> datetime:
    return datetime.now(UTC)


async def _lock_rules(session: AsyncSession) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _RULES_LOCK_KEY})


async def get_active(session: AsyncSession, *, for_update: bool = False) -> GlobalRuleVersion:
    stmt = select(GlobalRuleVersion).where(GlobalRuleVersion.status == "ACTIVE")
    if for_update:
        stmt = stmt.with_for_update()
    active = await session.scalar(stmt)
    if active is None:
        raise AppError(503, "NO_ACTIVE_RULES", "Hệ thống chưa có bộ luật đang áp dụng")
    return active


async def get_draft(session: AsyncSession, *, for_update: bool = False) -> GlobalRuleVersion | None:
    stmt = select(GlobalRuleVersion).where(GlobalRuleVersion.status == "DRAFT")
    if for_update:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)


async def require_draft(session: AsyncSession, *, for_update: bool = False) -> GlobalRuleVersion:
    draft = await get_draft(session, for_update=for_update)
    if draft is None:
        raise AppError(404, "NO_DRAFT", "Chưa có bản nháp luật")
    return draft


async def get_version(session: AsyncSession, version: int) -> GlobalRuleVersion:
    row = await session.scalar(select(GlobalRuleVersion).where(GlobalRuleVersion.version == version))
    if row is None:
        raise AppError(404, "VERSION_NOT_FOUND", f"Không có phiên bản luật v{version}")
    return row


async def list_versions(session: AsyncSession) -> list[GlobalRuleVersion]:
    rows = await session.scalars(
        select(GlobalRuleVersion)
        .where(GlobalRuleVersion.version.is_not(None))
        .order_by(GlobalRuleVersion.version.desc())
    )
    return list(rows)


async def ensure_seeded(session: AsyncSession) -> GlobalRuleVersion | None:
    """Tạo phiên bản v1 từ cấu hình mặc định đã duyệt nếu hệ thống chưa có luật ACTIVE."""
    if await session.scalar(select(GlobalRuleVersion.id).where(GlobalRuleVersion.status == "ACTIVE")):
        return None
    config = default_config()
    row = GlobalRuleVersion(
        version=1,
        status="ACTIVE",
        schema_version=SCHEMA_VERSION,
        config=config.model_dump(mode="json"),
        config_hash=config_hash(config),
        note="Cấu hình mặc định đã duyệt (GĐ1–GĐ2)",
        published_at=_now(),
    )
    session.add(row)
    await session.flush()
    add_audit(
        session,
        RequestMeta(None, "system"),
        "SEED",
        admin_id=None,
        rule_version_id=row.id,
        after_hash=row.config_hash,
    )
    try:
        await session.commit()
    except IntegrityError:  # tiến trình khác vừa seed
        await session.rollback()
        return None
    return row


def _check_lock(draft: GlobalRuleVersion, if_match: int | None) -> None:
    if if_match is None:
        raise AppError(428, "PRECONDITION_REQUIRED", "Thiếu header If-Match (lock_version của bản nháp)")
    if if_match != draft.lock_version:
        raise AppError(
            409,
            "DRAFT_CHANGED",
            "Bản nháp vừa được người khác sửa. Hãy tải lại trước khi lưu.",
            currentLockVersion=draft.lock_version,
        )


async def create_draft(
    session: AsyncSession, meta: RequestMeta, admin: AdminUser, from_version: int | None
) -> GlobalRuleVersion:
    await _lock_rules(session)
    if await get_draft(session):
        raise AppError(409, "DRAFT_EXISTS", "Đã có bản nháp. Hãy sửa tiếp hoặc hủy bản nháp hiện tại.")
    source = await get_version(session, from_version) if from_version else await get_active(session)
    draft = GlobalRuleVersion(
        version=None,
        status="DRAFT",
        schema_version=SCHEMA_VERSION,
        config=source.config,
        config_hash=source.config_hash,
        based_on_version=source.version,
        lock_version=1,
        created_by=admin.id,
    )
    session.add(draft)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(409, "DRAFT_EXISTS", "Đã có bản nháp do Admin khác vừa tạo.") from exc
    add_audit(
        session,
        meta,
        "CREATE_DRAFT",
        admin_id=admin.id,
        rule_version_id=draft.id,
        after_hash=draft.config_hash,
        detail={"fromVersion": source.version},
    )
    await session.commit()
    return draft


async def update_draft(
    session: AsyncSession, meta: RequestMeta, admin: AdminUser, if_match: int | None, config: dict[str, Any]
) -> GlobalRuleVersion:
    await _lock_rules(session)
    draft = await require_draft(session)
    _check_lock(draft, if_match)
    try:
        parsed = parse_rule_config(config)
    except ValidationError:
        report = validate_rule_config(config)
        raise AppError(
            422, "CONFIG_INVALID", "Cấu hình sai kiểu hoặc ngoài giới hạn", **report.to_json()
        ) from None
    new_json = parsed.model_dump(mode="json")
    changes = [c.to_json() for c in diff_configs(draft.config, new_json)]
    before = draft.config_hash
    draft.config = new_json
    draft.config_hash = config_hash(parsed)
    draft.lock_version += 1
    draft.updated_by = admin.id
    draft.updated_at = _now()
    add_audit(
        session,
        meta,
        "UPDATE_DRAFT",
        admin_id=admin.id,
        rule_version_id=draft.id,
        before_hash=before,
        after_hash=draft.config_hash,
        diff=changes,
    )
    await session.commit()
    return draft


async def discard_draft(
    session: AsyncSession, meta: RequestMeta, admin: AdminUser, if_match: int | None
) -> None:
    await _lock_rules(session)
    draft = await require_draft(session)
    _check_lock(draft, if_match)
    draft.status = "DISCARDED"
    draft.updated_by = admin.id
    draft.updated_at = _now()
    add_audit(session, meta, "DISCARD_DRAFT", admin_id=admin.id, rule_version_id=draft.id)
    await session.commit()


async def diff_draft(
    session: AsyncSession, against: int | None
) -> tuple[GlobalRuleVersion, list[dict[str, Any]]]:
    draft = await require_draft(session)
    base = await get_version(session, against) if against else await get_active(session)
    return base, [c.to_json() for c in diff_configs(base.config, draft.config)]


async def _next_version(session: AsyncSession) -> int:
    current = await session.scalar(select(func.max(GlobalRuleVersion.version)))
    return (current or 0) + 1


async def publish(
    session: AsyncSession,
    meta: RequestMeta,
    admin: AdminUser,
    *,
    expected_hash: str,
    expected_active_version: int,
    note: str,
    acknowledged_warnings: list[str],
) -> GlobalRuleVersion:
    await _lock_rules(session)
    active = await get_active(session)
    draft = await require_draft(session)
    if active.version != expected_active_version:
        raise AppError(
            409,
            "ACTIVE_CHANGED",
            "Luật đang áp dụng vừa thay đổi. Hãy xem lại khác biệt trước khi xuất bản.",
            activeVersion=active.version,
        )
    if draft.config_hash != expected_hash:
        raise AppError(409, "DRAFT_CHANGED", "Bản nháp đã thay đổi sau lần kiểm tra. Hãy kiểm tra lại.")
    report = validate_rule_config(draft.config)
    if not report.ok:
        raise AppError(422, "CONFIG_INVALID", "Bản nháp còn lỗi, chưa thể xuất bản", **report.to_json())
    missing = sorted({w.code for w in report.warnings} - set(acknowledged_warnings))
    if missing:
        raise AppError(
            422,
            "WARNINGS_NOT_ACKNOWLEDGED",
            "Cần xác nhận đã đọc các cảnh báo",
            missingWarnings=missing,
            **report.to_json(),
        )
    if draft.config_hash == active.config_hash:
        raise AppError(409, "NO_CHANGES", "Bản nháp giống hệt luật đang áp dụng")

    changes = [c.to_json() for c in diff_configs(active.config, draft.config)]
    now = _now()
    next_version = await _next_version(session)
    active.status = "SUPERSEDED"
    await session.flush()
    draft.status = "ACTIVE"
    draft.version = next_version
    draft.note = note
    draft.published_by = admin.id
    draft.published_at = now
    add_audit(
        session,
        meta,
        "PUBLISH",
        admin_id=admin.id,
        rule_version_id=draft.id,
        before_hash=active.config_hash,
        after_hash=draft.config_hash,
        diff=changes,
        detail={
            "version": draft.version,
            "previousVersion": active.version,
            "note": note,
            "acknowledgedWarnings": acknowledged_warnings,
        },
    )
    await session.commit()
    return draft


async def rollback(
    session: AsyncSession,
    meta: RequestMeta,
    admin: AdminUser,
    *,
    target_version: int,
    expected_active_version: int,
    note: str,
) -> GlobalRuleVersion:
    """Rollback = tạo phiên bản MỚI chép config của phiên bản đích (ADR-010)."""
    await _lock_rules(session)
    active = await get_active(session)
    if active.version != expected_active_version:
        raise AppError(409, "ACTIVE_CHANGED", "Luật đang áp dụng vừa thay đổi.", activeVersion=active.version)
    target = await get_version(session, target_version)
    if target.config_hash == active.config_hash:
        raise AppError(409, "NO_CHANGES", f"v{target_version} giống hệt luật đang áp dụng")
    report = validate_rule_config(target.config)
    if not report.ok:
        raise AppError(
            422,
            "CONFIG_INVALID",
            f"v{target_version} không còn hợp lệ với schema hiện tại",
            **report.to_json(),
        )

    changes = [c.to_json() for c in diff_configs(active.config, target.config)]
    next_version = await _next_version(session)
    active.status = "SUPERSEDED"
    await session.flush()
    new = GlobalRuleVersion(
        version=next_version,
        status="ACTIVE",
        schema_version=SCHEMA_VERSION,
        config=target.config,
        config_hash=target.config_hash,
        based_on_version=target.version,
        note=note,
        created_by=admin.id,
        published_by=admin.id,
        published_at=_now(),
    )
    session.add(new)
    await session.flush()
    add_audit(
        session,
        meta,
        "ROLLBACK",
        admin_id=admin.id,
        rule_version_id=new.id,
        before_hash=active.config_hash,
        after_hash=new.config_hash,
        diff=changes,
        detail={
            "version": new.version,
            "targetVersion": target_version,
            "previousVersion": active.version,
            "note": note,
        },
    )
    await session.commit()
    return new


async def list_audit(
    session: AsyncSession, limit: int, before_id: int | None
) -> list[tuple[RuleAuditLog, str | None]]:
    stmt = (
        select(RuleAuditLog, AdminUser.username)
        .outerjoin(AdminUser, AdminUser.id == RuleAuditLog.admin_id)
        .order_by(RuleAuditLog.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        stmt = stmt.where(RuleAuditLog.id < before_id)
    return [(log, username) for log, username in (await session.execute(stmt)).all()]

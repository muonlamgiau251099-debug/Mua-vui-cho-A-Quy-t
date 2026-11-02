import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RuleAuditLog


@dataclass(frozen=True, slots=True)
class RequestMeta:
    ip: str | None
    user_agent: str | None


def add_audit(
    session: AsyncSession,
    meta: RequestMeta,
    action: str,
    *,
    admin_id: uuid.UUID | None,
    rule_version_id: int | None = None,
    before_hash: str | None = None,
    after_hash: str | None = None,
    diff: list[Any] | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        RuleAuditLog(
            admin_id=admin_id,
            action=action,
            rule_version_id=rule_version_id,
            before_hash=before_hash,
            after_hash=after_hash,
            diff=diff,
            detail=detail,
            ip=meta.ip,
            user_agent=meta.user_agent,
        )
    )

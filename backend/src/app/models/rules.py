import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

RULE_STATUSES = ("DRAFT", "ACTIVE", "SUPERSEDED", "DISCARDED")


class GlobalRuleVersion(Base):
    """Một phiên bản RuleConfig GLOBAL. Tối đa 1 ACTIVE và 1 DRAFT (partial unique index)."""

    __tablename__ = "global_rule_versions"
    __table_args__ = (
        CheckConstraint(f"status IN {RULE_STATUSES}", name="ck_rule_versions_status"),
        CheckConstraint(
            "(status = 'DRAFT' OR status = 'DISCARDED') = (version IS NULL)", name="ck_rule_versions_version"
        ),
        Index(
            "ux_rule_versions_one_active", "status", unique=True, postgresql_where=text("status = 'ACTIVE'")
        ),
        Index("ux_rule_versions_one_draft", "status", unique=True, postgresql_where=text("status = 'DRAFT'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    version: Mapped[int | None] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(String(16))
    schema_version: Mapped[int]
    config: Mapped[dict[str, Any]]
    config_hash: Mapped[str] = mapped_column(String(64))
    based_on_version: Mapped[int | None]
    lock_version: Mapped[int] = mapped_column(server_default=text("1"))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("admin_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("admin_users.id"))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("admin_users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RuleAuditLog(Base):
    """Nhật ký thao tác Admin. Append-only: trigger DB chặn UPDATE/DELETE."""

    __tablename__ = "rule_audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    admin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("admin_users.id"))
    action: Mapped[str] = mapped_column(String(32), index=True)
    rule_version_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("global_rule_versions.id"))
    before_hash: Mapped[str | None] = mapped_column(String(64))
    after_hash: Mapped[str | None] = mapped_column(String(64))
    diff: Mapped[list[Any] | None]
    detail: Mapped[dict[str, Any] | None]
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

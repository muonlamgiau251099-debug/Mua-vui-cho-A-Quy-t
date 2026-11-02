"""admin + global rules + audit log (slice S1)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", TS),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", TS),
    )
    op.create_index("ux_admin_users_username", "admin_users", [sa.text("lower(username)")], unique=True)

    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("admin_id", sa.Uuid(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("revoked_at", TS),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(400)),
    )
    op.create_index("ix_admin_sessions_admin_id", "admin_sessions", ["admin_id"])

    op.create_table(
        "global_rule_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("version", sa.Integer(), unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("based_on_version", sa.Integer()),
        sa.Column("lock_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("admin_users.id")),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("admin_users.id")),
        sa.Column("updated_at", TS),
        sa.Column("published_by", sa.Uuid(), sa.ForeignKey("admin_users.id")),
        sa.Column("published_at", TS),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'SUPERSEDED', 'DISCARDED')", name="ck_rule_versions_status"
        ),
        sa.CheckConstraint(
            "(status = 'DRAFT' OR status = 'DISCARDED') = (version IS NULL)", name="ck_rule_versions_version"
        ),
    )
    op.create_index(
        "ux_rule_versions_one_active",
        "global_rule_versions",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "ux_rule_versions_one_draft",
        "global_rule_versions",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'DRAFT'"),
    )

    op.create_table(
        "rule_audit_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("admin_id", sa.Uuid(), sa.ForeignKey("admin_users.id")),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("rule_version_id", sa.BigInteger(), sa.ForeignKey("global_rule_versions.id")),
        sa.Column("before_hash", sa.String(64)),
        sa.Column("after_hash", sa.String(64)),
        sa.Column("diff", postgresql.JSONB()),
        sa.Column("detail", postgresql.JSONB()),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(400)),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rule_audit_logs_action", "rule_audit_logs", ["action"])
    op.create_index("ix_rule_audit_logs_created_at", "rule_audit_logs", ["created_at"])

    # Audit log chỉ được thêm, không được sửa/xóa (docs/gd2/01 §3.1).
    op.execute(
        """
        CREATE FUNCTION forbid_row_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Bảng % chỉ cho phép thêm dòng (append-only)', TG_TABLE_NAME;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER rule_audit_logs_append_only BEFORE UPDATE OR DELETE ON rule_audit_logs
        FOR EACH ROW EXECUTE FUNCTION forbid_row_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS rule_audit_logs_append_only ON rule_audit_logs")
    op.drop_table("rule_audit_logs")
    op.execute("DROP FUNCTION IF EXISTS forbid_row_mutation()")
    op.drop_table("global_rule_versions")
    op.drop_table("admin_sessions")
    op.drop_table("admin_users")

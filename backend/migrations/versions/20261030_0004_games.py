"""game sessions + games + game events + command dedup (slice S4)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "game_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("room_id", sa.Uuid(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("session_no", sa.Integer(), nullable=False),
        sa.Column("roster", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(10), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("end_reason", sa.String(30)),
        sa.Column("started_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", TS),
        sa.CheckConstraint("status IN ('ACTIVE', 'ENDED')", name="ck_game_sessions_status"),
        sa.UniqueConstraint("room_id", "session_no", name="uq_game_sessions_room_no"),
    )
    op.create_index(
        "ux_game_sessions_one_active",
        "game_sessions",
        ["room_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "games",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("game_sessions.id"), nullable=False),
        sa.Column("room_id", sa.Uuid(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("game_no", sa.Integer(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("rules_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("rules_hash", sa.String(64), nullable=False),
        sa.Column("opening_mode", sa.String(16), nullable=False),
        sa.Column("deck", postgresql.JSONB(), nullable=False),
        sa.Column("deck_salt", sa.String(64), nullable=False),
        sa.Column("deck_commitment", sa.String(64), nullable=False),
        sa.Column("redeal_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(12), server_default=sa.text("'IN_PROGRESS'"), nullable=False),
        sa.Column("end_type", sa.String(20)),
        sa.Column("cancel_reason", sa.String(30)),
        sa.Column("winner_seat", sa.SmallInteger()),
        sa.Column("last_seq", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("started_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", TS),
        sa.CheckConstraint("status IN ('IN_PROGRESS', 'FINISHED', 'CANCELLED')", name="ck_games_status"),
        sa.UniqueConstraint("session_id", "game_no", name="uq_games_session_no"),
    )
    op.create_index(
        "ux_games_one_in_progress", "games", ["room_id"], unique=True, postgresql_where=sa.text("status = 'IN_PROGRESS'")
    )

    op.create_table(
        "game_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("game_id", sa.Uuid(), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("actor_seat", sa.SmallInteger()),
        sa.Column("request_id", sa.Uuid()),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("game_id", "seq", name="uq_game_events_seq"),
    )

    op.create_table(
        "command_dedup",
        sa.Column("game_id", sa.Uuid(), sa.ForeignKey("games.id"), primary_key=True),
        sa.Column("seat", sa.SmallInteger(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), primary_key=True),
        sa.Column("outcome", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )

    # Luật, bộ bài và mã kiểm chứng của ván là bất biến (ID 136, 156; ADR-008).
    op.execute(
        """
        CREATE FUNCTION forbid_game_identity_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.rules_snapshot IS DISTINCT FROM OLD.rules_snapshot
               OR NEW.rules_hash IS DISTINCT FROM OLD.rules_hash
               OR NEW.deck IS DISTINCT FROM OLD.deck
               OR NEW.deck_salt IS DISTINCT FROM OLD.deck_salt
               OR NEW.deck_commitment IS DISTINCT FROM OLD.deck_commitment THEN
                RAISE EXCEPTION 'Luật và bộ bài của ván không được sửa (immutable)';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER games_immutable_identity BEFORE UPDATE ON games
        FOR EACH ROW EXECUTE FUNCTION forbid_game_identity_change();
        """
    )
    op.execute(
        """
        CREATE TRIGGER game_events_append_only BEFORE UPDATE OR DELETE ON game_events
        FOR EACH ROW EXECUTE FUNCTION forbid_row_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS game_events_append_only ON game_events")
    op.execute("DROP TRIGGER IF EXISTS games_immutable_identity ON games")
    op.execute("DROP FUNCTION IF EXISTS forbid_game_identity_change()")
    op.drop_table("command_dedup")
    op.drop_table("game_events")
    op.drop_table("games")
    op.drop_table("game_sessions")

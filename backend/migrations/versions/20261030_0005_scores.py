"""game results + score transfers + session scores (slice S5)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "game_results",
        # PK = game_id: một ván chỉ ghi kết quả đúng một lần → không cộng điểm trùng (docs/gd2/01 §3.2).
        sa.Column("game_id", sa.Uuid(), sa.ForeignKey("games.id"), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("game_sessions.id"), nullable=False),
        sa.Column("end_type", sa.String(20), nullable=False),
        sa.Column("ranks", postgresql.JSONB(), nullable=False),
        sa.Column("statuses", postgresql.JSONB(), nullable=False),
        sa.Column("net", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_game_results_session", "game_results", ["session_id"])

    op.create_table(
        "score_transfers",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("game_id", sa.Uuid(), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("game_sessions.id"), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("from_seat", sa.SmallInteger(), nullable=False),
        sa.Column("to_seat", sa.SmallInteger(), nullable=False),
        sa.Column("from_guest", sa.Uuid(), sa.ForeignKey("guest_players.id"), nullable=False),
        sa.Column("to_guest", sa.Uuid(), sa.ForeignKey("guest_players.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("game_id", "line_no", name="uq_score_transfers_line"),
        sa.CheckConstraint("amount > 0", name="ck_score_transfers_amount"),
        sa.CheckConstraint("from_seat <> to_seat", name="ck_score_transfers_seats"),
    )
    op.create_index("ix_score_transfers_session", "score_transfers", ["session_id"])

    op.create_table(
        "session_scores",
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("game_sessions.id"), primary_key=True),
        sa.Column("guest_id", sa.Uuid(), sa.ForeignKey("guest_players.id"), primary_key=True),
        sa.Column("seat", sa.SmallInteger(), nullable=False),
        sa.Column("total", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("games_counted", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        """
        CREATE TRIGGER score_transfers_append_only BEFORE UPDATE OR DELETE ON score_transfers
        FOR EACH ROW EXECUTE FUNCTION forbid_row_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS score_transfers_append_only ON score_transfers")
    op.drop_table("session_scores")
    op.drop_table("score_transfers")
    op.drop_table("game_results")

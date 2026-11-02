"""game snapshots + state hash để khôi phục ván sau khi server khởi động lại (slice S6)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "game_snapshots",
        sa.Column("game_id", sa.Uuid(), sa.ForeignKey("games.id"), primary_key=True),
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("state", postgresql.JSONB(), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("games", sa.Column("state_hash", sa.String(64)))
    op.add_column("game_events", sa.Column("state_hash", sa.String(64)))


def downgrade() -> None:
    op.drop_column("game_events", "state_hash")
    op.drop_column("games", "state_hash")
    op.drop_table("game_snapshots")

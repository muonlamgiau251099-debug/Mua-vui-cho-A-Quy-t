"""guest players + rooms + room seats (slice S2)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "guest_players",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("nickname", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", TS, nullable=False),
    )
    op.create_index("ix_guest_players_expires_at", "guest_players", ["expires_at"])

    op.create_table(
        "rooms",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("code", sa.String(6), nullable=False),
        sa.Column("owner_guest_id", sa.Uuid(), sa.ForeignKey("guest_players.id")),
        sa.Column("status", sa.String(10), server_default=sa.text("'WAITING'"), nullable=False),
        sa.Column("state_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("guest_players.id"), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", TS),
        sa.Column("close_reason", sa.String(20)),
        sa.CheckConstraint("status IN ('WAITING', 'PLAYING', 'CLOSED')", name="ck_rooms_status"),
    )
    op.create_index(
        "ux_rooms_open_code", "rooms", ["code"], unique=True, postgresql_where=sa.text("status <> 'CLOSED'")
    )

    op.create_table(
        "room_seats",
        sa.Column("room_id", sa.Uuid(), sa.ForeignKey("rooms.id"), primary_key=True),
        sa.Column("seat_no", sa.SmallInteger(), primary_key=True),
        sa.Column("guest_id", sa.Uuid(), sa.ForeignKey("guest_players.id")),
        sa.Column("conn_state", sa.String(12), server_default=sa.text("'EMPTY'"), nullable=False),
        sa.Column("ready", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("hold_until", TS),
        sa.Column("joined_at", TS),
        sa.CheckConstraint("seat_no BETWEEN 0 AND 3", name="ck_room_seats_seat_no"),
        sa.CheckConstraint("conn_state IN ('EMPTY', 'CONNECTED', 'DISCONNECTED')", name="ck_room_seats_conn"),
        sa.CheckConstraint("(guest_id IS NULL) = (conn_state = 'EMPTY')", name="ck_room_seats_guest"),
    )
    op.create_index(
        "ux_room_seats_guest", "room_seats", ["guest_id"], unique=True, postgresql_where=sa.text("guest_id IS NOT NULL")
    )
    op.create_index(
        "ix_room_seats_hold", "room_seats", ["hold_until"], postgresql_where=sa.text("conn_state = 'DISCONNECTED'")
    )


def downgrade() -> None:
    op.drop_table("room_seats")
    op.drop_table("rooms")
    op.drop_table("guest_players")

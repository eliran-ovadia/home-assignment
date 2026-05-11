"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Shared money/quantity precision. Intentionally duplicated from
# src/db/models.py rather than imported — migrations are immutable snapshots
# of schema-at-a-point-in-time; importing live model code would silently
# change the behaviour of an already-applied migration if the model later
# evolves. If you change one of these values, change the other too.
_MONEY = sa.Numeric(18, 6)
_RATIO = sa.Numeric(10, 4)


def upgrade() -> None:
    # uploads has no outgoing FKs — create first so other tables can reference it.
    op.create_table(
        "uploads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("file_content", sa.LargeBinary(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("violation_count", sa.Integer(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # users references uploads via the per-user last_viewed preference (ADR 016).
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "last_viewed_upload_id",
            sa.Integer(),
            sa.ForeignKey("uploads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "upload_id",
            sa.Integer(),
            sa.ForeignKey("uploads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transaction_id", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("isin", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("quantity", _MONEY, nullable=False),
        sa.Column("price", _MONEY, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "action IN ('Buy', 'Sell')",
            name="ck_transactions_action",
        ),
    )
    op.create_index("ix_transactions_upload_id", "transactions", ["upload_id"])
    op.create_index(
        "ix_transactions_upload_client_isin_ts",
        "transactions",
        ["upload_id", "client_id", "isin", "timestamp"],
    )

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "upload_id",
            sa.Integer(),
            sa.ForeignKey("uploads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("isin", sa.Text(), nullable=False),
        sa.Column("quantity", _MONEY, nullable=False, server_default=sa.text("0")),
        sa.Column("avg_cost", _MONEY, nullable=False, server_default=sa.text("0")),
        sa.Column("realized_pnl", _MONEY, nullable=False, server_default=sa.text("0")),
        sa.Column("unrealized_pnl", _MONEY, nullable=False, server_default=sa.text("0")),
        sa.Column("last_price", _MONEY, nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint(
            "upload_id", "client_id", "isin", name="uq_positions_upload_client_isin"
        ),
    )
    op.create_index("ix_positions_upload_client", "positions", ["upload_id", "client_id"])

    op.create_table(
        "violations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "upload_id",
            sa.Integer(),
            sa.ForeignKey("uploads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transaction_id", sa.Text(), nullable=True),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("isin", sa.Text(), nullable=True),
        sa.Column("violation_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_violations_upload_client", "violations", ["upload_id", "client_id"])
    op.create_index("ix_violations_upload_type", "violations", ["upload_id", "violation_type"])

    op.create_table(
        "client_analytics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "upload_id",
            sa.Integer(),
            sa.ForeignKey("uploads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("avg_holding_days", _RATIO, nullable=True),
        sa.Column("max_portfolio_value", _MONEY, nullable=False),
        sa.Column("min_portfolio_value", _MONEY, nullable=False),
        sa.Column("value_range", _MONEY, nullable=False),
        sa.Column("winning_trades", sa.Integer(), nullable=True),
        sa.Column("total_trades", sa.Integer(), nullable=True),
        sa.UniqueConstraint("upload_id", "client_id", name="uq_client_analytics_upload_client"),
    )
    op.create_index("ix_client_analytics_upload", "client_analytics", ["upload_id"])


def downgrade() -> None:
    # Reverse dependency order: drop tables that reference uploads before
    # uploads itself. `users.last_viewed_upload_id` is the only outbound FK
    # on users, so users must be dropped before uploads as well.
    op.drop_table("client_analytics")
    op.drop_table("violations")
    op.drop_table("positions")
    op.drop_table("transactions")
    op.drop_table("users")
    op.drop_table("uploads")

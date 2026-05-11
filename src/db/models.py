"""
SQLAlchemy 2.0 ORM models.

One class per table; structure mirrors SPEC §3 exactly. Constants used in the
schema (numeric precision/scale, allowed action values) are declared here so
the migration file and any runtime code reference the same source of truth.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# All money/quantity columns share this precision. NUMERIC(18,6) covers the
# real-world range for equity quantities and prices without floating-point drift.
_MONEY = Numeric(18, 6)
_RATIO = Numeric(10, 4)

ACTION_BUY = "Buy"
ACTION_SELL = "Sell"


class Base(DeclarativeBase):
    """Shared declarative base. `Base.metadata` is what Alembic targets."""


class Upload(Base):
    """
    File history. One row per uploaded file. Visible to every user in the
    organization — uploads are a shared pool (ADR 016).
    """

    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    violation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="upload",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    positions: Mapped[list[Position]] = relationship(
        back_populates="upload",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    violations: Mapped[list[Violation]] = relationship(
        back_populates="upload",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    client_analytics: Mapped[list[ClientAnalytic]] = relationship(
        back_populates="upload",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class User(Base):
    """
    One row per known corporate email (ADR 016).

    `email` is the identity. `last_viewed_upload_id` is a per-user UI preference
    that lets a returning user (possibly on a new device) auto-load the upload
    they last selected. `ON DELETE SET NULL` keeps this safe when an upload row
    is removed — the user just sees the upload list again on next visit.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    last_viewed_upload_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("uploads.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )


class Transaction(Base):
    """Raw validated rows from one upload. Immutable after insert."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    isin: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    price: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    upload: Mapped[Upload] = relationship(back_populates="transactions")

    __table_args__ = (
        # Literal value list, not an f-string — keeps the constraint SQL
        # immune to any future change in the Python-side constants. The
        # constants below remain the single source of truth for domain code.
        CheckConstraint(
            "action IN ('Buy', 'Sell')",
            name="ck_transactions_action",
        ),
        Index("ix_transactions_upload_id", "upload_id"),
        Index(
            "ix_transactions_upload_client_isin_ts",
            "upload_id",
            "client_id",
            "isin",
            "timestamp",
        ),
    )


class Position(Base):
    """One row per (upload, client, ISIN). Output of the FIFO engine."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    isin: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(_MONEY, nullable=False, default=Decimal(0))
    avg_cost: Mapped[Decimal] = mapped_column(_MONEY, nullable=False, default=Decimal(0))
    realized_pnl: Mapped[Decimal] = mapped_column(_MONEY, nullable=False, default=Decimal(0))
    unrealized_pnl: Mapped[Decimal] = mapped_column(_MONEY, nullable=False, default=Decimal(0))
    last_price: Mapped[Decimal] = mapped_column(_MONEY, nullable=False, default=Decimal(0))

    upload: Mapped[Upload] = relationship(back_populates="positions")

    __table_args__ = (
        UniqueConstraint("upload_id", "client_id", "isin", name="uq_positions_upload_client_isin"),
        Index("ix_positions_upload_client", "upload_id", "client_id"),
    )


class Violation(Base):
    """All detected violations for one upload. Immutable after insert."""

    __tablename__ = "violations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    isin: Mapped[str | None] = mapped_column(Text, nullable=True)
    violation_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    upload: Mapped[Upload] = relationship(back_populates="violations")

    __table_args__ = (
        Index("ix_violations_upload_client", "upload_id", "client_id"),
        Index("ix_violations_upload_type", "upload_id", "violation_type"),
    )


class ClientAnalytic(Base):
    """Precomputed per-client analytics. One row per (upload, client)."""

    __tablename__ = "client_analytics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    # null = the client has no completed buy→sell trades, so holding time is undefined.
    avg_holding_days: Mapped[Decimal | None] = mapped_column(_RATIO, nullable=True)
    max_portfolio_value: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    min_portfolio_value: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    value_range: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    # Populated by the FIFO engine (PR 3). Null when the client has no completed
    # trades — `winning_trades` is the count of completed trades with positive
    # realized P&L; `total_trades` is the total completed-trade count.
    winning_trades: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_trades: Mapped[int | None] = mapped_column(Integer, nullable=True)

    upload: Mapped[Upload] = relationship(back_populates="client_analytics")

    __table_args__ = (
        UniqueConstraint("upload_id", "client_id", name="uq_client_analytics_upload_client"),
        Index("ix_client_analytics_upload", "upload_id"),
    )

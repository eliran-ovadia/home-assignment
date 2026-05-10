"""
SQLAlchemy 2.0 ORM models.

One class per table; structure mirrors SPEC §3 exactly. Constants used in the
schema (numeric precision/scale, allowed action values) are declared here so
the migration file and any runtime code reference the same source of truth.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# All money/quantity columns share this precision. NUMERIC(18,6) covers the
# real-world range for equity quantities and prices without floating-point drift.
_MONEY = Numeric(18, 6)
_RATIO = Numeric(10, 4)

ACTION_BUY = "Buy"
ACTION_SELL = "Sell"


class Base(DeclarativeBase):
    """Shared declarative base. `Base.metadata` is what Alembic targets."""


class User(Base):
    """One row per anonymous browser session (ADR 015)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    uploads: Mapped[list[Upload]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Upload(Base):
    """File history. One row per uploaded file, per user. Never deleted."""

    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    violation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    # At most one active upload per user — enforced in application logic
    # (uploads repository.set_active) rather than as a partial unique index,
    # which keeps the schema portable and avoids deadlocks under load.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped[User] = relationship(back_populates="uploads")
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

    __table_args__ = (Index("ix_uploads_user_id", "user_id"),)


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
        CheckConstraint(
            f"action IN ('{ACTION_BUY}', '{ACTION_SELL}')",
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

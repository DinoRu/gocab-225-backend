import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    String, Text, Date, DateTime, Integer, Numeric, ForeignKey,
    UniqueConstraint, CheckConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDMixin, TimestampMixin


class PurchaseRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "purchase_requests"
    __table_args__ = (
        UniqueConstraint("bc_number", name="uq_purchase_requests_number"),
        CheckConstraint("status IN ('draft','sent','received')", name="ck_purchase_requests_status"),
    )

    bc_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    request_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    supply_request_id: Mapped[uuid.UUID | None] = mapped_column(
            PGUUID(as_uuid=True),
            ForeignKey("supply_requests.id", ondelete="SET NULL"),
            nullable=True,
        )

    supplier: Mapped["Supplier"] = relationship(lazy="selectin")
    items: Mapped[list["PurchaseRequestItem"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class PurchaseRequestItem(Base, UUIDMixin):
    __tablename__ = "purchase_request_items"
    __table_args__ = (
        UniqueConstraint("purchase_request_id", "part_id", name="uq_pr_item_request_part"),
        CheckConstraint("quantity > 0", name="ck_pr_item_quantity_positive"),
    )

    purchase_request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("purchase_requests.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("parts.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    request: Mapped["PurchaseRequest"] = relationship(back_populates="items")
    part: Mapped["Part"] = relationship(lazy="selectin")
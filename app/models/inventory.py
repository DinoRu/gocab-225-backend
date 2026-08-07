import uuid
from datetime import date, datetime

from sqlalchemy import (
    String, Text, Date, DateTime, Integer, ForeignKey,
    UniqueConstraint, CheckConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDMixin, TimestampMixin


class InventoryCount(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "inventory_counts"
    __table_args__ = (
        UniqueConstraint("count_number", name="uq_inventory_counts_number"),
    )

    count_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    count_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["InventoryCountItem"]] = relationship(
        back_populates="count", cascade="all, delete-orphan"
    )


class InventoryCountItem(Base, UUIDMixin):
    __tablename__ = "inventory_count_items"
    __table_args__ = (
        UniqueConstraint("inventory_count_id", "part_id", name="uq_count_item_count_part"),
        CheckConstraint("counted_quantity >= 0", name="ck_count_item_qty_nonneg"),
    )

    inventory_count_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_counts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("parts.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    counted_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    count: Mapped["InventoryCount"] = relationship(back_populates="items")
    part: Mapped["Part"] = relationship(lazy="selectin")
import uuid
from datetime import date, datetime

from sqlalchemy import (
    String, Text, Date, DateTime, Integer, ForeignKey,
    UniqueConstraint, CheckConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDMixin, TimestampMixin


class SupplyRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "supply_requests"
    __table_args__ = (
        UniqueConstraint("sr_number", name="uq_supply_requests_number"),
        CheckConstraint(
            "status IN ('open','in_progress','fulfilled')", name="ck_supply_requests_status"
        ),
    )

    sr_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    request_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    creator: Mapped["User | None"] = relationship(lazy="selectin")
    items: Mapped[list["SupplyRequestItem"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class SupplyRequestItem(Base, UUIDMixin):
    __tablename__ = "supply_request_items"
    __table_args__ = (
        UniqueConstraint("supply_request_id", "part_id", name="uq_sr_item_request_part"),
        CheckConstraint("quantity > 0", name="ck_sr_item_quantity_positive"),
    )

    supply_request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("supply_requests.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("parts.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    request: Mapped["SupplyRequest"] = relationship(back_populates="items")
    part: Mapped["Part"] = relationship(lazy="selectin")
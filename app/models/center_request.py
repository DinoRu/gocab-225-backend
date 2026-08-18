import uuid
from datetime import date, datetime

from sqlalchemy import (
    String, Text, Date, DateTime, Integer, Boolean, ForeignKey,
    UniqueConstraint, CheckConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDMixin, TimestampMixin


class CenterRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "center_requests"
    __table_args__ = (
        UniqueConstraint("request_number", name="uq_center_requests_number"),
        CheckConstraint("status IN ('nouvelle','preparee','envoyee')", name="ck_center_requests_status"),
    )

    request_number: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    vehicle_brand: Mapped[str] = mapped_column(String(100), nullable=False)
    vehicle_model: Mapped[str] = mapped_column(String(100), nullable=False)
    plate_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    request_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="nouvelle", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    prepared_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    creator: Mapped["User | None"] = relationship(lazy="selectin")
    items: Mapped[list["CenterRequestItem"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class CenterRequestItem(Base, UUIDMixin):
    __tablename__ = "center_request_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_center_item_qty_positive"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("center_requests.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    part_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("parts.id", ondelete="SET NULL"),
        nullable=True,
    )
    designation: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prepared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    request: Mapped["CenterRequest"] = relationship(back_populates="items")
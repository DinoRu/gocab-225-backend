import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    String, Text, Date, DateTime, Numeric, ForeignKey,
    UniqueConstraint, CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDMixin, TimestampMixin


class PaymentRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "payment_requests"
    __table_args__ = (
        UniqueConstraint("request_number", name="uq_payment_requests_number"),
        CheckConstraint("amount > 0", name="ck_payment_requests_amount_positive"),
        CheckConstraint(
            "priority IN ('low','normal','high','urgent')", name="ck_payment_requests_priority"
        ),
        CheckConstraint("status IN ('to_pay','paid')", name="ck_payment_requests_status"),
    )
    request_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    request_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    link: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    odoo_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="to_pay", nullable=False, index=True)

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    supplier: Mapped["Supplier"] = relationship(lazy="selectin")
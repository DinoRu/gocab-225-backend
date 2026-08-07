import uuid
from datetime import datetime, date

from sqlalchemy import String, ForeignKey, Date, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class PurchaseOrder(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "purchase_orders"
    
    order_number: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    supplier: Mapped["Supplier"] = relationship(back_populates="orders")
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    
    


import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Integer, Numeric, ForeignKey, UniqueConstraint, CheckConstraint, func
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDMixin


class PurchaseOrderItem(Base, UUIDMixin):  # pas de updated_at ici (ligne immuable)
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        UniqueConstraint("purchase_order_id", "part_id", name="uq_order_item_order_part"),
        CheckConstraint("quantity > 0", name="ck_order_item_quantity_positive"),
    )

    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("parts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)  # FCFA
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    order: Mapped["PurchaseOrder"] = relationship(back_populates="items")
    part: Mapped["Part"] = relationship(back_populates="order_items")
import uuid
from datetime import datetime

from sqlalchemy import Integer, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDMixin


class SupplyLineConsumption(Base, UUIDMixin):
    __tablename__ = "supply_line_consumptions"
    __table_args__ = (
        UniqueConstraint(
            "supply_request_item_id", "purchase_request_item_id",
            name="uq_slc_supply_purchase",
        ),
        CheckConstraint("quantity > 0", name="ck_slc_quantity_positive"),
    )

    supply_request_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("supply_request_items.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    purchase_request_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("purchase_request_items.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
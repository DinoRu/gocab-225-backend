import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.database.base import Base, TimestampMixin, UUIDMixin
from app.models.associations import part_vehicle_models

class Part(Base, TimestampMixin, UUIDMixin):
    
    __tablename__ = "parts"
    
    reference: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    designation: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # vehicle_model_id: Mapped[uuid.UUID] = mapped_column(
    #     PGUUID(as_uuid=True), ForeignKey("vehicle_models.id", ondelete="RESTRICT"), 
    #     nullable=False, index=True
    #         )
    category: Mapped[str | None] = mapped_column(String(120), nullable=False)
    vehicle_models: Mapped[list["VehicleModel"]] = relationship(
        secondary=part_vehicle_models,
        back_populates="parts",
        lazy='selectin',
        order_by="VehicleModel.name"
    )
    order_items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates='part'
    )
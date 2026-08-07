import uuid
from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDMixin, TimestampMixin
from app.models.associations import part_vehicle_models


class VehicleModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "vehicle_models"
    __table_args__ = (
        UniqueConstraint("brand_id", "name", name="uq_vehicle_models_brand_name"),
    )

    brand_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("vehicle_brands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    brand: Mapped["VehicleBrand"] = relationship(back_populates="models")
    parts: Mapped[list["Part"]] = relationship(
        secondary=part_vehicle_models,
        back_populates="vehicle_models")
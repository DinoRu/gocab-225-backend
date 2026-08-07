from app.database.base import TimestampMixin, Base, UUIDMixin
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class VehicleBrand(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "vehicle_brands"
    
    
    name: Mapped[str] = mapped_column(
        String(120), unique=True, nullable=True, index=True 
    )
    
    models: Mapped[list["VehicleModel"]] = relationship(
        back_populates="brand", cascade="all, delete-orphan"
    )
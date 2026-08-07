
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDMixin, TimestampMixin


class Supplier(Base, UUIDMixin, TimestampMixin):
    __tablename__ = 'suppliers'
    
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, 
        index=True
    )
    phone: Mapped[str] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    orders: Mapped[list["PurchaseOrder"]] = relationship(
        back_populates="supplier"
    )
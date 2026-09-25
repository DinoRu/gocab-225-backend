import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    String, Text, Date, Numeric, ForeignKey,
    UniqueConstraint, CheckConstraint, func, Index, text
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDMixin, TimestampMixin



class TariffSupplier(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tariff_suppliers"
    __table_args__ = (UniqueConstraint("name", name="uq_tariff_suppliers_name"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TariffArticle(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tariff_articles"
    __table_args__ = (
        UniqueConstraint("reference", name="uq_tariff_articles_reference"),
    )

    reference: Mapped[str] = mapped_column(String(100), nullable=False)
    designation: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TariffPrice(Base, UUIDMixin):
    __tablename__ = "tariff_prices"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_tariff_price_nonneg"),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tariff_articles.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tariff_suppliers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    article: Mapped["TariffArticle"] = relationship(lazy="selectin")
    supplier: Mapped["TariffSupplier"] = relationship(lazy="selectin")
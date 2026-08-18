import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    String, Text, Date, Integer, Numeric, ForeignKey,
    UniqueConstraint, CheckConstraint, func
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDMixin, TimestampMixin


class SalesClient(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sales_clients"
    __table_args__ = (UniqueConstraint("name", name="uq_sales_clients_name"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class SalesProduct(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sales_products"

    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    designation: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    default_purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    default_sale_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class SalesOrder(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sales_orders"
    __table_args__ = (UniqueConstraint("sale_number", name="uq_sales_orders_number"),)

    sale_number: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sales_clients.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    sale_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    client: Mapped["SalesClient"] = relationship(lazy="selectin")
    items: Mapped[list["SalesOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan",
        lazy="selectin",
    )


class SalesOrderItem(Base, UUIDMixin):
    __tablename__ = "sales_order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sales_item_qty_positive"),
        CheckConstraint("purchase_price >= 0", name="ck_sales_item_purchase_nonneg"),
        CheckConstraint("sale_price >= 0", name="ck_sales_item_sale_nonneg"),
    )

    sales_order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sales_products.id", ondelete="SET NULL"),
        nullable=True,
    )
    designation: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    order: Mapped["SalesOrder"] = relationship(back_populates="items")
    
    
class SalesPayment(Base, UUIDMixin):
    __tablename__ = "sales_payments"
    __table_args__ = (
        UniqueConstraint("payment_number", name="uq_sales_payments_number"),
        CheckConstraint("amount > 0", name="ck_sales_payment_amount_positive"),
    )

    payment_number: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sales_clients.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    client: Mapped["SalesClient"] = relationship(lazy="selectin")
    allocations: Mapped[list["SalesPaymentAllocation"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan", lazy="selectin"
    )


class SalesPaymentAllocation(Base, UUIDMixin):
    __tablename__ = "sales_payment_allocations"
    __table_args__ = (
        UniqueConstraint("payment_id", "sales_order_id", name="uq_sales_alloc_payment_order"),
        CheckConstraint("amount > 0", name="ck_sales_alloc_amount_positive"),
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sales_payments.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sales_order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    payment: Mapped["SalesPayment"] = relationship(back_populates="allocations")
    
    
class SalesProforma(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sales_proformas"
    __table_args__ = (
        UniqueConstraint("proforma_number", name="uq_sales_proformas_number"),
        CheckConstraint("status IN ('en_cours','convertie')", name="ck_sales_proforma_status"),
    )

    proforma_number: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sales_clients.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    proforma_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="en_cours", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    converted_sale_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sales_orders.id", ondelete="SET NULL"),
        nullable=True,
    )

    client: Mapped["SalesClient"] = relationship(lazy="selectin")
    items: Mapped[list["SalesProformaItem"]] = relationship(
        back_populates="proforma", cascade="all, delete-orphan"
    )


class SalesProformaItem(Base, UUIDMixin):
    __tablename__ = "sales_proforma_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sales_proforma_item_qty_positive"),
        CheckConstraint("sale_price >= 0", name="ck_sales_proforma_item_price_nonneg"),
    )

    proforma_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sales_proformas.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sales_products.id", ondelete="SET NULL"),
        nullable=True,
    )
    designation: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    proforma: Mapped["SalesProforma"] = relationship(back_populates="items")
from datetime import date as date_type, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import constraint_name
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.tax import vat_amount, ttc_amount
from app.models.sales import SalesOrder, SalesInvoice, SalesInvoiceItem

_MAX_RETRIES = 5


def _serialize(inv: SalesInvoice, sale_number: str | None, diverged: bool) -> dict:
    return {
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "sales_order_id": inv.sales_order_id,
        "sale_number": sale_number,
        "client_id": inv.client_id,
        "client_name": inv.client_name,
        "invoice_date": inv.invoice_date,
        "vat_applicable": inv.vat_applicable,
        "total_ht": inv.total_ht,
        "vat_amount": inv.vat_amount,
        "total_ttc": inv.total_ttc,
        "notes": inv.notes,
        "items": [
            {
                "id": it.id, "designation": it.designation, "quantity": it.quantity,
                "unit": it.unit, "sale_price": it.sale_price, "line_total": it.line_total,
            }
            for it in sorted(inv.items, key=lambda x: x.designation)
        ],
        "diverged": diverged,
        "created_at": inv.created_at,
    }


class SalesInvoiceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _load(self, invoice_id: UUID) -> SalesInvoice:
        inv = await self.session.scalar(
            select(SalesInvoice).where(SalesInvoice.id == invoice_id)
            .options(selectinload(SalesInvoice.items))
        )
        if inv is None:
            raise NotFoundError(f"Facture {invoice_id} introuvable.")
        return inv

    async def _diverged(self, inv: SalesInvoice) -> tuple[bool, str | None]:
        """La vente a-t-elle changé depuis l'émission ? Renvoie (diverged, sale_number)."""
        if inv.sales_order_id is None:
            return (False, None)
        so = await self.session.get(SalesOrder, inv.sales_order_id)
        if so is None:
            return (False, None)   # vente supprimée : la facture reste autonome
        # la vente a été modifiée après la capture → divergence
        diverged = so.updated_at is not None and so.updated_at > inv.sale_snapshot_at
        return (diverged, so.sale_number)

    async def get_detail(self, invoice_id: UUID) -> dict:
        inv = await self._load(invoice_id)
        diverged, sale_number = await self._diverged(inv)
        return _serialize(inv, sale_number, diverged)

    async def get_by_order(self, order_id: UUID) -> dict | None:
        inv = await self.session.scalar(
            select(SalesInvoice).where(SalesInvoice.sales_order_id == order_id)
            .options(selectinload(SalesInvoice.items))
        )
        if inv is None:
            return None
        diverged, sale_number = await self._diverged(inv)
        return _serialize(inv, sale_number, diverged)

    async def issue(self, order_id: UUID) -> dict:
        """Émet la facture d'une vente (une seule fois). Copie le contenu figé."""
        so = await self.session.scalar(
            select(SalesOrder).where(SalesOrder.id == order_id)
            .options(selectinload(SalesOrder.items), selectinload(SalesOrder.client))
        )
        if so is None:
            raise NotFoundError(f"Vente {order_id} introuvable.")

        # déjà facturée ?
        existing = await self.session.scalar(
            select(SalesInvoice.id).where(SalesInvoice.sales_order_id == order_id)
        )
        if existing is not None:
            raise BusinessRuleError("Cette vente a déjà une facture. Vous pouvez la re-télécharger.")

        if not so.items:
            raise BusinessRuleError("Impossible de facturer une vente sans ligne.")

        total_ht = sum((it.sale_price * it.quantity for it in so.items), Decimal("0"))
        tva = vat_amount(total_ht) if so.vat_applicable else Decimal("0")
        ttc = total_ht + tva

        last_exc = None
        for _ in range(_MAX_RETRIES):
            number = await self._next_number(date_type.today().year)
            inv = SalesInvoice(
                invoice_number=number,
                sales_order_id=so.id,
                client_id=so.client_id,
                client_name=so.client.name,
                invoice_date=date_type.today(),
                vat_applicable=so.vat_applicable,
                total_ht=total_ht,
                vat_amount=tva,
                total_ttc=ttc,
                notes=so.notes,
                sale_snapshot_at=datetime.utcnow(),
                items=[
                    SalesInvoiceItem(
                        designation=it.designation,
                        quantity=it.quantity,
                        unit=it.unit,
                        sale_price=it.sale_price,
                        line_total=it.sale_price * it.quantity,
                    )
                    for it in so.items
                ],
            )
            self.session.add(inv)
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if constraint_name(exc) == "uq_sales_invoices_number":
                    last_exc = exc
                    continue
                if constraint_name(exc) == "uq_sales_invoices_order":
                    raise BusinessRuleError("Cette vente a déjà une facture.") from exc
                raise
            else:
                return await self.get_detail(inv.id)
        raise ConflictError("Impossible de générer un numéro de facture unique.") from last_exc

    async def _next_number(self, year: int) -> str:
        prefix = f"FAC-{year}-"
        seq = cast(func.split_part(SalesInvoice.invoice_number, "-", 3), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq), 0)).where(
                SalesInvoice.invoice_number.like(f"{prefix}%")
            )
        )
        return f"{prefix}{(last or 0) + 1:03d}"
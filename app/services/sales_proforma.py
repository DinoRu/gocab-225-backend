from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import constraint_name
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.sales import (
    SalesClient, SalesOrder, SalesOrderItem,
    SalesProforma, SalesProformaItem,
)

_MAX_RETRIES = 5


def _serialize(pf: SalesProforma, sale_number: str | None) -> dict:
    items = []
    total = Decimal("0")
    for it in pf.items:
        line_total = it.sale_price * it.quantity
        total += line_total
        items.append({
            "id": it.id,
            "product_id": it.product_id,
            "designation": it.designation,
            "quantity": it.quantity,
            "sale_price": it.sale_price,
            "line_total": line_total,
        })
    items.sort(key=lambda x: x["designation"])
    return {
        "id": pf.id,
        "proforma_number": pf.proforma_number,
        "client_id": pf.client_id,
        "client_name": pf.client.name,
        "proforma_date": pf.proforma_date,
        "status": pf.status,
        "notes": pf.notes,
        "converted_sale_id": pf.converted_sale_id,
        "converted_sale_number": sale_number,
        "items": items,
        "total": total,
        "created_at": pf.created_at,
    }


class SalesProformaService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_404(self, pf_id: UUID) -> SalesProforma:
        pf = await self.session.scalar(
            select(SalesProforma)
            .where(SalesProforma.id == pf_id)
            .options(selectinload(SalesProforma.items), selectinload(SalesProforma.client))
        )
        if pf is None:
            raise NotFoundError(f"Proforma {pf_id} introuvable.")
        return pf

    async def _detail(self, pf: SalesProforma) -> dict:
        sale_number = None
        if pf.converted_sale_id:
            sale_number = await self.session.scalar(
                select(SalesOrder.sale_number).where(SalesOrder.id == pf.converted_sale_id)
            )
        return _serialize(pf, sale_number)

    async def get_detail(self, pf_id: UUID) -> dict:
        return await self._detail(await self.get_or_404(pf_id))

    async def list_proformas(self, *, client_id, status, page, limit):
        stmt = (
            select(SalesProforma)
            .options(selectinload(SalesProforma.items), selectinload(SalesProforma.client))
            .order_by(SalesProforma.proforma_date.desc(), SalesProforma.proforma_number.desc())
        )
        if client_id:
            stmt = stmt.where(SalesProforma.client_id == client_id)
        if status:
            stmt = stmt.where(SalesProforma.status == status)
        items, total = await paginate(self.session, stmt, page=page, limit=limit)
        return [await self._detail(pf) for pf in items], total

    async def _ensure_client(self, client_id: UUID) -> None:
        if await self.session.scalar(select(SalesClient.id).where(SalesClient.id == client_id)) is None:
            raise NotFoundError(f"Client {client_id} introuvable.")

    async def create(self, data) -> dict:
        await self._ensure_client(data.client_id)
        last_exc = None
        for _ in range(_MAX_RETRIES):
            number = await self._next_number(data.proforma_date.year)
            pf = SalesProforma(
                proforma_number=number,
                client_id=data.client_id,
                proforma_date=data.proforma_date,
                status="en_cours",
                notes=data.notes,
                items=[
                    SalesProformaItem(
                        product_id=i.product_id,
                        designation=i.designation.strip(),
                        quantity=i.quantity,
                        sale_price=i.sale_price,
                    )
                    for i in data.items
                ],
            )
            self.session.add(pf)
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if constraint_name(exc) == "uq_sales_proformas_number":
                    last_exc = exc
                    continue
                raise
            else:
                return await self.get_detail(pf.id)
        raise ConflictError("Impossible de générer un numéro de proforma unique.") from last_exc

    async def update(self, pf_id: UUID, data) -> dict:
        pf = await self.get_or_404(pf_id)
        if pf.status == "convertie":
            raise BusinessRuleError("Une proforma convertie ne peut plus être modifiée.")
        fields = data.model_dump(exclude_unset=True)
        if fields.get("client_id") is not None:
            await self._ensure_client(fields["client_id"])
            pf.client_id = fields["client_id"]
        if fields.get("proforma_date") is not None:
            pf.proforma_date = fields["proforma_date"]
        if "notes" in fields:
            pf.notes = fields["notes"]
        if data.items is not None:
            pf.items.clear()
            await self.session.flush()
            for i in data.items:
                pf.items.append(SalesProformaItem(
                    product_id=i.product_id,
                    designation=i.designation.strip(),
                    quantity=i.quantity,
                    sale_price=i.sale_price,
                ))
        await self.session.commit()
        return await self.get_detail(pf_id)

    async def delete(self, pf_id: UUID) -> None:
        pf = await self.get_or_404(pf_id)
        await self.session.delete(pf)
        await self.session.commit()

    async def convert(self, pf_id: UUID, data) -> dict:
        """Crée une vente depuis la proforma. Prix de vente = ceux de la proforma,
        prix d'achat = saisis maintenant. La proforma est marquée 'convertie'."""
        pf = await self.get_or_404(pf_id)
        if pf.status == "convertie":
            raise BusinessRuleError("Cette proforma a déjà été convertie en vente.")

        # Prix d'achat fournis, indexés par ligne de proforma.
        purchase_by_item = {c.proforma_item_id: c.purchase_price for c in data.items}
        pf_item_ids = {it.id for it in pf.items}
        # chaque ligne de proforma doit avoir son prix d'achat
        missing = pf_item_ids - set(purchase_by_item.keys())
        if missing:
            raise BusinessRuleError("Chaque ligne doit avoir un prix d'achat pour la conversion.")

        # Crée la vente (réutilise la logique de numérotation VNT-).
        last_exc = None
        for _ in range(_MAX_RETRIES):
            number = await self._next_sale_number(data.sale_date.year)
            sale = SalesOrder(
                sale_number=number,
                client_id=pf.client_id,
                sale_date=data.sale_date,
                notes=f"Issue de la proforma {pf.proforma_number}",
                items=[
                    SalesOrderItem(
                        product_id=it.product_id,
                        designation=it.designation,
                        quantity=it.quantity,
                        purchase_price=purchase_by_item[it.id],
                        sale_price=it.sale_price,      # prix de vente de la proforma
                    )
                    for it in pf.items
                ],
            )
            self.session.add(sale)
            try:
                await self.session.flush()   # obtenir sale.id
                pf.status = "convertie"
                pf.converted_sale_id = sale.id
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if constraint_name(exc) == "uq_sales_orders_number":
                    last_exc = exc
                    continue
                raise
            else:
                return await self.get_detail(pf_id)
        raise ConflictError("Impossible de générer un numéro de vente unique.") from last_exc

    async def _next_number(self, year: int) -> str:
        prefix = f"PRO-{year}-"
        seq = cast(func.split_part(SalesProforma.proforma_number, "-", 3), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq), 0)).where(
                SalesProforma.proforma_number.like(f"{prefix}%")
            )
        )
        return f"{prefix}{(last or 0) + 1:03d}"

    async def _next_sale_number(self, year: int) -> str:
        prefix = f"VNT-{year}-"
        seq = cast(func.split_part(SalesOrder.sale_number, "-", 3), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq), 0)).where(
                SalesOrder.sale_number.like(f"{prefix}%")
            )
        )
        return f"{prefix}{(last or 0) + 1:03d}"
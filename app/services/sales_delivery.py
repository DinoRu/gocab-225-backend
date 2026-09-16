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
    SalesDeliveryNote, SalesDeliveryItem,
)
from app.services._sales_delivery import delivered_by_order_item

_MAX_RETRIES = 5


def _serialize(dn: SalesDeliveryNote) -> dict:
    items = []
    total = Decimal("0")
    for it in dn.items:
        line_total = it.sale_price * it.quantity
        total += line_total
        items.append({
            "id": it.id,
            "sales_order_item_id": it.sales_order_item_id,
            "designation": it.designation,
            "quantity": it.quantity,
            "unit": it.unit,
            "sale_price": it.sale_price,
            "line_total": line_total,
        })
    items.sort(key=lambda x: x["designation"])
    return {
        "id": dn.id,
        "delivery_number": dn.delivery_number,
        "sales_order_id": dn.sales_order_id,
        "sale_number": dn.order.sale_number,
        "client_id": dn.client_id,
        "client_name": dn.client.name,
        "delivery_date": dn.delivery_date,
        "notes": dn.notes,
        "items": items,
        "total": total,
        "created_at": dn.created_at,
    }


class SalesDeliveryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_404(self, dn_id: UUID) -> SalesDeliveryNote:
        dn = await self.session.scalar(
            select(SalesDeliveryNote)
            .where(SalesDeliveryNote.id == dn_id)
            .options(
                selectinload(SalesDeliveryNote.items),
                selectinload(SalesDeliveryNote.client),
                selectinload(SalesDeliveryNote.order),
            )
        )
        if dn is None:
            raise NotFoundError(f"Bon de livraison {dn_id} introuvable.")
        return dn

    async def get_detail(self, dn_id: UUID) -> dict:
        return _serialize(await self.get_or_404(dn_id))

    async def list_deliveries(self, *, client_id, sales_order_id, page, limit):
        stmt = (
            select(SalesDeliveryNote)
            .options(
                selectinload(SalesDeliveryNote.items),
                selectinload(SalesDeliveryNote.client),
                selectinload(SalesDeliveryNote.order),
            )
            .order_by(SalesDeliveryNote.delivery_date.desc(), SalesDeliveryNote.delivery_number.desc())
        )
        if client_id:
            stmt = stmt.where(SalesDeliveryNote.client_id == client_id)
        if sales_order_id:
            stmt = stmt.where(SalesDeliveryNote.sales_order_id == sales_order_id)
        items, total = await paginate(self.session, stmt, page=page, limit=limit)
        return [_serialize(dn) for dn in items], total

    async def deliverable(self, sales_order_id: UUID) -> dict:
        """Le reste à livrer d'une vente, ligne par ligne."""
        so = await self.session.scalar(
            select(SalesOrder)
            .where(SalesOrder.id == sales_order_id)
            .options(selectinload(SalesOrder.items), selectinload(SalesOrder.client))
        )
        if so is None:
            raise NotFoundError(f"Vente {sales_order_id} introuvable.")
        delivered = await delivered_by_order_item(self.session, [it.id for it in so.items])
        lines = []
        for it in so.items:
            d = delivered.get(it.id, 0)
            rem = it.quantity - d
            lines.append({
                "sales_order_item_id": it.id,
                "designation": it.designation,
                "unit": it.unit,
                "sale_price": it.sale_price,
                "quantity_ordered": it.quantity,
                "quantity_delivered": d,
                "quantity_remaining": rem,
            })
        return {
            "sales_order_id": so.id,
            "sale_number": so.sale_number,
            "client_id": so.client_id,
            "client_name": so.client.name,
            "lines": lines,
        }

    async def create(self, data) -> dict:
        so = await self.session.scalar(
            select(SalesOrder)
            .where(SalesOrder.id == data.sales_order_id)
            .options(selectinload(SalesOrder.items))
        )
        if so is None:
            raise NotFoundError(f"Vente {data.sales_order_id} introuvable.")

        # Contrôle strict : pour chaque ligne rattachée, ne pas dépasser le reste.
        delivered = await delivered_by_order_item(self.session, [it.id for it in so.items])
        order_items = {it.id: it for it in so.items}

        clean_items = []
        for line in data.items:
            if line.quantity <= 0:
                continue
            if line.sales_order_item_id is not None:
                oi = order_items.get(line.sales_order_item_id)
                if oi is None:
                    raise BusinessRuleError("Une ligne référence une pièce qui n'appartient pas à cette vente.")
                remaining = oi.quantity - delivered.get(oi.id, 0)
                if line.quantity > remaining:
                    raise BusinessRuleError(
                        f"« {line.designation} » : livraison {line.quantity} > reste à livrer {remaining}."
                    )
            clean_items.append(line)

        if not clean_items:
            raise BusinessRuleError("Le bon de livraison doit contenir au moins une ligne à livrer.")

        last_exc = None
        for _ in range(_MAX_RETRIES):
            number = await self._next_number(data.delivery_date.year)
            dn = SalesDeliveryNote(
                delivery_number=number,
                sales_order_id=so.id,
                client_id=so.client_id,
                delivery_date=data.delivery_date,
                notes=data.notes,
                items=[
                    SalesDeliveryItem(
                        sales_order_item_id=l.sales_order_item_id,
                        designation=l.designation.strip(),
                        quantity=l.quantity,
                        unit=l.unit or "pièce",
                        sale_price=l.sale_price,
                    )
                    for l in clean_items
                ],
            )
            self.session.add(dn)
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if constraint_name(exc) == "uq_sales_delivery_number":
                    last_exc = exc
                    continue
                raise
            else:
                return await self.get_detail(dn.id)
        raise ConflictError("Impossible de générer un numéro de BL unique.") from last_exc

    async def delete(self, dn_id: UUID) -> None:
        dn = await self.get_or_404(dn_id)
        await self.session.delete(dn)   # cascade → items supprimés → quantités libérées
        await self.session.commit()

    async def _next_number(self, year: int) -> str:
        prefix = f"BL-{year}-"
        seq = cast(func.split_part(SalesDeliveryNote.delivery_number, "-", 3), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq), 0)).where(
                SalesDeliveryNote.delivery_number.like(f"{prefix}%")
            )
        )
        return f"{prefix}{(last or 0) + 1:03d}"
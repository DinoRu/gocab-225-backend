from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import constraint_name
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.sales import SalesClient, SalesProduct, SalesOrder, SalesOrderItem
from app.repositories.sales import (
    SalesClientRepository, SalesProductRepository, SalesOrderRepository,
)
from app.schemas.sales import (
    SalesClientCreate, SalesClientUpdate,
    SalesProductCreate, SalesProductUpdate,
    SalesOrderCreate, SalesOrderUpdate,
)
from app.core.tax import vat_amount, ttc_amount, VAT_RATE

_MAX_RETRIES = 5


# ======================= CLIENTS =======================
class SalesClientService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SalesClientRepository(session)

    async def list_clients(self, *, search, page, limit):
        stmt = self.repo.list_stmt(search=search)
        items, total = await paginate(self.session, stmt, page=page, limit=limit)
        return items, total

    async def get_or_404(self, client_id: UUID) -> SalesClient:
        c = await self.session.get(SalesClient, client_id)
        if c is None:
            raise NotFoundError(f"Client {client_id} introuvable.")
        return c

    async def create(self, data: SalesClientCreate) -> SalesClient:
        c = SalesClient(**data.model_dump())
        self.session.add(c)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if constraint_name(exc) == "uq_sales_clients_name":
                raise ConflictError("Un client porte déjà ce nom.") from exc
            raise
        await self.session.refresh(c)
        return c

    async def update(self, client_id: UUID, data: SalesClientUpdate) -> SalesClient:
        c = await self.get_or_404(client_id)
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(c, k, v)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if constraint_name(exc) == "uq_sales_clients_name":
                raise ConflictError("Un client porte déjà ce nom.") from exc
            raise
        await self.session.refresh(c)
        return c

    async def delete(self, client_id: UUID) -> None:
        c = await self.get_or_404(client_id)
        try:
            await self.session.delete(c)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            # RESTRICT sur sales_orders.client_id → client avec ventes non supprimable
            raise BusinessRuleError(
                "Ce client a des ventes enregistrées et ne peut pas être supprimé."
            ) from exc


# ======================= PRODUITS =======================
class SalesProductService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SalesProductRepository(session)

    async def list_products(self, *, search, page, limit):
        stmt = self.repo.list_stmt(search=search)
        return await paginate(self.session, stmt, page=page, limit=limit)

    async def get_or_404(self, product_id: UUID) -> SalesProduct:
        p = await self.session.get(SalesProduct, product_id)
        if p is None:
            raise NotFoundError(f"Produit {product_id} introuvable.")
        return p

    async def create(self, data: SalesProductCreate) -> SalesProduct:
        p = SalesProduct(**data.model_dump())
        self.session.add(p)
        await self.session.commit()
        await self.session.refresh(p)
        return p

    async def update(self, product_id: UUID, data: SalesProductUpdate) -> SalesProduct:
        p = await self.get_or_404(product_id)
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(p, k, v)
        await self.session.commit()
        await self.session.refresh(p)
        return p

    async def delete(self, product_id: UUID) -> None:
        p = await self.get_or_404(product_id)
        # SET NULL sur les lignes de vente → suppression sûre (l'historique garde la désignation)
        await self.session.delete(p)
        await self.session.commit()


# ======================= VENTES =======================
def serialize_sale(so: SalesOrder) -> dict:
    items = []
    total_sale = Decimal("0")      # HT
    total_purchase = Decimal("0")
    for it in so.items:
        line_total = it.sale_price * it.quantity
        line_purchase = it.purchase_price * it.quantity
        line_margin = line_total - line_purchase
        total_sale += line_total
        total_purchase += line_purchase
        items.append({
            "id": it.id,
            "product_id": it.product_id,
            "designation": it.designation,
            "quantity": it.quantity,
            "unit": it.unit,
            "purchase_price": it.purchase_price,
            "sale_price": it.sale_price,
            "line_total": line_total,
            "line_margin": line_margin,
        })
    items.sort(key=lambda x: x["designation"])

    tva = vat_amount(total_sale)
    ttc = total_sale + tva

    return {
        "id": so.id,
        "sale_number": so.sale_number,
        "client_id": so.client_id,
        "client_name": so.client.name,
        "sale_date": so.sale_date,
        "notes": so.notes,
        "items": items,
        "total_sale": total_sale,          # HT
        "total_purchase": total_purchase,
        "total_margin": total_sale - total_purchase,   # marge sur HT — inchangée
        "vat_rate": VAT_RATE,              # 0.18
        "vat_amount": tva,                 # TVA collectée
        "total_ttc": ttc,                  # ce que le client doit
        "created_at": so.created_at,
    }

class SalesOrderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SalesOrderRepository(session)

    async def get_or_404(self, order_id: UUID) -> SalesOrder:
        so = await self.repo.get_detail(order_id)
        if so is None:
            raise NotFoundError(f"Vente {order_id} introuvable.")
        return so

    async def get_detail(self, order_id: UUID) -> dict:
        return serialize_sale(await self.get_or_404(order_id))

    async def list_sales(self, *, search, client_id, start_date, end_date, page, limit):
        stmt = self.repo.list_stmt(
            search=search, client_id=client_id, start_date=start_date, end_date=end_date
        )
        items, total = await paginate(self.session, stmt, page=page, limit=limit)
        return [serialize_sale(so) for so in items], total

    async def _ensure_client(self, client_id: UUID) -> None:
        if await self.session.scalar(select(SalesClient.id).where(SalesClient.id == client_id)) is None:
            raise NotFoundError(f"Client {client_id} introuvable.")

    async def create(self, data: SalesOrderCreate) -> dict:
        await self._ensure_client(data.client_id)
        last_exc = None
        for _ in range(_MAX_RETRIES):
            number = await self._next_number(data.sale_date.year)
            so = SalesOrder(
                sale_number=number,
                client_id=data.client_id,
                sale_date=data.sale_date,
                notes=data.notes,
                items=[
                    SalesOrderItem(
                        product_id=i.product_id,
                        designation=i.designation.strip(),
                        quantity=i.quantity,
                        unit=i.unit,
                        purchase_price=i.purchase_price,
                        sale_price=i.sale_price,
                    )
                    for i in data.items
                ],
            )
            self.session.add(so)
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if constraint_name(exc) == "uq_sales_orders_number":
                    last_exc = exc
                    continue
                raise
            else:
                return await self.get_detail(so.id)
        raise ConflictError("Impossible de générer un numéro de vente unique.") from last_exc

    async def update(self, order_id: UUID, data: SalesOrderUpdate) -> dict:
        so = await self.repo.get_detail(order_id)
        if so is None:
            raise NotFoundError(f"Vente {order_id} introuvable.")

        fields = data.model_dump(exclude_unset=True)
        if fields.get("client_id") is not None:
            await self._ensure_client(fields["client_id"])
            so.client_id = fields["client_id"]
        if fields.get("sale_date") is not None:
            so.sale_date = fields["sale_date"]
        if "notes" in fields:
            so.notes = fields["notes"]
        if data.items is not None:
            so.items.clear()
            await self.session.flush()
            for i in data.items:
                so.items.append(SalesOrderItem(
                    product_id=i.product_id,
                    designation=i.designation.strip(),
                    quantity=i.quantity,
                    unit=i.unit,
                    purchase_price=i.purchase_price,
                    sale_price=i.sale_price,
                ))
        await self.session.commit()
        return await self.get_detail(order_id)

    async def delete(self, order_id: UUID) -> None:
        so = await self.repo.get_detail(order_id)
        if so is None:
            raise NotFoundError(f"Vente {order_id} introuvable.")
        await self.session.delete(so)
        await self.session.commit()

    async def _next_number(self, year: int) -> str:
        prefix = f"VNT-{year}-"
        seq = cast(func.split_part(SalesOrder.sale_number, "-", 3), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq), 0)).where(
                SalesOrder.sale_number.like(f"{prefix}%")
            )
        )
        return f"{prefix}{(last or 0) + 1:03d}"
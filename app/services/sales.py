from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import constraint_name
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.helpers import ensure_catalog_product
from app.core.pagination import paginate
from app.models.sales import SalesClient, SalesProduct, SalesOrder, SalesOrderItem, SalesProforma, SalesProformaItem
from app.repositories.sales import (
    SalesClientRepository, SalesProductRepository, SalesOrderRepository,
)
from app.schemas.sales import (
    SalesClientCreate, SalesClientUpdate,
    SalesProductCreate, SalesProductUpdate,
    SalesOrderCreate, SalesOrderUpdate,
)
from app.services._sales_delivery import delivered_by_order_item
from app.services._sales_balance import allocated_by_order
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


async def compute_delivery_status(session, so: SalesOrder) -> str:
    """non_livree / partiellement_livree / livree — calculé depuis les BL."""
    item_ids = [it.id for it in so.items]
    delivered = await delivered_by_order_item(session, item_ids)
    total_ordered = sum(it.quantity for it in so.items)
    total_delivered = sum(delivered.get(it.id, 0) for it in so.items)
    if total_delivered == 0:
        return "non_livree"
    if total_delivered >= total_ordered:
        return "livree"
    return "partiellement_livree"


async def compute_payment_status(session: AsyncSession, so: SalesOrder) -> dict:
    """Statut de paiement dérivé d'une vente + reste dû (en TTC)."""
    allocated = await allocated_by_order(session, [so.id])
    paid = allocated.get(so.id, Decimal("0"))
    total_ht = sum((it.sale_price * it.quantity for it in so.items), Decimal("0"))
    total_ttc = ttc_amount(total_ht)
    remaining = total_ttc - paid
    if paid <= 0:
        status = "impayee"
    elif remaining <= 0:
        status = "payee"
    else:
        status = "partiellement_payee"
    return {"payment_status": status, "amount_paid": paid, "amount_due": remaining if remaining > 0 else Decimal("0")}


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
        so = await self.get_or_404(order_id)
        data = serialize_sale(so)
        data["delivery_status"] = await compute_delivery_status(self.session, so)
        pay = await compute_payment_status(self.session, so)
        data.update(pay)   # payment_status, amount_paid, amount_due
        return data

    async def list_sales(self, *, search, client_id, start_date, end_date, page, limit):
        stmt = self.repo.list_stmt(search=search, client_id=client_id, start_date=start_date, end_date=end_date)
        items, total = await paginate(self.session, stmt, page=page, limit=limit)

        all_item_ids = [it.id for so in items for it in so.items]
        delivered = await delivered_by_order_item(self.session, all_item_ids)
        allocated = await allocated_by_order(self.session, [so.id for so in items])

        result = []
        for so in items:
            data = serialize_sale(so)
            # livraison
            total_ordered = sum(it.quantity for it in so.items)
            total_delivered = sum(delivered.get(it.id, 0) for it in so.items)
            data["delivery_status"] = (
                "non_livrée" if total_delivered == 0
                else "livrée" if total_delivered >= total_ordered
                else "partiellement_livrée"
            )
            # paiement
            paid = allocated.get(so.id, Decimal("0"))
            total_ttc = ttc_amount(data["total_sale"])   # total_sale = HT dans serialize_sale
            remaining = total_ttc - paid
            data["payment_status"] = (
                "impayee" if paid <= 0
                else "payee" if remaining <= 0
                else "partiellement_payee"
            )
            data["amount_paid"] = paid
            data["amount_due"] = remaining if remaining > 0 else Decimal("0")
            result.append(data)
        return result, total

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
            # Enregistrement auto au catalogue pour les lignes libres cochées
            for i in data.items:
                if getattr(i, "add_to_catalog", False) and i.product_id is None:
                    await ensure_catalog_product(
                        session=self.session,
                        designation=i.designation,
                        purchase_price=i.purchase_price,
                        sale_price=i.sale_price,
                        unit=i.unit or "pièce",
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

    async def last_price_for_client(
            self, *, client_id: UUID, designation: str | None, product_id: UUID | None
        ) -> dict | None:
            """Dernier prix pratiqué à ce client pour cet article, en cherchant dans :
            - les ventes passées (prix achat + vente)
            - les proformas en cours (prix vente seulement)
            Le plus récent des deux gagne."""

            norm = " ".join(designation.lower().split()) if designation else None

            # --- Source 1 : ventes ---
            vente_stmt = (
                select(
                    SalesOrderItem.purchase_price,
                    SalesOrderItem.sale_price,
                    SalesOrder.sale_date.label("d"),
                )
                .join(SalesOrder, SalesOrder.id == SalesOrderItem.sales_order_id)
                .where(SalesOrder.client_id == client_id)
                .order_by(SalesOrder.sale_date.desc(), SalesOrder.created_at.desc())
                .limit(1)
            )
            if product_id is not None:
                vente_stmt = vente_stmt.where(SalesOrderItem.product_id == product_id)
            elif norm:
                vente_stmt = vente_stmt.where(func.lower(func.trim(SalesOrderItem.designation)) == norm)
            else:
                return None
            vente = (await self.session.execute(vente_stmt)).first()

            # --- Source 2 : proformas en cours (non converties) ---
            pf_stmt = (
                select(
                    SalesProformaItem.sale_price,
                    SalesProforma.proforma_date.label("d"),
                )
                .join(SalesProforma, SalesProforma.id == SalesProformaItem.proforma_id)
                .where(
                    SalesProforma.client_id == client_id,
                    SalesProforma.status == "en_cours",
                )
                .order_by(SalesProforma.proforma_date.desc(), SalesProforma.created_at.desc())
                .limit(1)
            )
            if product_id is not None:
                pf_stmt = pf_stmt.where(SalesProformaItem.product_id == product_id)
            elif norm:
                pf_stmt = pf_stmt.where(func.lower(func.trim(SalesProformaItem.designation)) == norm)
            pf = (await self.session.execute(pf_stmt)).first()

            # --- Choisir le plus récent ---
            if vente is None and pf is None:
                return None
            if pf is None or (vente is not None and vente.d >= pf.d):
                # la vente est plus récente (ou égale) → on a les deux prix
                return {
                    "purchase_price": vente.purchase_price,
                    "sale_price": vente.sale_price,
                    "last_sale_date": vente.d,
                    "source": "vente",
                }
            else:
                # la proforma est plus récente → seulement le prix de vente
                return {
                    "purchase_price": None,
                    "sale_price": pf.sale_price,
                    "last_sale_date": pf.d,
                    "source": "proforma",
                }
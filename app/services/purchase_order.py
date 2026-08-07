from decimal import Decimal
from uuid import UUID

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import constraint_name
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.part import Part
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.supplier import Supplier
from app.repositories.purchase_order import PurchaseOrderRepository
from app.schemas.purchase_order import PurchaseOrderCreate, PurchaseOrderUpdate

_MAX_ORDER_NUMBER_RETRIES = 5

_SORTABLE = {
    "order_date": PurchaseOrder.order_date,
    "order_number": PurchaseOrder.order_number,
    "created_at": PurchaseOrder.created_at,
}


class PurchaseOrderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PurchaseOrderRepository(session)
        
        
    # --- lecture ---

    async def get_or_404(self, order_id: UUID) -> PurchaseOrder:
        order = await self.repo.get(order_id)
        if order is None:
            raise NotFoundError(f"Commande {order_id} introuvable.")
        return order

    async def get_detail(self, order_id: UUID, hide_prices: bool = False) -> dict:
        order = await self.repo.get_detail(order_id)
        if order is None:
            raise NotFoundError(f"Commande {order_id} introuvable.")
        return self._serialize_order(order, hide_prices=hide_prices)

    async def list_orders(
        self,
        *,
        search: str | None,
        start_date=None,
        end_date=None,
        supplier_id: UUID | None,
        part_id: UUID | None,
        brand_id: UUID | None,
        vehicle_model_id: UUID | None,
        sort: str,
        page: int,
        limit: int,
        hide_prices: bool = False,
    ) -> tuple[list[dict], int]:
        stmt = self.repo.filtered_stmt(
            search=search,
            start_date=start_date,
            end_date=end_date,
            supplier_id=supplier_id,
            part_id=part_id,
            brand_id=brand_id,
            vehicle_model_id=vehicle_model_id,
        )
        stmt = self._apply_sort(stmt, sort)
        items, total = await paginate(self.session, stmt, page=page, limit=limit)
        return [self._serialize_order(o, hide_prices=hide_prices) for o in items], total

    # --- écriture ---

    async def create(self, data: PurchaseOrderCreate) -> dict:
        await self._ensure_supplier_exists(data.supplier_id)
        await self._ensure_parts_exist([i.part_id for i in data.items])

        last_exc: IntegrityError | None = None
        for _ in range(_MAX_ORDER_NUMBER_RETRIES):
            order_number = await self._next_order_number(data.order_date.year)
            order = PurchaseOrder(
                order_number=order_number,
                supplier_id=data.supplier_id,
                order_date=data.order_date,
                notes=data.notes,
                items=[
                    PurchaseOrderItem(
                        part_id=i.part_id, quantity=i.quantity, unit_price=i.unit_price
                    )
                    for i in data.items
                ],
            )
            self.session.add(order)
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if constraint_name(exc) == "uq_purchase_orders_order_number":
                    last_exc = exc
                    continue  # collision de numéro → recalcul + nouvel essai
                self._translate_item_integrity(exc)
                raise
            else:
                return await self.get_detail(order.id)

        raise ConflictError(
            "Impossible de générer un numéro de commande unique après plusieurs tentatives."
        ) from last_exc

    async def update(self, order_id: UUID, data: PurchaseOrderUpdate) -> dict:
        order = await self.repo.get_with_items(order_id)
        if order is None:
            raise NotFoundError(f"Commande {order_id} introuvable.")

        fields = data.model_dump(exclude_unset=True)

        if "supplier_id" in fields and fields["supplier_id"] is not None:
            await self._ensure_supplier_exists(fields["supplier_id"])
            order.supplier_id = fields["supplier_id"]
        if "order_date" in fields and fields["order_date"] is not None:
            order.order_date = fields["order_date"]
        if "notes" in fields:                       # présent → None efface
            order.notes = fields["notes"]

        if data.items is not None:                  # remplacement intégral des lignes
            await self._ensure_parts_exist([i.part_id for i in data.items])
            order.items.clear()
            await self.session.flush()              # exécute les DELETE avant les INSERT
            for item in data.items:
                order.items.append(
                    PurchaseOrderItem(
                        part_id=item.part_id,
                        quantity=item.quantity,
                        unit_price=item.unit_price,
                    )
                )

        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            self._translate_item_integrity(exc)
            raise
        return await self.get_detail(order_id)

    async def delete(self, order_id: UUID) -> None:
        # On charge les items pour que la cascade ORM les supprime sans lazy-load async.
        order = await self.repo.get_with_items(order_id)
        if order is None:
            raise NotFoundError(f"Commande {order_id} introuvable.")
        await self.session.delete(order)
        await self.session.commit()

    # --- internes ---

    async def _next_order_number(self, year: int) -> str:
        """Prochain numéro pour l'année, basé sur le MAX réel du suffixe.
        Robuste aux suppressions (hard delete) et aux paddings > 999."""
        prefix = f"CMD-{year}-"
        seq_expr = cast(func.split_part(PurchaseOrder.order_number, "-", 3), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq_expr), 0)).where(
                PurchaseOrder.order_number.like(f"{prefix}%")
            )
        )
        return f"{prefix}{(last or 0) + 1:03d}"

    async def _ensure_supplier_exists(self, supplier_id: UUID) -> None:
        exists = await self.session.scalar(
            select(Supplier.id).where(Supplier.id == supplier_id)
        )
        if exists is None:
            raise NotFoundError(f"Fournisseur {supplier_id} introuvable.")

    async def _ensure_parts_exist(self, part_ids: list[UUID]) -> None:
        unique_ids = set(part_ids)
        found = set(
            await self.session.scalars(select(Part.id).where(Part.id.in_(unique_ids)))
        )
        missing = unique_ids - found
        if missing:
            listed = ", ".join(str(m) for m in missing)
            raise NotFoundError(f"Pièce(s) introuvable(s) : {listed}")

    def _apply_sort(self, stmt, sort: str):
        field = sort.lstrip("-")
        col = _SORTABLE.get(field)
        if col is None:
            allowed = ", ".join(_SORTABLE)
            raise BusinessRuleError(
                f"Tri non supporté : « {field} ». Champs autorisés : {allowed}."
            )
        direction = col.desc() if sort.startswith("-") else col.asc()
        # Tri secondaire déterministe.
        return stmt.order_by(direction, PurchaseOrder.order_number.desc())

    def _translate_item_integrity(self, exc: IntegrityError) -> None:
        """Traduit les violations de contraintes sur les lignes. Ne lève rien si
        la contrainte n'est pas reconnue (le caller re-raise)."""
        cn = constraint_name(exc)
        if cn == "uq_order_item_order_part":
            raise ConflictError(
                "Une même pièce ne peut apparaître qu'une fois dans la commande."
            ) from exc
        if cn == "ck_order_item_quantity_positive":
            raise BusinessRuleError("La quantité doit être supérieure à zéro.") from exc
        if cn and cn.endswith("part_id_fkey"):
            raise NotFoundError("Pièce introuvable.") from exc
        if cn and cn.endswith("supplier_id_fkey"):
            raise NotFoundError("Fournisseur introuvable.") from exc

    @staticmethod
    def _serialize(order: PurchaseOrder) -> dict:
        items: list[dict] = []
        total = Decimal("0")
        has_price = False
        for it in order.items:
            line_total = None
            if it.unit_price is not None:
                line_total = it.unit_price * it.quantity
                total += line_total
                has_price = True
            items.append(
                {
                    "id": it.id,
                    "part_id": it.part_id,
                    "reference": it.part.reference,
                    "designation": it.part.designation,
                    "quantity": it.quantity,
                    "unit_price": it.unit_price,
                    "line_total": line_total,
                }
            )
        items.sort(key=lambda x: x["reference"])
        return {
            "id": order.id,
            "order_number": order.order_number,
            "order_date": order.order_date,
            "supplier_id": order.supplier_id,
            "supplier_name": order.supplier.name,
            "notes": order.notes,
            "items": items,
            "total_amount": total if has_price else None,
            "created_at": order.created_at,
        }
    
    @staticmethod
    def _serialize_order(
        order: PurchaseOrder,
        *,
        hide_prices: bool = False,
    ) -> dict:
        items: list[dict] = []
        total = Decimal("0")
        has_price = False

        for it in order.items:
            line_total = None

            if not hide_prices and it.unit_price is not None:
                line_total = it.unit_price * it.quantity
                total += line_total
                has_price = True

            item = {
                "id": it.id,
                "part_id": it.part_id,
                "reference": it.part.reference,
                "designation": it.part.designation,
                "quantity": it.quantity,
                "unit_price": None if hide_prices else it.unit_price,
                "line_total": None if hide_prices else line_total,
            }

            items.append(item)

        items.sort(key=lambda item: item["reference"])

        return {
            "id": order.id,
            "order_number": order.order_number,
            "order_date": order.order_date,
            "supplier_id": order.supplier_id,
            "supplier_name": order.supplier.name,
            "notes": order.notes,
            "items": items,
            "total_amount": (
                None
                if hide_prices or not has_price
                else total
            ),
            "created_at": order.created_at,
        }
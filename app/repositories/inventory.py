from datetime import date
from uuid import UUID

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import selectinload

from app.models.inventory import InventoryCount, InventoryCountItem
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.repositories.base import BaseRepository


class InventoryRepository(BaseRepository[InventoryCount]):
    model = InventoryCount

    def _eager(self, stmt: Select) -> Select:
        return stmt.options(
            selectinload(InventoryCount.items).selectinload(InventoryCountItem.part)
        )

    async def get_detail(self, count_id: UUID) -> InventoryCount | None:
        return await self.session.scalar(
            self._eager(select(InventoryCount).where(InventoryCount.id == count_id))
        )

    async def get_with_items(self, count_id: UUID) -> InventoryCount | None:
        return await self.session.scalar(
            select(InventoryCount)
            .where(InventoryCount.id == count_id)
            .options(selectinload(InventoryCount.items))
        )

    def list_stmt(self, *, search, start_date, end_date) -> Select:
        stmt = self._eager(select(InventoryCount))
        if search:
            stmt = stmt.where(InventoryCount.count_number.ilike(f"%{search.strip()}%"))
        if start_date is not None:
            stmt = stmt.where(InventoryCount.count_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(InventoryCount.count_date <= end_date)
        return stmt.order_by(InventoryCount.count_date.desc(), InventoryCount.count_number.desc())

    async def previous_count_item(
        self, part_id: UUID, *, before_date: date, exclude_count_id: UUID
    ) -> tuple[int, date] | None:
        """Dernier comptage de CETTE pièce strictement avant le comptage courant.
        On ordonne par (date, count_number) pour un départage déterministe
        quand deux comptages tombent le même jour."""
        stmt = (
            select(InventoryCountItem.counted_quantity, InventoryCount.count_date)
            .join(InventoryCount, InventoryCount.id == InventoryCountItem.inventory_count_id)
            .where(
                InventoryCountItem.part_id == part_id,
                InventoryCount.id != exclude_count_id,
                InventoryCount.count_date <= before_date,
            )
            .order_by(InventoryCount.count_date.desc(), InventoryCount.count_number.desc())
            .limit(1)
        )
        row = (await self.session.execute(stmt)).first()
        if row is None:
            return None
        return int(row.counted_quantity), row.count_date

    async def entries_between(
        self, part_id: UUID, *, after_date: date, up_to_date: date
    ) -> int:
        """Somme des quantités commandées pour la pièce sur ]after_date, up_to_date].
        Borne gauche exclusive (déjà comptée dans le stock précédent),
        borne droite inclusive (reçue avant/le jour du comptage courant)."""
        stmt = (
            select(func.coalesce(func.sum(PurchaseOrderItem.quantity), 0))
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
            .where(
                PurchaseOrderItem.part_id == part_id,
                PurchaseOrder.order_date > after_date,
                PurchaseOrder.order_date <= up_to_date,
            )
        )
        return int(await self.session.scalar(stmt) or 0)

    async def part_history(self, part_id: UUID) -> list[InventoryCountItem]:
        """Tous les comptages d'une pièce, du plus ancien au plus récent."""
        stmt = (
            select(InventoryCountItem)
            .join(InventoryCount, InventoryCount.id == InventoryCountItem.inventory_count_id)
            .where(InventoryCountItem.part_id == part_id)
            .order_by(InventoryCount.count_date.asc(), InventoryCount.count_number.asc())
            .options(selectinload(InventoryCountItem.count))
        )
        return list(await self.session.scalars(stmt))
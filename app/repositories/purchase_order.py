from datetime import date
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from app.core.search import escape_like
from app.models.part import Part
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.vehicle_model import VehicleModel
from app.repositories.base import BaseRepository


class PurchaseOrderRepository(BaseRepository[PurchaseOrder]):
    model = PurchaseOrder

    def _eager(self, stmt: Select) -> Select:
        return stmt.options(
            selectinload(PurchaseOrder.supplier),
            selectinload(PurchaseOrder.items).selectinload(PurchaseOrderItem.part),
        )

    async def get_detail(self, order_id: UUID) -> PurchaseOrder | None:
        return await self.session.scalar(
            self._eager(select(PurchaseOrder).where(PurchaseOrder.id == order_id))
        )

    async def get_with_items(self, order_id: UUID) -> PurchaseOrder | None:
        """Charge les items (indispensable pour un remplacement ou une suppression
        en cascade sans lazy-load async)."""
        return await self.session.scalar(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == order_id)
            .options(selectinload(PurchaseOrder.items))
        )

    def filtered_stmt(
        self,
        *,
        search: str | None,
        start_date: date | None,
        end_date: date | None,
        supplier_id: UUID | None,
        part_id: UUID | None,
        brand_id: UUID | None,
        vehicle_model_id: UUID | None,
    ) -> Select:
        stmt = self._eager(select(PurchaseOrder))

        if search:
            like = f"%{escape_like(search.strip())}%"
            stmt = stmt.where(PurchaseOrder.order_number.ilike(like, escape="\\"))
        if start_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date >= start_date)   # inclusif
        if end_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date <= end_date)     # inclusif
        if supplier_id is not None:
            stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)

        # Commandes contenant au moins une ligne satisfaisant le critère (EXISTS).
        if part_id is not None:
            stmt = stmt.where(
                PurchaseOrder.items.any(PurchaseOrderItem.part_id == part_id)
            )
        if vehicle_model_id is not None:
            stmt = stmt.where(
                PurchaseOrder.items.any(
                    PurchaseOrderItem.part.has(Part.vehicle_model_id == vehicle_model_id)
                )
            )
        if brand_id is not None:
            stmt = stmt.where(
                PurchaseOrder.items.any(
                    PurchaseOrderItem.part.has(
                        Part.vehicle_model.has(VehicleModel.brand_id == brand_id)
                    )
                )
            )

        return stmt
from datetime import date
from uuid import UUID

from dateutil.relativedelta import relativedelta
from sqlalchemy import Row, exists, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.associations import part_vehicle_models
from app.models.part import Part
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.vehicle_brand import VehicleBrand
from app.models.vehicle_model import VehicleModel


# --- Helpers partagés (réutilisés par le dashboard) ---

def models_label_subquery():
    """Libellé « Marque Modèle, ... » corrélé à Part, 'Universel' si aucun lien."""
    return (
        select(
            func.coalesce(
                func.string_agg(
                    VehicleBrand.name + literal(" ") + VehicleModel.name, literal(", ")
                ),
                literal("Universel"),
            )
        )
        .select_from(part_vehicle_models)
        .join(VehicleModel, VehicleModel.id == part_vehicle_models.c.vehicle_model_id)
        .join(VehicleBrand, VehicleBrand.id == VehicleModel.brand_id)
        .where(part_vehicle_models.c.part_id == Part.id)
        .correlate(Part)
        .scalar_subquery()
    )


def brand_exists(brand_id: UUID):
    return exists(
        select(1)
        .select_from(part_vehicle_models)
        .join(VehicleModel, VehicleModel.id == part_vehicle_models.c.vehicle_model_id)
        .where(part_vehicle_models.c.part_id == Part.id)
        .where(VehicleModel.brand_id == brand_id)
        .correlate(Part)
    )


def model_exists(model_id: UUID):
    return exists(
        select(1)
        .select_from(part_vehicle_models)
        .where(part_vehicle_models.c.part_id == Part.id)
        .where(part_vehicle_models.c.vehicle_model_id == model_id)
        .correlate(Part)
    )


class StatisticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def parts_stats(
        self, *, start_date, end_date, part_id, supplier_id, brand_id, vehicle_model_id
    ) -> list[Row]:
        total = func.sum(PurchaseOrderItem.quantity)
        stmt = (
            select(
                Part.id.label("part_id"),
                Part.reference,
                Part.designation,
                models_label_subquery().label("models_label"),
                total.label("total_quantity_ordered"),
            )
            .select_from(PurchaseOrderItem)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
            .join(Part, Part.id == PurchaseOrderItem.part_id)
        )
        if start_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date <= end_date)
        if part_id is not None:
            stmt = stmt.where(Part.id == part_id)
        if supplier_id is not None:
            stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
        if brand_id is not None:
            stmt = stmt.where(brand_exists(brand_id))          # EXISTS → pas de fanout
        if vehicle_model_id is not None:
            stmt = stmt.where(model_exists(vehicle_model_id))
        stmt = stmt.group_by(Part.id, Part.reference, Part.designation).order_by(
            total.desc(), Part.designation
        )
        return (await self.session.execute(stmt)).all()

    async def part_total(self, part_id, *, start_date, end_date) -> int:
        stmt = (
            select(func.coalesce(func.sum(PurchaseOrderItem.quantity), 0))
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
            .where(PurchaseOrderItem.part_id == part_id)
        )
        if start_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date <= end_date)
        return int(await self.session.scalar(stmt) or 0)

    async def part_summary(self, part_id) -> Row:
        today = date.today()

        def window(months: int):
            floor = today - relativedelta(months=months)
            return func.coalesce(
                func.sum(PurchaseOrderItem.quantity).filter(PurchaseOrder.order_date >= floor), 0
            )

        stmt = (
            select(
                window(3).label("last_3_months"),
                window(6).label("last_6_months"),
                window(12).label("last_12_months"),
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
            .where(PurchaseOrderItem.part_id == part_id)
        )
        return (await self.session.execute(stmt)).one()
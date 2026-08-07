from uuid import UUID

from sqlalchemy import Row, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.associations import part_vehicle_models
from app.models.part import Part
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.supplier import Supplier
from app.models.vehicle_brand import VehicleBrand
from app.models.vehicle_model import VehicleModel
from app.repositories.statistics import brand_exists, model_exists, models_label_subquery

_TOP = 10


def _base(stmt):
    """item -> order -> part (sans modèle : évite tout fanout)."""
    return (
        stmt.select_from(PurchaseOrderItem)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .join(Part, Part.id == PurchaseOrderItem.part_id)
    )


def _scope(stmt, *, start_date, end_date, brand_id, vehicle_model_id):
    if start_date is not None:
        stmt = stmt.where(PurchaseOrder.order_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(PurchaseOrder.order_date <= end_date)
    if brand_id is not None:
        stmt = stmt.where(brand_exists(brand_id))
    if vehicle_model_id is not None:
        stmt = stmt.where(model_exists(vehicle_model_id))
    return stmt


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def kpis(self, **scope) -> Row:
        stmt = _base(
            select(
                func.count(func.distinct(PurchaseOrder.id)).label("total_orders"),
                func.coalesce(func.sum(PurchaseOrderItem.quantity), 0).label("total_quantity"),
                func.sum(PurchaseOrderItem.quantity * PurchaseOrderItem.unit_price).label("total_amount"),
                func.count(func.distinct(Part.id)).label("distinct_references"),
            )
        )
        return (await self.session.execute(_scope(stmt, **scope))).one()

    async def top_parts(self, **scope) -> list[Row]:
        qty = func.sum(PurchaseOrderItem.quantity)
        stmt = _base(
            select(
                Part.id.label("part_id"), Part.reference, Part.designation,
                models_label_subquery().label("models_label"), qty.label("total_quantity"),
            )
        )
        stmt = _scope(stmt, **scope).group_by(Part.id, Part.reference, Part.designation)
        return (await self.session.execute(stmt.order_by(qty.desc(), Part.designation).limit(_TOP))).all()

    async def top_suppliers(self, **scope) -> list[Row]:
        oc = func.count(func.distinct(PurchaseOrder.id))
        qty = func.sum(PurchaseOrderItem.quantity)
        stmt = _base(
            select(Supplier.id.label("supplier_id"), Supplier.name, oc.label("order_count"), qty.label("total_quantity"))
        ).join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        stmt = _scope(stmt, **scope).group_by(Supplier.id, Supplier.name)
        return (await self.session.execute(stmt.order_by(qty.desc(), Supplier.name).limit(_TOP))).all()

    async def quantity_by_month(self, **scope) -> list[Row]:
        month = func.date_trunc("month", PurchaseOrder.order_date)
        qty = func.sum(PurchaseOrderItem.quantity)
        stmt = _base(select(month.label("month"), qty.label("total_quantity")))
        stmt = _scope(stmt, **scope).group_by(month).order_by(month)
        return (await self.session.execute(stmt)).all()

    async def quantity_by_model(self, *, start_date, end_date, brand_id, vehicle_model_id) -> list[Row]:
        """FANOUT VOULU : chaque modèle compatible voit tout le volume."""
        qty = func.sum(PurchaseOrderItem.quantity)
        stmt = _base(
            select(
                VehicleModel.id.label("model_id"), VehicleModel.name,
                VehicleBrand.name.label("brand"), qty.label("total_quantity"),
            )
        ).join(
            part_vehicle_models, part_vehicle_models.c.part_id == Part.id
        ).join(
            VehicleModel, VehicleModel.id == part_vehicle_models.c.vehicle_model_id
        ).join(
            VehicleBrand, VehicleBrand.id == VehicleModel.brand_id
        )
        if start_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date <= end_date)
        if brand_id is not None:            # filtre sur la ligne fanout, pas EXISTS
            stmt = stmt.where(VehicleModel.brand_id == brand_id)
        if vehicle_model_id is not None:
            stmt = stmt.where(VehicleModel.id == vehicle_model_id)
        stmt = stmt.group_by(VehicleModel.id, VehicleModel.name, VehicleBrand.name)
        return (await self.session.execute(stmt.order_by(qty.desc()))).all()

    async def quantity_by_brand(self, *, start_date, end_date, brand_id, vehicle_model_id) -> list[Row]:
        # (part, brand) DISTINCT : une pièce compte UNE fois par marque (pas par modèle).
        pb = (
            select(
                part_vehicle_models.c.part_id.label("part_id"),
                VehicleModel.brand_id.label("brand_id"),
            )
            .select_from(part_vehicle_models)
            .join(VehicleModel, VehicleModel.id == part_vehicle_models.c.vehicle_model_id)
            .distinct()
            .subquery()
        )
        qty = func.sum(PurchaseOrderItem.quantity)
        stmt = _base(
            select(VehicleBrand.id.label("brand_id"), VehicleBrand.name, qty.label("total_quantity"))
        ).join(pb, pb.c.part_id == Part.id).join(VehicleBrand, VehicleBrand.id == pb.c.brand_id)
        if start_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date <= end_date)
        if brand_id is not None:
            stmt = stmt.where(VehicleBrand.id == brand_id)
        if vehicle_model_id is not None:
            stmt = stmt.where(model_exists(vehicle_model_id))
        stmt = stmt.group_by(VehicleBrand.id, VehicleBrand.name)
        return (await self.session.execute(stmt.order_by(qty.desc()))).all()

    async def universal_quantity(self, *, start_date, end_date) -> int:
        """Volume des pièces SANS modèle (bucket 'Universel')."""
        stmt = _base(select(func.coalesce(func.sum(PurchaseOrderItem.quantity), 0))).where(
            ~exists(
                select(1).select_from(part_vehicle_models)
                .where(part_vehicle_models.c.part_id == Part.id).correlate(Part)
            )
        )
        if start_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date <= end_date)
        return int(await self.session.scalar(stmt) or 0)
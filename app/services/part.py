from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import constraint_name
from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.part import Part
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.supplier import Supplier
from app.models.vehicle_model import VehicleModel
from app.repositories.part import PartRepository
from app.schemas.part import PartCreate, PartUpdate


def serialize_part(part: Part) -> dict:
    models = [
        {"id": m.id, "name": m.name, "brand_id": m.brand_id, "brand_name": m.brand.name}
        for m in part.vehicle_models
    ]
    return {
        "id": part.id,
        "reference": part.reference,
        "designation": part.designation,
        "category": part.category,
        "vehicle_models": models,
        "is_universal": len(models) == 0,
        "created_at": part.created_at,
        "updated_at": part.updated_at,
    }


class PartService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PartRepository(session)

    async def get_or_404(self, part_id: UUID) -> Part:
        part = await self.repo.get_with_relations(part_id)
        if part is None:
            raise NotFoundError(f"Pièce {part_id} introuvable.")
        return part

    async def get_detail(self, part_id: UUID) -> dict:
        return serialize_part(await self.get_or_404(part_id))

    async def list_parts(self, *, search, brand_id, vehicle_model_id, universal, page, limit):
        stmt = self.repo.search_stmt(
            search=search, brand_id=brand_id,
            vehicle_model_id=vehicle_model_id, universal=universal,
        )
        items, total = await paginate(self.session, stmt, page=page, limit=limit)
        return [serialize_part(p) for p in items], total

    async def create(self, data: PartCreate) -> dict:
        models = await self._resolve_models(data.vehicle_model_ids)
        part = Part(
            reference=data.reference.strip(),
            designation=data.designation.strip(),
            category=(data.category.strip() or None) if data.category else None,
        )
        part.vehicle_models = models
        self.session.add(part)
        await self._commit(reference=part.reference)
        await self.session.refresh(part)
        part = await self.repo.get_with_relations(part.id)
        return serialize_part(part)

    async def update(self, part_id: UUID, data: PartUpdate) -> dict:
        part = await self.get_or_404(part_id)
        fields = data.model_dump(exclude_unset=True)

        if fields.get("reference") is not None:
            part.reference = fields["reference"].strip()
        if fields.get("designation") is not None:
            part.designation = fields["designation"].strip()
        if "category" in fields:
            v = fields["category"]
            part.category = (v.strip() or None) if v else None
        if "vehicle_model_ids" in fields and fields["vehicle_model_ids"] is not None:
            part.vehicle_models = await self._resolve_models(fields["vehicle_model_ids"])

        await self._commit(reference=part.reference)
        await self.session.refresh(part)
        return serialize_part(part)

    async def delete(self, part_id: UUID) -> None:
        part = await self.get_or_404(part_id)
        await self.repo.delete(part)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                "Impossible de supprimer cette pièce : elle figure dans des commandes."
            ) from exc

    async def order_history(self, part_id, *, start_date, end_date, supplier_id) -> list[dict]:
        await self.get_or_404(part_id)
        stmt = (
            select(
                PurchaseOrder.order_date,
                PurchaseOrder.order_number,
                Supplier.name.label("supplier_name"),
                PurchaseOrderItem.quantity,
                PurchaseOrderItem.unit_price,
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
            .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
            .where(PurchaseOrderItem.part_id == part_id)
            .order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.order_number.desc())
        )
        if start_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(PurchaseOrder.order_date <= end_date)
        if supplier_id is not None:
            stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)

        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "order_date": r.order_date,
                "order_number": r.order_number,
                "supplier_name": r.supplier_name,
                "quantity": r.quantity,
                "unit_price": r.unit_price,
                "line_total": r.unit_price * r.quantity if r.unit_price is not None else None,
            }
            for r in rows
        ]

    async def _resolve_models(self, ids: list[UUID]) -> list[VehicleModel]:
        if not ids:
            return []
        unique = list(dict.fromkeys(ids))
        models = list(
            await self.session.scalars(select(VehicleModel).where(VehicleModel.id.in_(unique)))
        )
        missing = set(unique) - {m.id for m in models}
        if missing:
            raise NotFoundError(f"Modèle(s) introuvable(s) : {', '.join(str(m) for m in missing)}")
        return models

    async def _commit(self, *, reference: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if constraint_name(exc) in {"uq_parts_reference", "ix_parts_reference"}:
                raise ConflictError(f"La référence « {reference} » existe déjà.") from exc
            raise
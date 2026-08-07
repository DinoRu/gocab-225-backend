from uuid import UUID
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from app.models.part import Part
from app.models.vehicle_model import VehicleModel
from app.repositories.base import BaseRepository

SIMILARITY_THRESHOLD = 0.3


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class PartRepository(BaseRepository[Part]):
    model = Part

    def _eager(self, stmt: Select) -> Select:
        return stmt.options(selectinload(Part.vehicle_models).selectinload(VehicleModel.brand))

    async def get_with_relations(self, part_id: UUID) -> Part | None:
        return await self.session.scalar(self._eager(select(Part).where(Part.id == part_id)))

    def search_stmt(
        self, *, search, brand_id, vehicle_model_id, universal
    ) -> Select:
        stmt = self._eager(select(Part))

        if universal is True:
            stmt = stmt.where(~Part.vehicle_models.any())          # aucune compatibilité
        if vehicle_model_id is not None:
            stmt = stmt.where(Part.vehicle_models.any(VehicleModel.id == vehicle_model_id))
        if brand_id is not None:
            stmt = stmt.where(Part.vehicle_models.any(VehicleModel.brand_id == brand_id))

        if search:
            term = search.strip()
            like = f"%{_escape_like(term)}%"
            ref_sim = func.similarity(Part.reference, term)
            des_sim = func.similarity(Part.designation, term)
            stmt = stmt.where(
                or_(
                    Part.reference.ilike(like, escape="\\"),
                    Part.designation.ilike(like, escape="\\"),
                    ref_sim > SIMILARITY_THRESHOLD,
                    des_sim > SIMILARITY_THRESHOLD,
                )
            ).order_by(func.greatest(ref_sim, des_sim).desc(), Part.designation)
        else:
            stmt = stmt.order_by(Part.designation)

        return stmt
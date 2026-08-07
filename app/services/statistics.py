from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models.part import Part
from app.repositories.statistics import StatisticsRepository


class StatisticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = StatisticsRepository(session)

    @staticmethod
    def _validate_range(start_date, end_date) -> None:
        if start_date and end_date and start_date > end_date:
            raise BusinessRuleError(
                "La date de début doit être antérieure ou égale à la date de fin."
            )

    async def _part_or_404(self, part_id: UUID) -> Part:
        part = await self.session.get(Part, part_id)   # selectin charge modèles + marques
        if part is None:
            raise NotFoundError(f"Pièce {part_id} introuvable.")
        return part

    async def parts_stats(self, *, start_date, end_date, part_id, supplier_id, brand_id, vehicle_model_id):
        self._validate_range(start_date, end_date)
        rows = await self.repo.parts_stats(
            start_date=start_date, end_date=end_date, part_id=part_id,
            supplier_id=supplier_id, brand_id=brand_id, vehicle_model_id=vehicle_model_id,
        )
        return [
            {
                "part_id": r.part_id,
                "reference": r.reference,
                "designation": r.designation,
                "models_label": r.models_label,
                "is_universal": r.models_label == "Universel",
                "total_quantity_ordered": int(r.total_quantity_ordered),
            }
            for r in rows
        ]

    async def part_detail(self, part_id, *, start_date, end_date):
        self._validate_range(start_date, end_date)
        part = await self._part_or_404(part_id)
        total = await self.repo.part_total(part_id, start_date=start_date, end_date=end_date)
        return {
            "part_id": part.id,
            "reference": part.reference,
            "designation": part.designation,
            "vehicle_models": [
                {"id": m.id, "name": m.name, "brand_id": m.brand_id, "brand_name": m.brand.name}
                for m in part.vehicle_models
            ],
            "is_universal": len(part.vehicle_models) == 0,
            "start_date": start_date,
            "end_date": end_date,
            "total_quantity_ordered": total,
        }

    async def part_summary(self, part_id):
        part = await self._part_or_404(part_id)
        row = await self.repo.part_summary(part_id)
        label = ", ".join(f"{m.brand.name} {m.name}" for m in part.vehicle_models) or "Universel"
        return {
            "part": {"reference": part.reference, "designation": part.designation, "models": label},
            "last_3_months": int(row.last_3_months),
            "last_6_months": int(row.last_6_months),
            "last_12_months": int(row.last_12_months),
        }
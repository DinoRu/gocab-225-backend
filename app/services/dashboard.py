from datetime import date
from typing import Literal
from uuid import UUID

from dateutil.relativedelta import relativedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError
from app.repositories.dashboard import DashboardRepository

Period = Literal["3m", "6m", "12m"]
_PERIOD_MONTHS: dict[str, int] = {"3m": 3, "6m": 6, "12m": 12}
_DEFAULT_PERIOD: Period = "12m"


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = DashboardRepository(session)

    @staticmethod
    def _resolve_period(
        period: Period | None, start_date: date | None, end_date: date | None
    ) -> tuple[date | None, date | None]:
        """Dates custom prioritaires ; sinon fenêtre glissante ; défaut = 12 mois."""
        if start_date is not None or end_date is not None:
            if start_date is not None and end_date is not None and start_date > end_date:
                raise BusinessRuleError(
                    "La date de début doit être antérieure ou égale à la date de fin."
                )
            return start_date, end_date

        months = _PERIOD_MONTHS[period or _DEFAULT_PERIOD]
        today = date.today()
        return today - relativedelta(months=months), today

    async def build(
        self,
        *,
        period: Period | None,
        start_date: date | None,
        end_date: date | None,
        brand_id: UUID | None,
        vehicle_model_id: UUID | None,
    ) -> dict:
        start, end = self._resolve_period(period, start_date, end_date)
        scope = {
            "start_date": start,
            "end_date": end,
            "brand_id": brand_id,
            "vehicle_model_id": vehicle_model_id,
        }

        kpis = await self.repo.kpis(**scope)
        top_parts = await self.repo.top_parts(**scope)
        top_suppliers = await self.repo.top_suppliers(**scope)
        by_month = await self.repo.quantity_by_month(**scope)
        by_brand = await self.repo.quantity_by_brand(**scope)
        by_model = await self.repo.quantity_by_model(**scope)

        # Bucket "Universel" : seulement quand aucun filtre marque/modèle
        # (une pièce universelle n'appartient à aucune marque/modèle, donc exclue si on filtre).
        universal = 0
        if not brand_id and not vehicle_model_id:
            universal = await self.repo.universal_quantity(
                start_date=start, end_date=end
            )

        model_rows = [
            {"model_id": r.model_id, "name": r.name, "brand": r.brand,
             "total_quantity": int(r.total_quantity)}
            for r in by_model
        ]
        brand_rows = [
            {"brand_id": r.brand_id, "name": r.name, "total_quantity": int(r.total_quantity)}
            for r in by_brand
        ]
        if universal > 0:
            model_rows.append({"model_id": None, "name": "Universel", "brand": "—", "total_quantity": universal})
            brand_rows.append({"brand_id": None, "name": "Universel", "total_quantity": universal})

        return {
            "period": {"start_date": start, "end_date": end},
            "total_orders": int(kpis.total_orders),
            "total_quantity": int(kpis.total_quantity),
            "total_amount": kpis.total_amount,
            "distinct_references": int(kpis.distinct_references),
            "top_parts": [
                {"part_id": r.part_id, "reference": r.reference, "designation": r.designation,
                 "models_label": r.models_label, "total_quantity": int(r.total_quantity)}
                for r in top_parts
            ],
            "top_suppliers": [
                {"supplier_id": r.supplier_id, "name": r.name,
                 "order_count": int(r.order_count), "total_quantity": int(r.total_quantity)}
                for r in top_suppliers
            ],
            "quantity_by_month": [
                {"month": r.month.strftime("%Y-%m"), "total_quantity": int(r.total_quantity)}
                for r in by_month
            ],
            "quantity_by_brand": brand_rows,
            "quantity_by_model": model_rows,
        }
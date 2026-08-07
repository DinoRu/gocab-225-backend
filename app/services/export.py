from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.export_excel import build_parts_orders_workbook
from app.services.statistics import StatisticsService


class ExportService:
    def __init__(self, session: AsyncSession) -> None:
        self.stats = StatisticsService(session)

    @staticmethod
    def _filename(start_date: date | None, end_date: date | None) -> str:
        if start_date and end_date:
            span = f"{start_date.isoformat()}_{end_date.isoformat()}"
        elif start_date:
            span = f"depuis_{start_date.isoformat()}"
        elif end_date:
            span = f"jusqu_{end_date.isoformat()}"
        else:
            span = f"complet_{date.today().isoformat()}"
        return f"commandes_pieces_{span}.xlsx"

    async def parts_orders(
        self,
        *,
        start_date: date | None,
        end_date: date | None,
        part_id: UUID | None,
        supplier_id: UUID | None,
        brand_id: UUID | None,
        vehicle_model_id: UUID | None,
    ) -> tuple[bytes, str]:
        rows = await self.stats.parts_stats(       # valide la plage + agrège en SQL
            start_date=start_date,
            end_date=end_date,
            part_id=part_id,
            supplier_id=supplier_id,
            brand_id=brand_id,
            vehicle_model_id=vehicle_model_id,
        )
        buffer = build_parts_orders_workbook(
            rows, start_date=start_date, end_date=end_date
        )
        return buffer.getvalue(), self._filename(start_date, end_date)
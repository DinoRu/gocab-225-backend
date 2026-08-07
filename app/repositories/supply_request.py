from datetime import date
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from app.models.supply_request import SupplyRequest, SupplyRequestItem
from app.repositories.base import BaseRepository


class SupplyRequestRepository(BaseRepository[SupplyRequest]):
    model = SupplyRequest

    def _eager(self, stmt: Select) -> Select:
        return stmt.options(
            selectinload(SupplyRequest.creator),
            selectinload(SupplyRequest.items).selectinload(SupplyRequestItem.part),
        )

    async def get_detail(self, request_id: UUID) -> SupplyRequest | None:
        return await self.session.scalar(
            self._eager(select(SupplyRequest).where(SupplyRequest.id == request_id))
        )

    async def get_with_items(self, request_id: UUID) -> SupplyRequest | None:
        return await self.session.scalar(
            select(SupplyRequest)
            .where(SupplyRequest.id == request_id)
            .options(selectinload(SupplyRequest.items))
        )

    def list_stmt(self, *, search, status, created_by, start_date, end_date) -> Select:
        stmt = self._eager(select(SupplyRequest))
        if search:
            stmt = stmt.where(SupplyRequest.sr_number.ilike(f"%{search.strip()}%"))
        if status:
            stmt = stmt.where(SupplyRequest.status == status)
        if created_by is not None:            # filtre "mes besoins" pour le magazinier
            stmt = stmt.where(SupplyRequest.created_by == created_by)
        if start_date is not None:
            stmt = stmt.where(SupplyRequest.request_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(SupplyRequest.request_date <= end_date)
        return stmt.order_by(SupplyRequest.request_date.desc(), SupplyRequest.sr_number.desc())
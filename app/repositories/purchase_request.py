from datetime import date
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from app.core.search import escape_like
from app.models.purchase_request import PurchaseRequest, PurchaseRequestItem
from app.repositories.base import BaseRepository


class PurchaseRequestRepository(BaseRepository[PurchaseRequest]):
    model = PurchaseRequest

    def _eager(self, stmt: Select) -> Select:
        return stmt.options(
            selectinload(PurchaseRequest.supplier),
            selectinload(PurchaseRequest.items).selectinload(PurchaseRequestItem.part),
        )

    async def get_detail(self, request_id: UUID) -> PurchaseRequest | None:
        return await self.session.scalar(
            self._eager(select(PurchaseRequest).where(PurchaseRequest.id == request_id))
        )

    async def get_with_items(self, request_id: UUID) -> PurchaseRequest | None:
        return await self.session.scalar(
            select(PurchaseRequest)
            .where(PurchaseRequest.id == request_id)
            .options(selectinload(PurchaseRequest.items))
        )

    def list_stmt(self, *, search, status, supplier_id, start_date, end_date) -> Select:
        stmt = self._eager(select(PurchaseRequest))
        if search:
            stmt = stmt.where(PurchaseRequest.bc_number.ilike(f"%{escape_like(search.strip())}%", escape="\\"))
        if status:
            stmt = stmt.where(PurchaseRequest.status == status)
        if supplier_id:
            stmt = stmt.where(PurchaseRequest.supplier_id == supplier_id)
        if start_date is not None:
            stmt = stmt.where(PurchaseRequest.request_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(PurchaseRequest.request_date <= end_date)
        return stmt.order_by(PurchaseRequest.request_date.desc(), PurchaseRequest.bc_number.desc())
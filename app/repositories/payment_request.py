from datetime import date
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from app.core.search import escape_like
from app.models.payment_request import PaymentRequest
from app.repositories.base import BaseRepository


class PaymentRequestRepository(BaseRepository[PaymentRequest]):
    model = PaymentRequest

    def _eager(self, stmt: Select) -> Select:
        return stmt.options(
            selectinload(PaymentRequest.supplier)
        )

    async def get_detail(self, request_id: UUID) -> PaymentRequest | None:
        return await self.session.scalar(
            self._eager(select(PaymentRequest).where(PaymentRequest.id == request_id))
        )

    def filtered_stmt(
        self, *, search, status, priority, supplier_id, start_date, end_date
    ) -> Select:
        stmt = self._eager(select(PaymentRequest))
        if search:
            like = f"%{escape_like(search.strip())}%"
            stmt = stmt.where(
                PaymentRequest.title.ilike(like, escape="\\")
                | PaymentRequest.request_number.ilike(like, escape="\\")
            )
        if status:
            stmt = stmt.where(PaymentRequest.status == status)
        if priority:
            stmt = stmt.where(PaymentRequest.priority == priority)
        if supplier_id:
            stmt = stmt.where(PaymentRequest.supplier_id == supplier_id)
        if start_date is not None:
            stmt = stmt.where(PaymentRequest.request_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(PaymentRequest.request_date <= end_date)
        return stmt
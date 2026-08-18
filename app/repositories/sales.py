from datetime import date
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from app.models.sales import SalesClient, SalesProduct, SalesOrder, SalesOrderItem
from app.repositories.base import BaseRepository


class SalesClientRepository(BaseRepository[SalesClient]):
    model = SalesClient

    def list_stmt(self, *, search: str | None) -> Select:
        stmt = select(SalesClient)
        if search:
            stmt = stmt.where(SalesClient.name.ilike(f"%{search.strip()}%"))
        return stmt.order_by(SalesClient.name.asc())


class SalesProductRepository(BaseRepository[SalesProduct]):
    model = SalesProduct

    def list_stmt(self, *, search: str | None) -> Select:
        stmt = select(SalesProduct)
        if search:
            s = f"%{search.strip()}%"
            stmt = stmt.where(
                SalesProduct.designation.ilike(s) | SalesProduct.reference.ilike(s)
            )
        return stmt.order_by(SalesProduct.designation.asc())


class SalesOrderRepository(BaseRepository[SalesOrder]):
    model = SalesOrder

    def _eager(self, stmt: Select) -> Select:
        return stmt.options(
            selectinload(SalesOrder.items),
            selectinload(SalesOrder.client),
        )

    async def get_detail(self, order_id: UUID) -> SalesOrder | None:
        return await self.session.scalar(
            self._eager(select(SalesOrder).where(SalesOrder.id == order_id))
        )

    def list_stmt(self, *, search, client_id, start_date, end_date) -> Select:
        stmt = self._eager(select(SalesOrder))
        if search:
            stmt = stmt.where(SalesOrder.sale_number.ilike(f"%{search.strip()}%"))
        if client_id:
            stmt = stmt.where(SalesOrder.client_id == client_id)
        if start_date is not None:
            stmt = stmt.where(SalesOrder.sale_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(SalesOrder.sale_date <= end_date)
        return stmt.order_by(SalesOrder.sale_date.desc(), SalesOrder.sale_number.desc())
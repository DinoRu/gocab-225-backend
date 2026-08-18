from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sales import SalesPaymentAllocation


async def allocated_by_order(session: AsyncSession, order_ids: list[UUID]) -> dict[UUID, "Decimal"]:
    """Somme des imputations reçues par vente. {sales_order_id: montant_reçu}. Absent = 0."""
    if not order_ids:
        return {}
    rows = await session.execute(
        select(
            SalesPaymentAllocation.sales_order_id,
            func.coalesce(func.sum(SalesPaymentAllocation.amount), 0),
        )
        .where(SalesPaymentAllocation.sales_order_id.in_(order_ids))
        .group_by(SalesPaymentAllocation.sales_order_id)
    )
    return {oid: amt for oid, amt in rows.all()}
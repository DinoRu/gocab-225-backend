from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sales import SalesDeliveryItem


async def delivered_by_order_item(session: AsyncSession, order_item_ids: list[UUID]) -> dict[UUID, int]:
    """Quantité déjà livrée par ligne de vente. {sales_order_item_id: qté}. Absent = 0."""
    if not order_item_ids:
        return {}
    rows = await session.execute(
        select(
            SalesDeliveryItem.sales_order_item_id,
            func.coalesce(func.sum(SalesDeliveryItem.quantity), 0),
        )
        .where(SalesDeliveryItem.sales_order_item_id.in_(order_item_ids))
        .group_by(SalesDeliveryItem.sales_order_item_id)
    )
    return {oid: int(qty) for oid, qty in rows.all()}
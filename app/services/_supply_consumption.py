from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supply_consumption import SupplyLineConsumption


async def consumed_by_item(
    session: AsyncSession, supply_item_ids: list[UUID]
) -> dict[UUID, int]:
    """Somme des quantités déjà consommées (parties en bon) par ligne de besoin.
    Retourne {supply_request_item_id: quantité_consommée}. Absent = 0."""
    if not supply_item_ids:
        return {}
    rows = await session.execute(
        select(
            SupplyLineConsumption.supply_request_item_id,
            func.coalesce(func.sum(SupplyLineConsumption.quantity), 0),
        )
        .where(SupplyLineConsumption.supply_request_item_id.in_(supply_item_ids))
        .group_by(SupplyLineConsumption.supply_request_item_id)
    )
    return {sid: int(qty) for sid, qty in rows.all()}
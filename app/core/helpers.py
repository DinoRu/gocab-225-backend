from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sales import SalesProduct


async def ensure_catalog_product(
    session: AsyncSession, *, designation: str, sale_price: Decimal, unit: str,
    purchase_price: Decimal | None = None,
) -> None:
    norm = " ".join(designation.lower().split())
    existing = await session.scalar(
        select(SalesProduct.id).where(func.lower(func.trim(SalesProduct.designation)) == norm)
    )
    if existing is not None:
        return
    session.add(SalesProduct(
        designation=designation.strip(),
        default_purchase_price=purchase_price,
        default_sale_price=sale_price,
        default_unit=unit,
    ))
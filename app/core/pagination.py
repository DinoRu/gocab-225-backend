from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class Pagination:
    page: int
    limit: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


def pagination_params(
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=2000)] = 20,
) -> Pagination:
    return Pagination(page=page, limit=limit)


PaginationDep = Annotated[Pagination, Depends(pagination_params)]


async def paginate(
    session: AsyncSession, stmt: Select, *, page: int, limit: int
) -> tuple[list, int]:
    """Retourne (items, total) en 2 requêtes. Le COUNT ignore l'ORDER BY."""
    total = (
        await session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        or 0
    )
    rows = await session.scalars(stmt.limit(limit).offset((page - 1) * limit))
    return list(rows.all()), total

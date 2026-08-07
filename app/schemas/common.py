from math import ceil
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    limit: int
    pages: int


def to_page(items: list, *, total: int, page: int, limit: int) -> dict:
    """Payload prêt à être validé par response_model=Page[Schema]."""
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": ceil(total / limit) if limit else 0,
    }
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from datetime import date
from app.api.deps import SessionDep
from app.core.pagination import PaginationDep
from app.schemas.common import Page, to_page
from app.schemas.part import PartCreate, PartDetail, PartRead, PartUpdate
from app.services.part import PartService
from app.schemas.part import PartOrderHistoryRow
from app.api.auth_deps import AdminOnly, AnyUser

router = APIRouter(prefix="/parts", tags=["parts"])


def get_service(session: SessionDep) -> PartService:
    return PartService(session)


ServiceDep = Annotated[PartService, Depends(get_service)]

@router.get("", response_model=Page[PartDetail])
async def list_parts(
    service: ServiceDep,
    pagination: PaginationDep,
    _user: AnyUser,
    search: Annotated[str | None, Query(max_length=255)] = None,
    brand_id: Annotated[UUID | None, Query()] = None,
    vehicle_model_id: Annotated[UUID | None, Query()] = None,
    universal: Annotated[bool | None, Query()] = None,   # true = universelles seulement
):
    items, total = await service.list_parts(
        search=search, brand_id=brand_id, vehicle_model_id=vehicle_model_id,
        universal=universal, page=pagination.page, limit=pagination.limit,
    )
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)

@router.post("", response_model=PartDetail, status_code=status.HTTP_201_CREATED)
async def create_part(payload: PartCreate, service: ServiceDep, _user: AdminOnly):
    return await service.create(payload)


@router.get("/{part_id}", response_model=PartDetail)
async def get_part(part_id: UUID, service: ServiceDep, _user: AnyUser):
    return await service.get_detail(part_id)


@router.get("/{part_id}/order-history", response_model=list[PartOrderHistoryRow])
async def part_order_history(
    part_id: UUID,
    service: ServiceDep,
    _user: AdminOnly,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    supplier_id: Annotated[UUID | None, Query()] = None,
):
    return await service.order_history(
        part_id, start_date=start_date, end_date=end_date, supplier_id=supplier_id
    )


@router.patch("/{part_id}", response_model=PartDetail)
async def update_part(part_id: UUID, payload: PartUpdate, service: ServiceDep, _user: AdminOnly):
    return await service.update(part_id, payload)


@router.delete("/{part_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_part(part_id: UUID, service: ServiceDep, _user: AdminOnly):
    await service.delete(part_id)
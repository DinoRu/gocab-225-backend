from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep
from app.core.pagination import PaginationDep
from app.schemas.common import Page, to_page
from app.schemas.vehicle_brand import (
    VehicleBrandCreate,
    VehicleBrandRead,
    VehicleBrandUpdate,
)
from app.schemas.vehicle_model import VehicleModelRead
from app.services.vehicle_brand import VehicleBrandService
from app.api.auth_deps import AdminOnly, AnyUser

router = APIRouter(prefix="/vehicle-brands", tags=["vehicle-brands"])


def get_service(session: SessionDep) -> VehicleBrandService:
    return VehicleBrandService(session)


ServiceDep = Annotated[VehicleBrandService, Depends(get_service)]


@router.get("", response_model=Page[VehicleBrandRead])
async def list_brands(
    service: ServiceDep,
    pagination: PaginationDep,
    _user: AnyUser,
    search: Annotated[str | None, Query(max_length=120)] = None,
):
    items, total = await service.list_brands(
        search=search, page=pagination.page, limit=pagination.limit
    )
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.post("", response_model=VehicleBrandRead, status_code=status.HTTP_201_CREATED)
async def create_brand(payload: VehicleBrandCreate, service: ServiceDep, _user: AdminOnly ):
    return await service.create(payload)


@router.get("/{brand_id}", response_model=VehicleBrandRead)
async def get_brand(brand_id: UUID, service: ServiceDep, _user: AnyUser):
    return await service.get_or_404(brand_id)


@router.patch("/{brand_id}", response_model=VehicleBrandRead)
async def update_brand(brand_id: UUID, payload: VehicleBrandUpdate, service: ServiceDep, _user: AdminOnly):
    return await service.update(brand_id, payload)


@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand(brand_id: UUID, service: ServiceDep, _user: AdminOnly):
    await service.delete(brand_id)


@router.get("/{brand_id}/models", response_model=list[VehicleModelRead])
async def list_brand_models(brand_id: UUID, service: ServiceDep, _user: AnyUser):
    return await service.list_models(brand_id)
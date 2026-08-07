from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep
from app.core.pagination import PaginationDep
from app.schemas.common import Page, to_page
from app.schemas.vehicle_model import (
    VehicleModelCreate,
    VehicleModelRead,
    VehicleModelUpdate,
    VehicleModelWithBrand,
)
from app.services.vehicle_model import VehicleModelService
from app.api.auth_deps import AdminOnly, AnyUser

router = APIRouter(prefix="/vehicle-models", tags=["vehicle-models"])


def get_service(session: SessionDep) -> VehicleModelService:
    return VehicleModelService(session)


ServiceDep = Annotated[VehicleModelService, Depends(get_service)]


@router.get("", response_model=Page[VehicleModelRead])
async def list_models(
    service: ServiceDep,
    pagination: PaginationDep,
    _user: AnyUser,
    brand_id: Annotated[UUID | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
):
    items, total = await service.list(
        brand_id=brand_id,
        search=search,
        page=pagination.page,
        limit=pagination.limit,
    )
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.post("", response_model=VehicleModelRead, status_code=status.HTTP_201_CREATED)
async def create_model(payload: VehicleModelCreate, service: ServiceDep, _user: AdminOnly):
    return await service.create(payload)


@router.get("/{model_id}", response_model=VehicleModelWithBrand)
async def get_model(model_id: UUID, service: ServiceDep, _user: AnyUser):
    return await service.get_with_brand(model_id)


@router.patch("/{model_id}", response_model=VehicleModelRead)
async def update_model(model_id: UUID, payload: VehicleModelUpdate, service: ServiceDep, _user: AdminOnly):
    return await service.update(model_id, payload)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(model_id: UUID, service: ServiceDep, _user: AdminOnly):
    await service.delete(model_id)
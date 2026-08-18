from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from app.api.deps import SessionDep
from app.api.auth_deps import require_role, CurrentUserDep, AdminOnly
from app.core.pagination import PaginationDep
from app.schemas.common import Page, to_page
from app.schemas.center_request import (
    CenterRequestCreate, CenterRequestRead, CenterRequestUpdate, Status,
)
from app.services.center_request import CenterRequestService

# admin + centre ont accès au module
router = APIRouter(
    prefix="/center-requests",
    tags=["center-requests"],
    dependencies=[Depends(require_role("admin", "centre"))],
)


def get_service(session: SessionDep) -> CenterRequestService:
    return CenterRequestService(session)


ServiceDep = Annotated[CenterRequestService, Depends(get_service)]


@router.get("", response_model=Page[CenterRequestRead])
async def list_requests(
    service: ServiceDep,
    pagination: PaginationDep,
    user: CurrentUserDep,
    status_: Annotated[Status | None, Query(alias="status")] = None,
):
    # Un centre ne voit que ses demandes ; l'admin voit tout.
    is_admin = user.role == "admin"
    items, total = await service.list_requests(
        status=status_, mine_only=not is_admin, user_id=user.id,
        page=pagination.page, limit=pagination.limit,
    )
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.get("/{request_id}", response_model=CenterRequestRead)
async def get_request(request_id: UUID, service: ServiceDep):
    return await service.get_detail(request_id)


@router.post("", response_model=CenterRequestRead, status_code=status.HTTP_201_CREATED)
async def create_request(payload: CenterRequestCreate, service: ServiceDep, user: CurrentUserDep):
    return await service.create(payload, user_id=user.id)


@router.patch("/{request_id}", response_model=CenterRequestRead)
async def update_request(request_id: UUID, payload: CenterRequestUpdate, service: ServiceDep, user: CurrentUserDep):
    return await service.update(request_id, payload, user_id=user.id, is_admin=user.role == "admin")


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_request(request_id: UUID, service: ServiceDep, user: CurrentUserDep):
    await service.delete(request_id, user_id=user.id, is_admin=user.role == "admin")


# --- Préparation : admin uniquement ---
class ToggleInput(BaseModel):
    prepared: bool


@router.post("/{request_id}/items/{item_id}/toggle", response_model=CenterRequestRead)
async def toggle_item(request_id: UUID, item_id: UUID, payload: ToggleInput, service: ServiceDep, _a: AdminOnly):
    return await service.toggle_item(request_id, item_id, payload.prepared)


class StatusInput(BaseModel):
    status: Status


@router.post("/{request_id}/status", response_model=CenterRequestRead)
async def set_status(request_id: UUID, payload: StatusInput, service: ServiceDep, _a: AdminOnly):
    return await service.set_status(request_id, payload.status)
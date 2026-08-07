from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep
from app.api.auth_deps import require_role, CurrentUserDep
from app.core.pagination import PaginationDep
from app.schemas.common import Page, to_page
from app.schemas.user import PasswordReset, Role, UserCreate, UserRead, UserUpdate
from app.services.user import UserService

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_role("admin"))],   # tout le module : admin only
)


def get_service(session: SessionDep) -> UserService:
    return UserService(session)


ServiceDep = Annotated[UserService, Depends(get_service)]


@router.get("", response_model=Page[UserRead])
async def list_users(
    service: ServiceDep,
    pagination: PaginationDep,
    search: Annotated[str | None, Query(max_length=50)] = None,
    role: Annotated[Role | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
):
    items, total = await service.list_users(
        search=search, role=role, is_active=is_active,
        page=pagination.page, limit=pagination.limit,
    )
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, service: ServiceDep):
    return await service.create(payload)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: UUID, service: ServiceDep):
    return await service.get_or_404(user_id)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID, payload: UserUpdate, service: ServiceDep, current: CurrentUserDep
):
    return await service.update(user_id, payload, acting_admin_id=current.id)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(user_id: UUID, payload: PasswordReset, service: ServiceDep):
    await service.reset_password(user_id, payload.new_password)


@router.post("/{user_id}/activate", response_model=UserRead)
async def activate_user(user_id: UUID, service: ServiceDep, current: CurrentUserDep):
    return await service.set_active(user_id, True, acting_admin_id=current.id)


@router.post("/{user_id}/deactivate", response_model=UserRead)
async def deactivate_user(user_id: UUID, service: ServiceDep, current: CurrentUserDep):
    return await service.set_active(user_id, False, acting_admin_id=current.id)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: UUID, service: ServiceDep, current: CurrentUserDep):
    await service.delete(user_id, acting_admin_id=current.id)
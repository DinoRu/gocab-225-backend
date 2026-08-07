from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep
from app.core.pagination import PaginationDep
from app.schemas.common import Page, to_page
from app.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate
from app.services.supplier import SupplierService
from app.api.auth_deps import require_role

router = APIRouter(prefix="/suppliers", tags=["suppliers"], dependencies=[Depends(require_role("admin"))])


def get_service(session: SessionDep) -> SupplierService:
    return SupplierService(session)


ServiceDep = Annotated[SupplierService, Depends(get_service)]


@router.get("", response_model=Page[SupplierRead])
async def list_suppliers(
    service: ServiceDep,
    pagination: PaginationDep,
    search: Annotated[str | None, Query(max_length=200)] = None,
):
    items, total = await service.list(
        search=search, page=pagination.page, limit=pagination.limit
    )
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
async def create_supplier(payload: SupplierCreate, service: ServiceDep):
    return await service.create(payload)


@router.get("/{supplier_id}", response_model=SupplierRead)
async def get_supplier(supplier_id: UUID, service: ServiceDep):
    return await service.get_or_404(supplier_id)


@router.patch("/{supplier_id}", response_model=SupplierRead)
async def update_supplier(supplier_id: UUID, payload: SupplierUpdate, service: ServiceDep):
    return await service.update(supplier_id, payload)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(supplier_id: UUID, service: ServiceDep):
    await service.delete(supplier_id)
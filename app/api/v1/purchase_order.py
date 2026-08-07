from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep
from app.core.pagination import PaginationDep
from app.schemas.common import Page, to_page
from app.schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderRead,
    PurchaseOrderUpdate,
)
from app.services.purchase_order import PurchaseOrderService
from app.api.auth_deps import AdminOnly, AnyUser



router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


def get_service(session: SessionDep) -> PurchaseOrderService:
    return PurchaseOrderService(session)


ServiceDep = Annotated[PurchaseOrderService, Depends(get_service)]


@router.get("", response_model=Page[PurchaseOrderRead])
async def list_orders(
    service: ServiceDep,
    pagination: PaginationDep,
    user: AnyUser,
    search: Annotated[str | None, Query(max_length=30)] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    supplier_id: Annotated[UUID | None, Query()] = None,
    part_id: Annotated[UUID | None, Query()] = None,
    brand_id: Annotated[UUID | None, Query()] = None,
    vehicle_model_id: Annotated[UUID | None, Query()] = None,
    sort: Annotated[str, Query()] = "-order_date",
):
    items, total = await service.list_orders(
        search=search,
        start_date=start_date,
        end_date=end_date,
        supplier_id=supplier_id,
        part_id=part_id,
        brand_id=brand_id,
        vehicle_model_id=vehicle_model_id,
        sort=sort,
        page=pagination.page,
        limit=pagination.limit,
        hide_prices=(user.role != "admin"),  # les non-admins ne voient pas les prix
    )
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.post("", response_model=PurchaseOrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(payload: PurchaseOrderCreate, service: ServiceDep, _user: AdminOnly):
    return await service.create(payload)


@router.get("/{order_id}", response_model=PurchaseOrderRead)
async def get_order(order_id: UUID, service: ServiceDep, user: AnyUser):
    return await service.get_detail(order_id, hide_prices=(user.role != "admin"))  # les non-admins ne voient pas les prix


@router.patch("/{order_id}", response_model=PurchaseOrderRead)
async def update_order(order_id: UUID, payload: PurchaseOrderUpdate, service: ServiceDep, _user: AdminOnly):
    return await service.update(order_id, payload)


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(order_id: UUID, service: ServiceDep, _user: AdminOnly):
    await service.delete(order_id)
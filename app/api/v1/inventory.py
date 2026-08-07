from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import SessionDep
from app.core.pagination import PaginationDep
from app.schemas.common import Page, to_page
from app.schemas.inventory import (
    InventoryCountCreate,
    InventoryCountRead,
    InventoryCountUpdate,
    PartInventoryHistoryRow,
)
from app.services.inventory import InventoryService
from app.services.inventory_export import build_inventory_workbook
from app.api.auth_deps import require_role

router = APIRouter(prefix="/inventory", tags=["inventory"], dependencies=[Depends(require_role("admin", "magazinier"))])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def get_service(session: SessionDep) -> InventoryService:
    return InventoryService(session)


ServiceDep = Annotated[InventoryService, Depends(get_service)]


@router.get("/counts", response_model=Page[InventoryCountRead])
async def list_counts(
    service: ServiceDep,
    pagination: PaginationDep,
    search: Annotated[str | None, Query(max_length=30)] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
):
    items, total = await service.list_counts(
        search=search, start_date=start_date, end_date=end_date,
        page=pagination.page, limit=pagination.limit,
    )
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.post("/counts", response_model=InventoryCountRead, status_code=status.HTTP_201_CREATED)
async def create_count(payload: InventoryCountCreate, service: ServiceDep):
    return await service.create(payload)


@router.get("/counts/{count_id}", response_model=InventoryCountRead)
async def get_count(count_id: UUID, service: ServiceDep):
    return await service.get_detail(count_id)


@router.patch("/counts/{count_id}", response_model=InventoryCountRead)
async def update_count(count_id: UUID, payload: InventoryCountUpdate, service: ServiceDep):
    return await service.update(count_id, payload)


@router.delete("/counts/{count_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_count(count_id: UUID, service: ServiceDep):
    await service.delete(count_id)


@router.get("/counts/{count_id}/export")
async def export_count(count_id: UUID, service: ServiceDep):
    count = await service.get_detail(count_id)
    buffer = build_inventory_workbook(count)
    filename = f"inventaire_{count['count_number']}.xlsx"
    return Response(
        content=buffer.getvalue(), media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/parts/{part_id}/history", response_model=list[PartInventoryHistoryRow])
async def part_inventory_history(part_id: UUID, service: ServiceDep):
    return await service.part_history(part_id)
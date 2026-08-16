from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import SessionDep
from app.core.pagination import PaginationDep
from app.schemas.common import Page, to_page
from app.schemas.purchase_request import (
    BcFromSupplyInput,
    LinkOrderInput,
    PurchaseRequestCreate,
    PurchaseRequestRead,
    PurchaseRequestUpdate,
    Status,
)
from app.services.purchase_request import PurchaseRequestService
from app.services.purchase_request_doc import build_bc_pdf, build_bc_workbook
from app.api.auth_deps import AdminOnly, require_role


router = APIRouter(prefix="/purchase-requests", tags=["purchase-requests"], dependencies=[Depends(require_role("admin"))])
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PDF = "application/pdf"


def get_service(session: SessionDep) -> PurchaseRequestService:
    return PurchaseRequestService(session)


ServiceDep = Annotated[PurchaseRequestService, Depends(get_service)]


@router.get("", response_model=Page[PurchaseRequestRead])
async def list_bc(
    service: ServiceDep,
    pagination: PaginationDep,
    search: Annotated[str | None, Query(max_length=30)] = None,
    status_: Annotated[Status | None, Query(alias="status")] = None,
    supplier_id: Annotated[UUID | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
):
    items, total = await service.list_purchases(
        search=search, status=status_, supplier_id=supplier_id,
        start_date=start_date, end_date=end_date,
        page=pagination.page, limit=pagination.limit,
    )
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.post("", response_model=PurchaseRequestRead, status_code=status.HTTP_201_CREATED)
async def create_bc(payload: PurchaseRequestCreate, service: ServiceDep):
    return await service.create(payload)

from app.schemas.purchase_request import PurchaseRequestFromSupply
from app.services.supply_request import SupplyRequestService


@router.post("/from-supply", response_model=PurchaseRequestRead, status_code=status.HTTP_201_CREATED)
async def create_from_supply(
    payload: BcFromSupplyInput,
    service: ServiceDep,
    session: SessionDep,
    _user: AdminOnly,
):
    supply_service = SupplyRequestService(session)
    return await service.create_from_supply(payload, service_supply=supply_service)


@router.get("/{request_id}", response_model=PurchaseRequestRead)
async def get_bc(request_id: UUID, service: ServiceDep):
    return await service.get_detail(request_id)


@router.patch("/{request_id}", response_model=PurchaseRequestRead)
async def update_bc(request_id: UUID, payload: PurchaseRequestUpdate, service: ServiceDep):
    return await service.update(request_id, payload)


@router.post("/{request_id}/send", response_model=PurchaseRequestRead)
async def mark_sent(request_id: UUID, service: ServiceDep):
    return await service.mark_sent(request_id)


@router.post("/{request_id}/receive", response_model=PurchaseRequestRead)
async def mark_received(request_id: UUID, payload: LinkOrderInput, service: ServiceDep):
    return await service.mark_received(request_id, purchase_order_id=payload.purchase_order_id)


@router.post("/{request_id}/reopen", response_model=PurchaseRequestRead)
async def reopen(request_id: UUID, service: ServiceDep):
    return await service.reopen(request_id)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bc(request_id: UUID, service: ServiceDep):
    await service.delete(request_id)


@router.get("/{request_id}/pdf")
async def export_pdf(request_id: UUID, service: ServiceDep):
    pr = await service.get_detail(request_id)
    buffer = build_bc_pdf(pr)
    filename = f"bon_commande_{pr['bc_number']}.pdf"
    return Response(content=buffer.getvalue(), media_type=_PDF,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{request_id}/excel")
async def export_excel(request_id: UUID, service: ServiceDep):
    pr = await service.get_detail(request_id)
    buffer = build_bc_workbook(pr)
    filename = f"bon_commande_{pr['bc_number']}.xlsx"
    return Response(content=buffer.getvalue(), media_type=_XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
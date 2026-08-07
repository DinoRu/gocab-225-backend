from datetime import date
from io import BytesIO
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import SessionDep
from app.core.pagination import PaginationDep
from app.schemas.common import Page, to_page
from app.schemas.payment_request import (
    PaymentRequestCreate,
    PaymentRequestRead,
    PaymentRequestUpdate,
    Priority,
    Status,
)
from app.services.payment_request import PaymentRequestService
from app.services.payment_request_export import build_payment_requests_workbook
from app.api.auth_deps import require_role

router = APIRouter(prefix="/payment-requests", tags=["payment-requests"], dependencies=[Depends(require_role("admin"))])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def get_service(session: SessionDep) -> PaymentRequestService:
    return PaymentRequestService(session)


ServiceDep = Annotated[PaymentRequestService, Depends(get_service)]


@router.get("", response_model=Page[PaymentRequestRead])
async def list_requests(
    service: ServiceDep,
    pagination: PaginationDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    status_: Annotated[Status | None, Query(alias="status")] = None,
    priority: Annotated[Priority | None, Query()] = None,
    supplier_id: Annotated[UUID | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
):
    items, total = await service.list_payments(
        search=search, status=status_, priority=priority, supplier_id=supplier_id,
        start_date=start_date, end_date=end_date, page=pagination.page, limit=pagination.limit,
    )
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.post("", response_model=PaymentRequestRead, status_code=status.HTTP_201_CREATED)
async def create_request(payload: PaymentRequestCreate, service: ServiceDep):
    return await service.create(payload)


@router.get("/export")
async def export_requests(
    service: ServiceDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    status_: Annotated[Status | None, Query(alias="status")] = None,
    priority: Annotated[Priority | None, Query()] = None,
    supplier_id: Annotated[UUID | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
):
    # On exporte tout le périmètre filtré (grande limite, pas de pagination).
    items, _ = await service.list_payments(
        search=search, status=status_, priority=priority, supplier_id=supplier_id,
        start_date=start_date, end_date=end_date, page=1, limit=100_000,
    )
    buffer: BytesIO = build_payment_requests_workbook(items)
    filename = f"demandes_paiement_{date.today().isoformat()}.xlsx"
    return Response(
        content=buffer.getvalue(),
        media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{request_id}", response_model=PaymentRequestRead)
async def get_request(request_id: UUID, service: ServiceDep):
    return await service.get_detail(request_id)


@router.patch("/{request_id}", response_model=PaymentRequestRead)
async def update_request(request_id: UUID, payload: PaymentRequestUpdate, service: ServiceDep):
    return await service.update(request_id, payload)


@router.post("/{request_id}/mark-paid", response_model=PaymentRequestRead)
async def mark_paid(request_id: UUID, service: ServiceDep):
    return await service.mark_paid(request_id)


@router.post("/{request_id}/mark-unpaid", response_model=PaymentRequestRead)
async def mark_unpaid(request_id: UUID, service: ServiceDep):
    return await service.mark_unpaid(request_id)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_request(request_id: UUID, service: ServiceDep):
    await service.delete(request_id)
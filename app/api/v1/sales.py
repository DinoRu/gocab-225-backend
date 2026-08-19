from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import SessionDep
from app.api.auth_deps import require_role
from app.core.pagination import PaginationDep
from app.schemas.common import Page, to_page
from app.schemas.sales import (
    SalesClientCreate, SalesClientRead, SalesClientUpdate, SalesDashboardResponse,
    SalesProductCreate, SalesProductRead, SalesProductUpdate,
    SalesOrderCreate, SalesOrderRead, SalesOrderUpdate,
    SalesPaymentCreate, SalesPaymentRead, ClientLedgerRead,
    SalesProformaCreate, SalesProformaRead, SalesProformaUpdate, ProformaConvertInput
)
from app.services.sales import (
    SalesClientService, SalesProductService, SalesOrderService,
)
from app.services.sales_dashboard import SalesDashboardService
from app.services.sales_payment import SalesPaymentService
from app.services.sales_proforma import SalesProformaService
from app.services.sales_proforma_doc import build_proforma_pdf



_PDF = "application/pdf"

router = APIRouter(
    prefix="/sales",
    tags=["sales"],
    dependencies=[Depends(require_role("admin"))],   # module réservé à l'admin
)


# @router.get("/units", response_model=list[str])
# async def list_units():
#     return SALES_UNITS


@router.get("/dashboard", response_model=SalesDashboardResponse)
async def sales_dashboard(
    session: SessionDep,
    months: Annotated[int, Query(ge=1, le=36)] = 12,
):
    return await SalesDashboardService(session).build(months=months)


# ---------- Clients ----------
@router.get("/clients", response_model=Page[SalesClientRead])
async def list_clients(
    session: SessionDep,
    pagination: PaginationDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
):
    svc = SalesClientService(session)
    items, total = await svc.list_clients(search=search, page=pagination.page, limit=pagination.limit)
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.post("/clients", response_model=SalesClientRead, status_code=status.HTTP_201_CREATED)
async def create_client(payload: SalesClientCreate, session: SessionDep):
    return await SalesClientService(session).create(payload)


@router.patch("/clients/{client_id}", response_model=SalesClientRead)
async def update_client(client_id: UUID, payload: SalesClientUpdate, session: SessionDep):
    return await SalesClientService(session).update(client_id, payload)


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(client_id: UUID, session: SessionDep):
    await SalesClientService(session).delete(client_id)


# ---------- Produits ----------
@router.get("/products", response_model=Page[SalesProductRead])
async def list_products(
    session: SessionDep,
    pagination: PaginationDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
):
    svc = SalesProductService(session)
    items, total = await svc.list_products(search=search, page=pagination.page, limit=pagination.limit)
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.post("/products", response_model=SalesProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(payload: SalesProductCreate, session: SessionDep):
    return await SalesProductService(session).create(payload)


@router.patch("/products/{product_id}", response_model=SalesProductRead)
async def update_product(product_id: UUID, payload: SalesProductUpdate, session: SessionDep):
    return await SalesProductService(session).update(product_id, payload)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: UUID, session: SessionDep):
    await SalesProductService(session).delete(product_id)


# ---------- Ventes ----------
@router.get("/orders", response_model=Page[SalesOrderRead])
async def list_sales(
    session: SessionDep,
    pagination: PaginationDep,
    search: Annotated[str | None, Query(max_length=30)] = None,
    client_id: Annotated[UUID | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
):
    svc = SalesOrderService(session)
    items, total = await svc.list_sales(
        search=search, client_id=client_id, start_date=start_date, end_date=end_date,
        page=pagination.page, limit=pagination.limit,
    )
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.get("/orders/{order_id}", response_model=SalesOrderRead)
async def get_sale(order_id: UUID, session: SessionDep):
    return await SalesOrderService(session).get_detail(order_id)


@router.post("/orders", response_model=SalesOrderRead, status_code=status.HTTP_201_CREATED)
async def create_sale(payload: SalesOrderCreate, session: SessionDep):
    return await SalesOrderService(session).create(payload)


@router.patch("/orders/{order_id}", response_model=SalesOrderRead)
async def update_sale(order_id: UUID, payload: SalesOrderUpdate, session: SessionDep):
    return await SalesOrderService(session).update(order_id, payload)


@router.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sale(order_id: UUID, session: SessionDep):
    await SalesOrderService(session).delete(order_id)
    
# ---------- Paiements ----------
@router.get("/payments", response_model=Page[SalesPaymentRead])
async def list_payments(
    session: SessionDep,
    pagination: PaginationDep,
    client_id: Annotated[UUID | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
):
    svc = SalesPaymentService(session)
    items, total = await svc.list_payments(
        client_id=client_id, start_date=start_date, end_date=end_date,
        page=pagination.page, limit=pagination.limit,
    )
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.post("/payments", response_model=SalesPaymentRead, status_code=status.HTTP_201_CREATED)
async def create_payment(payload: SalesPaymentCreate, session: SessionDep):
    return await SalesPaymentService(session).create(payload)


@router.delete("/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment(payment_id: UUID, session: SessionDep):
    await SalesPaymentService(session).delete(payment_id)


# ---------- Grand livre d'un client ----------
@router.get("/clients/{client_id}/ledger", response_model=ClientLedgerRead)
async def client_ledger(client_id: UUID, session: SessionDep):
    return await SalesPaymentService(session).client_ledger(client_id)



@router.get("/proformas", response_model=Page[SalesProformaRead])
async def list_proformas(
    session: SessionDep,
    pagination: PaginationDep,
    client_id: Annotated[UUID | None, Query()] = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
):
    svc = SalesProformaService(session)
    items, total = await svc.list_proformas(
        client_id=client_id, status=status_, page=pagination.page, limit=pagination.limit,
    )
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.get("/proformas/{pf_id}", response_model=SalesProformaRead)
async def get_proforma(pf_id: UUID, session: SessionDep):
    return await SalesProformaService(session).get_detail(pf_id)


@router.post("/proformas", response_model=SalesProformaRead, status_code=status.HTTP_201_CREATED)
async def create_proforma(payload: SalesProformaCreate, session: SessionDep):
    return await SalesProformaService(session).create(payload)


@router.patch("/proformas/{pf_id}", response_model=SalesProformaRead)
async def update_proforma(pf_id: UUID, payload: SalesProformaUpdate, session: SessionDep):
    return await SalesProformaService(session).update(pf_id, payload)


@router.delete("/proformas/{pf_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proforma(pf_id: UUID, session: SessionDep):
    await SalesProformaService(session).delete(pf_id)


@router.post("/proformas/{pf_id}/convert", response_model=SalesProformaRead)
async def convert_proforma(pf_id: UUID, payload: ProformaConvertInput, session: SessionDep):
    return await SalesProformaService(session).convert(pf_id, payload)


@router.get("/proformas/{pf_id}/pdf")
async def proforma_pdf(pf_id: UUID, session: SessionDep):
    pf = await SalesProformaService(session).get_detail(pf_id)
    buffer = build_proforma_pdf(pf)
    filename = f"proforma_{pf['proforma_number']}.pdf"
    return Response(content=buffer.getvalue(), media_type=_PDF,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
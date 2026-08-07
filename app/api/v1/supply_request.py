from datetime import date
from io import BytesIO
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import SessionDep
from app.api.auth_deps import AdminOnly, AnyUser, CurrentUserDep
from app.core.pagination import PaginationDep
from app.schemas.common import Page, to_page
from app.schemas.supply_request import (
    SupplyRequestCreate,
    SupplyRequestRead,
    SupplyRequestUpdate,
    Status,
)
from app.services.supply_request import SupplyRequestService
from app.services.supply_request_export import build_supply_requests_workbook

router = APIRouter(prefix="/supply-requests", tags=["supply-requests"])
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def get_service(session: SessionDep) -> SupplyRequestService:
    return SupplyRequestService(session)


ServiceDep = Annotated[SupplyRequestService, Depends(get_service)]


def _visibility(user) -> UUID | None:
    """Magazinier → limité à ses propres besoins. Admin → tout (None = pas de filtre)."""
    return None if user.role == "admin" else user.id


@router.get("", response_model=Page[SupplyRequestRead])
async def list_supply_requests(
    service: ServiceDep,
    pagination: PaginationDep,
    user: AnyUser,
    search: Annotated[str | None, Query(max_length=30)] = None,
    status_: Annotated[Status | None, Query(alias="status")] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
):
    items, total = await service.list_requests(
        search=search, status=status_, created_by=_visibility(user),
        start_date=start_date, end_date=end_date,
        page=pagination.page, limit=pagination.limit,
    )
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.post("", response_model=SupplyRequestRead, status_code=status.HTTP_201_CREATED)
async def create_supply_request(
    payload: SupplyRequestCreate, service: ServiceDep, current: CurrentUserDep
):
    # Magazinier ET admin peuvent créer ; on trace l'auteur.
    return await service.create(payload, created_by=current.id)


@router.get("/export")
async def export_supply_requests(
    service: ServiceDep,
    user: AnyUser,
    status_: Annotated[Status | None, Query(alias="status")] = None,
):
    # L'export respecte la visibilité : le magazinier n'exporte que ses besoins.
    items, _ = await service.list_requests(
        search=None, status=status_, created_by=_visibility(user),
        start_date=None, end_date=None, page=1, limit=100_000,
    )
    buffer: BytesIO = build_supply_requests_workbook(items, status_filter=status_)
    filename = f"besoins_approvisionnement_{date.today().isoformat()}.xlsx"
    return Response(
        content=buffer.getvalue(), media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{request_id}", response_model=SupplyRequestRead)
async def get_supply_request(request_id: UUID, service: ServiceDep, user: AnyUser):
    data = await service.get_detail(request_id)
    # Un magazinier ne peut pas ouvrir le besoin d'un autre.
    if user.role != "admin" and data["created_by"] != user.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Besoin introuvable.")
    return data


@router.patch("/{request_id}", response_model=SupplyRequestRead)
async def update_supply_request(
    request_id: UUID, payload: SupplyRequestUpdate, service: ServiceDep, user: AnyUser
):
    # Le magazinier ne modifie que ses besoins ; l'admin modifie tout.
    if user.role != "admin":
        existing = await service.get_detail(request_id)
        if existing["created_by"] != user.id:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Besoin introuvable.")
    return await service.update(request_id, payload)


@router.post("/{request_id}/mark-fulfilled", response_model=SupplyRequestRead)
async def mark_fulfilled(request_id: UUID, service: ServiceDep, _user: AdminOnly):
    # Seul l'admin décide qu'un besoin est traité.
    return await service.mark_fulfilled(request_id)


@router.post("/{request_id}/reopen", response_model=SupplyRequestRead)
async def reopen(request_id: UUID, service: ServiceDep, _user: AdminOnly):
    return await service.reopen(request_id)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supply_request(request_id: UUID, service: ServiceDep, user: AnyUser):
    # Le magazinier supprime ses besoins (tant qu'ils ne sont pas traités) ; l'admin supprime tout.
    if user.role != "admin":
        existing = await service.get_detail(request_id)
        if existing["created_by"] != user.id:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Besoin introuvable.")
        if existing["status"] == "fulfilled":
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail="Un besoin traité ne peut pas être supprimé.")
    await service.delete(request_id)
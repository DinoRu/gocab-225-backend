from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import SessionDep
from app.services.export import ExportService

router = APIRouter(prefix="/exports", tags=["exports"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def get_service(session: SessionDep) -> ExportService:
    return ExportService(session)


ServiceDep = Annotated[ExportService, Depends(get_service)]


@router.get("/parts-orders")
async def export_parts_orders(
    service: ServiceDep,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    part_id: Annotated[UUID | None, Query()] = None,
    supplier_id: Annotated[UUID | None, Query()] = None,
    brand_id: Annotated[UUID | None, Query()] = None,
    vehicle_model_id: Annotated[UUID | None, Query()] = None,
):
    content, filename = await service.parts_orders(
        start_date=start_date,
        end_date=end_date,
        part_id=part_id,
        supplier_id=supplier_id,
        brand_id=brand_id,
        vehicle_model_id=vehicle_model_id,
    )
    return Response(
        content=content,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
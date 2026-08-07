from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import SessionDep
from app.schemas.statistics import PartStatDetail, PartStatRow, PartStatSummary
from app.services.statistics import StatisticsService
from app.api.auth_deps import require_role

router = APIRouter(prefix="/statistics", tags=["statistics"], dependencies=[Depends(require_role("admin"))])


def get_service(session: SessionDep) -> StatisticsService:
    return StatisticsService(session)


ServiceDep = Annotated[StatisticsService, Depends(get_service)]


@router.get("/parts", response_model=list[PartStatRow])
async def parts_statistics(
    service: ServiceDep,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    part_id: Annotated[UUID | None, Query()] = None,
    supplier_id: Annotated[UUID | None, Query()] = None,
    brand_id: Annotated[UUID | None, Query()] = None,
    vehicle_model_id: Annotated[UUID | None, Query()] = None,
):
    return await service.parts_stats(
        start_date=start_date,
        end_date=end_date,
        part_id=part_id,
        supplier_id=supplier_id,
        brand_id=brand_id,
        vehicle_model_id=vehicle_model_id,
    )


@router.get("/parts/{part_id}", response_model=PartStatDetail)
async def part_statistics(
    part_id: UUID,
    service: ServiceDep,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
):
    return await service.part_detail(part_id, start_date=start_date, end_date=end_date)


@router.get("/parts/{part_id}/summary", response_model=PartStatSummary)
async def part_statistics_summary(part_id: UUID, service: ServiceDep):
    return await service.part_summary(part_id)
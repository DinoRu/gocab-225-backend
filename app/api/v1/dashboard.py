from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import SessionDep
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import DashboardService, Period

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_service(session: SessionDep) -> DashboardService:
    return DashboardService(session)


ServiceDep = Annotated[DashboardService, Depends(get_service)]


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    service: ServiceDep,
    period: Annotated[Period | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    brand_id: Annotated[UUID | None, Query()] = None,
    vehicle_model_id: Annotated[UUID | None, Query()] = None,
):
    return await service.build(
        period=period,
        start_date=start_date,
        end_date=end_date,
        brand_id=brand_id,
        vehicle_model_id=vehicle_model_id,
    )
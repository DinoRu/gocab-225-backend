import uuid
from datetime import date
from pydantic import BaseModel

from app.schemas.part import ModelRef


class PartStatRow(BaseModel):
    part_id: uuid.UUID
    reference: str
    designation: str
    models_label: str          # "Bestune B70, Bestune T55" ou "Universel"
    is_universal: bool
    total_quantity_ordered: int


class PartStatDetail(BaseModel):
    part_id: uuid.UUID
    reference: str
    designation: str
    vehicle_models: list[ModelRef]
    is_universal: bool
    start_date: date | None
    end_date: date | None
    total_quantity_ordered: int


class PartInfo(BaseModel):
    reference: str
    designation: str
    models: str                # label lisible


class PartStatSummary(BaseModel):
    part: PartInfo
    last_3_months: int
    last_6_months: int
    last_12_months: int
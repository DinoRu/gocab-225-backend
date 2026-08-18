import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["nouvelle", "preparee", "envoyee"]


class CenterItemCreate(BaseModel):
    part_id: uuid.UUID | None = None
    designation: str = Field(min_length=1, max_length=255)
    quantity: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=255)


class CenterRequestCreate(BaseModel):
    vehicle_brand: str = Field(min_length=1, max_length=100)
    vehicle_model: str = Field(min_length=1, max_length=100)
    plate_number: str | None = Field(default=None, max_length=30)
    request_date: date
    notes: str | None = None
    items: list[CenterItemCreate] = Field(min_length=1)


class CenterRequestUpdate(BaseModel):
    vehicle_brand: str | None = Field(default=None, max_length=100)
    vehicle_model: str | None = Field(default=None, max_length=100)
    plate_number: str | None = Field(default=None, max_length=30)
    request_date: date | None = None
    notes: str | None = None
    items: list[CenterItemCreate] | None = None


class CenterItemRead(BaseModel):
    id: uuid.UUID
    part_id: uuid.UUID | None
    designation: str
    quantity: int
    note: str | None
    prepared: bool
    from_catalog: bool          # True si part_id renseigné


class CenterRequestRead(BaseModel):
    id: uuid.UUID
    request_number: str
    vehicle_brand: str
    vehicle_model: str
    plate_number: str | None
    request_date: date
    status: Status
    notes: str | None
    created_by: uuid.UUID | None
    created_by_name: str | None
    items: list[CenterItemRead]
    prepared_count: int         # nb de lignes cochées
    total_items: int
    created_at: datetime
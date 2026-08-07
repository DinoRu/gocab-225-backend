import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal
from datetime import date as _date

class ModelRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    brand_id: uuid.UUID
    brand_name: str


class PartCreate(BaseModel):
    reference: str = Field(min_length=1, max_length=120)
    designation: str = Field(min_length=1, max_length=255)
    vehicle_model_ids: list[uuid.UUID] = Field(default_factory=list)
    category: str | None = Field(default=None, max_length=120)


class PartUpdate(BaseModel):
    reference: str | None = Field(default=None, min_length=1, max_length=120)
    designation: str | None = Field(default=None, min_length=1, max_length=255)
    vehicle_model_ids: list[uuid.UUID] | None = None
    category: str | None = Field(default=None, max_length=120)


class PartRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    designation: str
    category: str | None
    vehicle_models: list[ModelRef]
    is_universal: bool
    created_at: datetime
    updated_at: datetime


# Version enrichie renvoyée par GET /parts (marque + modèle résolus par jointure)
class PartDetail(PartRead):
    pass


class PartOrderHistoryRow(BaseModel):
    order_date: _date
    order_number: str
    supplier_name: str
    quantity: int
    unit_price: Decimal | None
    line_total: Decimal | None
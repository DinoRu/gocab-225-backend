import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Status = Literal["open", "in_progress", "fulfilled"]


class SupplyRequestItemCreate(BaseModel):
    part_id: uuid.UUID
    quantity: int = Field(gt=0)


class SupplyRequestCreate(BaseModel):
    request_date: date
    notes: str | None = None
    items: list[SupplyRequestItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_dup(self):
        ids = [i.part_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Une même pièce ne peut apparaître qu'une fois dans le besoin.")
        return self


class SupplyRequestUpdate(BaseModel):
    request_date: date | None = None
    notes: str | None = None
    items: list[SupplyRequestItemCreate] | None = None

    @model_validator(mode="after")
    def _validate(self):
        if self.items is not None:
            if not self.items:
                raise ValueError("Un besoin doit contenir au moins une ligne.")
            ids = [i.part_id for i in self.items]
            if len(ids) != len(set(ids)):
                raise ValueError("Une même pièce ne peut apparaître qu'une fois.")
        return self


class SupplyRequestItemRead(BaseModel):
    id: uuid.UUID
    part_id: uuid.UUID
    reference: str
    designation: str
    quantity: int


class LinkedBcRead(BaseModel):
    id: uuid.UUID
    bc_number: str
    supplier_name: str | None
    status: str


class SupplyRequestRead(BaseModel):
    id: uuid.UUID
    sr_number: str
    request_date: date
    status: Status
    notes: str | None
    created_by: uuid.UUID | None
    created_by_name: str | None
    items: list[SupplyRequestItemRead]
    linked_bcs: list[LinkedBcRead]        # les bons issus de ce besoin
    created_at: datetime
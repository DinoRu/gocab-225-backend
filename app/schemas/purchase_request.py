import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Status = Literal["draft", "sent", "received"]


class PurchaseRequestItemCreate(BaseModel):
    part_id: uuid.UUID
    quantity: int = Field(gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)   # optionnel


class PurchaseRequestCreate(BaseModel):
    supplier_id: uuid.UUID
    request_date: date
    expected_date: date | None = None
    notes: str | None = None
    items: list[PurchaseRequestItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_dup(self):
        ids = [i.part_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Une même pièce ne peut apparaître qu'une fois dans le bon.")
        return self


class PurchaseRequestUpdate(BaseModel):
    supplier_id: uuid.UUID | None = None
    request_date: date | None = None
    expected_date: date | None = None
    notes: str | None = None
    items: list[PurchaseRequestItemCreate] | None = None

    @model_validator(mode="after")
    def _validate(self):
        if self.items is not None:
            if not self.items:
                raise ValueError("Un bon doit contenir au moins une ligne.")
            ids = [i.part_id for i in self.items]
            if len(ids) != len(set(ids)):
                raise ValueError("Une même pièce ne peut apparaître qu'une fois.")
        return self


class LinkOrderInput(BaseModel):
    purchase_order_id: uuid.UUID | None = None


class SupplierRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str


class PurchaseRequestItemRead(BaseModel):
    id: uuid.UUID
    part_id: uuid.UUID
    reference: str
    designation: str
    quantity: int
    unit_price: Decimal | None
    line_total: Decimal | None


class PurchaseRequestRead(BaseModel):
    id: uuid.UUID
    bc_number: str
    supplier: SupplierRef
    request_date: date
    expected_date: date | None
    status: Status
    purchase_order_id: uuid.UUID | None
    order_number: str | None
    notes: str | None
    items: list[PurchaseRequestItemRead]
    total_amount: Decimal | None       # None si aucun prix renseigné
    sent_at: datetime | None
    received_at: datetime | None
    created_at: datetime
    

class PurchaseRequestFromSupply(BaseModel):
    supply_request_id: uuid.UUID
    supplier_id: uuid.UUID
    request_date: date
    expected_date: date | None = None
    notes: str | None = None
    # Lignes ajustables : tu peux ne commander qu'une partie du besoin (éclatement),
    # et ajouter les prix. Si absent, on reprend toutes les lignes du besoin sans prix.
    items: list[PurchaseRequestItemCreate] | None = None
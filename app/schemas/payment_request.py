import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Priority = Literal["low", "normal", "high", "urgent"]
Status = Literal["to_pay", "paid"]


class PaymentRequestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(gt=0)
    request_date: date
    supplier_id: uuid.UUID
    link: str | None = Field(default=None, max_length=1000)
    odoo_reference: str | None = Field(default=None, max_length=120)
    priority: Priority = "normal"
    notes: str | None = None



class PaymentRequestUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    amount: Decimal | None = Field(default=None, gt=0)
    request_date: date | None = None
    link: str | None = Field(default=None, max_length=1000)
    odoo_reference: str | None = Field(default=None, max_length=120)
    priority: Priority | None = None
    notes: str | None = None


class SupplierRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str


class PaymentRequestRead(BaseModel):
    id: uuid.UUID
    request_number: str
    title: str
    amount: Decimal
    request_date: date
    link: str | None
    odoo_reference: str | None
    priority: Priority
    status: Status
    supplier: SupplierRef     # rempli si lié à une commande
    notes: str | None
    paid_at: datetime | None
    created_at: datetime
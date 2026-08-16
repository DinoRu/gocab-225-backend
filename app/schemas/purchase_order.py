import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class PurchaseOrderItemCreate(BaseModel):
    part_id: uuid.UUID
    quantity: int = Field(gt=0)                       # bloque <= 0 dès l'entrée
    unit_price: Decimal | None = Field(default=None, ge=0)


class PurchaseOrderCreate(BaseModel):
    supplier_id: uuid.UUID
    order_date: date
    notes: str | None = None
    items: list[PurchaseOrderItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_duplicate_parts(self):
        ids = [i.part_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Une même pièce ne peut apparaître qu'une fois dans la commande.")
        return self


class PurchaseOrderUpdate(BaseModel):
    supplier_id: uuid.UUID | None = None
    order_date: date | None = None
    notes: str | None = None
    # Si fourni, remplace intégralement les lignes (sinon lignes inchangées).
    items: list[PurchaseOrderItemCreate] | None = None

    @model_validator(mode="after")
    def _validate_items(self):
        if self.items is not None:
            if len(self.items) == 0:
                raise ValueError("Une commande doit contenir au moins une ligne.")
            ids = [i.part_id for i in self.items]
            if len(ids) != len(set(ids)):
                raise ValueError("Une même pièce ne peut apparaître qu'une fois dans la commande.")
        return self


class PurchaseOrderItemRead(BaseModel):
    id: uuid.UUID
    part_id: uuid.UUID
    reference: str
    designation: str
    quantity: int
    unit_price: Decimal | None
    line_total: Decimal | None       # quantity * unit_price (None si pas de prix)


class PurchaseOrderRead(BaseModel):
    id: uuid.UUID
    order_number: str
    order_date: date
    supplier_id: uuid.UUID
    supplier_name: str
    notes: str | None
    items: list[PurchaseOrderItemRead]
    total_amount: Decimal | None     # None si aucune ligne n'a de prix
    created_at: datetime


class OrderLineEdit(BaseModel):
    part_id: uuid.UUID
    quantity: int = Field(gt=0)
    unit_price: Decimal | None = None


class OrderLinesUpdate(BaseModel):
    """État final voulu des lignes. Le service compare avec l'existant
    pour déduire modifications / ajouts / suppressions."""
    items: list[OrderLineEdit] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_dup(self):
        ids = [i.part_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Une même pièce ne peut apparaître qu'une fois dans la commande.")
        return self


class OrderAuditEntry(BaseModel):
    id: uuid.UUID
    username: str | None
    changes: list[str]
    created_at: datetime
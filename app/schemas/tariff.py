import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ---------- Fournisseurs ----------
class TariffSupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = None
    contact_name: str | None = None
    notes: str | None = None


class TariffSupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = None
    contact_name: str | None = None
    notes: str | None = None


class TariffSupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    phone: str | None
    contact_name: str | None
    notes: str | None
    created_at: datetime


# ---------- Articles ----------
class TariffArticleCreate(BaseModel):
    reference: str | None = Field(default=None, max_length=100)
    designation: str = Field(min_length=1, max_length=255)
    notes: str | None = None


class TariffArticleUpdate(BaseModel):
    reference: str | None = Field(default=None, max_length=100)
    designation: str | None = Field(default=None, min_length=1, max_length=255)
    notes: str | None = None


class TariffArticleRead(BaseModel):
    id: uuid.UUID
    reference: str | None
    designation: str
    notes: str | None
    supplier_count: int          # combien de fournisseurs ont un prix
    best_price: Decimal | None   # le moins cher parmi les derniers prix
    created_at: datetime


# ---------- Prix ----------
class TariffPriceCreate(BaseModel):
    article_id: uuid.UUID
    supplier_id: uuid.UUID
    price: Decimal = Field(ge=0)
    effective_date: date
    notes: str | None = Field(default=None, max_length=255)


class TariffPriceRead(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str
    price: Decimal
    effective_date: date
    notes: str | None
    created_at: datetime


# ---------- Vue par article : fournisseurs + dernier prix ----------
class SupplierPriceRow(BaseModel):
    supplier_id: uuid.UUID
    supplier_name: str
    last_price: Decimal
    last_date: date
    history: list[TariffPriceRead]    # tout l'historique de ce couple


class ArticlePricesView(BaseModel):
    article_id: uuid.UUID
    designation: str
    reference: str | None
    suppliers: list[SupplierPriceRow]  # triés du moins cher au plus cher


# ---------- Vue par fournisseur : articles + dernier prix ----------
class ArticlePriceRow(BaseModel):
    article_id: uuid.UUID
    designation: str
    reference: str | None
    last_price: Decimal
    last_date: date


class SupplierPricesView(BaseModel):
    supplier_id: uuid.UUID
    supplier_name: str
    articles: list[ArticlePriceRow]
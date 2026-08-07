import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class DashboardPeriod(BaseModel):
    start_date: date | None
    end_date: date | None
    
    

class TopPartRow(BaseModel):
    part_id: uuid.UUID
    reference: str
    designation: str
    models_label: str          # remplace brand + model
    total_quantity: int
    
    

class TopSupplierRow(BaseModel):
    supplier_id: uuid.UUID
    name: str
    order_count: int
    total_quantity: int


class MonthlyQuantity(BaseModel):
    month: str            # "YYYY-MM"
    total_quantity: int
    

class BrandQuantity(BaseModel):
    brand_id: uuid.UUID | None  # None = bucket "Universel"
    name: str
    total_quantity: int


class ModelQuantity(BaseModel):
    model_id: uuid.UUID
    name: str
    brand: str
    total_quantity: int


class DashboardResponse(BaseModel):
    period: DashboardPeriod
    total_orders: int
    total_quantity: int
    total_amount: Decimal | None
    distinct_references: int
    top_parts: list[TopPartRow]
    top_suppliers: list[TopSupplierRow]
    quantity_by_month: list[MonthlyQuantity]
    quantity_by_brand: list[BrandQuantity]
    quantity_by_model: list[ModelQuantity]
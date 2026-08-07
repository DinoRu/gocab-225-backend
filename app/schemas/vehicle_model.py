import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.vehicle_brand import VehicleBrandRead


class VehicleModelCreate(BaseModel):
    brand_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)


class VehicleModelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class VehicleModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class VehicleModelWithBrand(VehicleModelRead):
    brand: VehicleBrandRead
    
    
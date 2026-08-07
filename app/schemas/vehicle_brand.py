import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class VehicleBrandCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class VehicleBrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class VehicleBrandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
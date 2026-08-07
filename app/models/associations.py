from sqlalchemy import Column, DateTime, ForeignKey, Table, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.database.base import Base

part_vehicle_models = Table(
    "part_vehicle_models",
    Base.metadata,
    Column("part_id", PGUUID(as_uuid=True),
           ForeignKey("parts.id", ondelete="CASCADE"), primary_key=True),
    Column("vehicle_model_id", PGUUID(as_uuid=True),
           ForeignKey("vehicle_models.id", ondelete="RESTRICT"), primary_key=True),
    Column("created_at", DateTime, server_default=func.now(), nullable=False),
)
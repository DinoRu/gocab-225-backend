import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["admin", "magazinier", "centre"]


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=120)
    role: Role = "magazinier"


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    role: Role | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str | None
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime
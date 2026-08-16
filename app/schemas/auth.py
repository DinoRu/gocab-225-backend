import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["admin", "magazinier"]


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1)


# class Token(BaseModel):
#     access_token: str
#     token_type: str = "bearer"


class CurrentUser(BaseModel):
    """L'utilisateur tel qu'exposé après authentification. Jamais le hash."""
    id: uuid.UUID
    username: str
    full_name: str | None
    role: Role
    is_active: bool
    created_at: datetime
    

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshInput(BaseModel):
    refresh_token: str
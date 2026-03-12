from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class UserCreate(BaseModel):
    entra_id: str
    email: str
    display_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str = "standard_user"
    is_active: bool = True


class UserUpdate(BaseModel):
    entra_id: Optional[str] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    entra_id: str
    email: str
    display_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    is_active: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

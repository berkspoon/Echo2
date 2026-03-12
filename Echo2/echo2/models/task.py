from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class TaskCreate(BaseModel):
    title: str
    due_date: Optional[date] = None
    assigned_to: UUID
    status: str = "open"
    notes: Optional[str] = None
    source: str = "manual"
    linked_record_type: Optional[str] = None
    linked_record_id: Optional[UUID] = None
    is_archived: bool = False
    created_by: Optional[UUID] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    due_date: Optional[date] = None
    assigned_to: Optional[UUID] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = None
    linked_record_type: Optional[str] = None
    linked_record_id: Optional[UUID] = None
    is_archived: Optional[bool] = None


class TaskResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    title: str
    due_date: Optional[date] = None
    assigned_to: UUID
    status: str
    notes: Optional[str] = None
    source: str
    linked_record_type: Optional[str] = None
    linked_record_id: Optional[UUID] = None
    is_archived: bool
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

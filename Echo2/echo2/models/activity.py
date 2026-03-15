from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class ActivityCreate(BaseModel):
    title: Optional[str] = None
    effective_date: date
    activity_type: str
    subtype: Optional[str] = None
    author_id: UUID
    details: str
    follow_up_required: bool = False
    follow_up_date: Optional[date] = None
    follow_up_notes: Optional[str] = None
    fund_tags: Optional[List[UUID]] = None
    notify_user_ids: Optional[List[UUID]] = None
    is_deleted: bool = False
    created_by: Optional[UUID] = None


class ActivityUpdate(BaseModel):
    title: Optional[str] = None
    effective_date: Optional[date] = None
    activity_type: Optional[str] = None
    subtype: Optional[str] = None
    author_id: Optional[UUID] = None
    details: Optional[str] = None
    follow_up_required: Optional[bool] = None
    follow_up_date: Optional[date] = None
    follow_up_notes: Optional[str] = None
    fund_tags: Optional[List[UUID]] = None
    notify_user_ids: Optional[List[UUID]] = None
    is_deleted: Optional[bool] = None


class ActivityResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    title: Optional[str] = None
    effective_date: date
    activity_type: str
    subtype: Optional[str] = None
    author_id: UUID
    details: str
    follow_up_required: bool
    follow_up_date: Optional[date] = None
    follow_up_notes: Optional[str] = None
    fund_tags: Optional[List[UUID]] = None
    notify_user_ids: Optional[List[UUID]] = None
    is_deleted: bool
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

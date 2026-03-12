from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FundProspectCreate(BaseModel):
    organization_id: UUID
    fund_id: UUID
    share_class: str
    stage: str = "target_identified"
    decline_reason: Optional[str] = None
    aksia_owner_id: UUID
    target_allocation_mn: Optional[Decimal] = None
    soft_circle_mn: Optional[Decimal] = None
    hard_circle_mn: Optional[Decimal] = None
    probability_pct: Optional[int] = None
    linked_lead_id: Optional[UUID] = None
    next_steps: Optional[str] = None
    next_steps_date: Optional[date] = None
    notes: Optional[str] = None
    stage_entry_date: date
    is_archived: bool = False
    created_by: Optional[UUID] = None


class FundProspectUpdate(BaseModel):
    organization_id: Optional[UUID] = None
    fund_id: Optional[UUID] = None
    share_class: Optional[str] = None
    stage: Optional[str] = None
    decline_reason: Optional[str] = None
    aksia_owner_id: Optional[UUID] = None
    target_allocation_mn: Optional[Decimal] = None
    soft_circle_mn: Optional[Decimal] = None
    hard_circle_mn: Optional[Decimal] = None
    probability_pct: Optional[int] = None
    linked_lead_id: Optional[UUID] = None
    next_steps: Optional[str] = None
    next_steps_date: Optional[date] = None
    notes: Optional[str] = None
    stage_entry_date: Optional[date] = None
    is_archived: Optional[bool] = None


class FundProspectResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    organization_id: UUID
    fund_id: UUID
    share_class: str
    stage: str
    decline_reason: Optional[str] = None
    aksia_owner_id: UUID
    target_allocation_mn: Optional[Decimal] = None
    soft_circle_mn: Optional[Decimal] = None
    hard_circle_mn: Optional[Decimal] = None
    probability_pct: Optional[int] = None
    linked_lead_id: Optional[UUID] = None
    next_steps: Optional[str] = None
    next_steps_date: Optional[date] = None
    notes: Optional[str] = None
    stage_entry_date: date
    is_archived: bool
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

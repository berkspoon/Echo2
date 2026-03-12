from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class ContractCreate(BaseModel):
    organization_id: UUID
    originating_lead_id: UUID
    start_date: date
    service_type: str
    asset_classes: List[str]
    client_coverage: Optional[str] = None
    summary: Optional[str] = None
    actual_revenue: Decimal
    inflation_provision: Optional[str] = None
    escalator_clause: Optional[str] = None
    is_archived: bool = False
    created_by: Optional[UUID] = None


class ContractUpdate(BaseModel):
    organization_id: Optional[UUID] = None
    originating_lead_id: Optional[UUID] = None
    start_date: Optional[date] = None
    service_type: Optional[str] = None
    asset_classes: Optional[List[str]] = None
    client_coverage: Optional[str] = None
    summary: Optional[str] = None
    actual_revenue: Optional[Decimal] = None
    inflation_provision: Optional[str] = None
    escalator_clause: Optional[str] = None
    is_archived: Optional[bool] = None


class ContractResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    organization_id: UUID
    originating_lead_id: UUID
    start_date: date
    service_type: str
    asset_classes: List[str]
    client_coverage: Optional[str] = None
    summary: Optional[str] = None
    actual_revenue: Decimal
    inflation_provision: Optional[str] = None
    escalator_clause: Optional[str] = None
    is_archived: bool
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

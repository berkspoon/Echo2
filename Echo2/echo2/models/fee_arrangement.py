from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FeeArrangementCreate(BaseModel):
    organization_id: UUID
    arrangement_name: str
    annual_value: Decimal
    frequency: str
    status: str = "active"
    start_date: date
    end_date: Optional[date] = None
    notes: Optional[str] = None
    created_by: Optional[UUID] = None


class FeeArrangementUpdate(BaseModel):
    arrangement_name: Optional[str] = None
    annual_value: Optional[Decimal] = None
    frequency: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None


class FeeArrangementResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    organization_id: UUID
    arrangement_name: str
    annual_value: Decimal
    frequency: str
    status: str
    start_date: date
    end_date: Optional[date] = None
    notes: Optional[str] = None
    is_archived: bool
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

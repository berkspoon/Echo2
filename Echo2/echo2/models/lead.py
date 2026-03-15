from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class LeadCreate(BaseModel):
    organization_id: UUID
    start_date: date
    end_date: Optional[date] = None
    rating: str = "exploratory"
    service_type: Optional[str] = None
    asset_classes: Optional[List[str]] = None
    relationship: Optional[str] = None
    aksia_owner_id: Optional[UUID] = None
    source: Optional[str] = None
    summary: Optional[str] = None

    # Focus+ fields
    pricing_proposal: Optional[str] = None
    pricing_proposal_details: Optional[str] = None
    expected_decision_date: Optional[date] = None
    expected_revenue: Optional[Decimal] = None
    expected_revenue_notes: Optional[str] = None
    expected_yr1_flar: Optional[Decimal] = None
    expected_longterm_flar: Optional[Decimal] = None
    previous_flar: Optional[Decimal] = None
    rfp_status: Optional[str] = None
    rfp_expected_date: Optional[date] = None
    risk_weight: Optional[str] = None
    next_steps: Optional[str] = None
    next_steps_date: Optional[date] = None

    # Verbal Mandate+ fields
    legacy_onboarding: Optional[bool] = None
    legacy_onboarding_holdings: Optional[str] = None
    potential_coverage: Optional[str] = None

    is_deleted: bool = False
    created_by: Optional[UUID] = None


class LeadUpdate(BaseModel):
    organization_id: Optional[UUID] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    rating: Optional[str] = None
    service_type: Optional[str] = None
    asset_classes: Optional[List[str]] = None
    relationship: Optional[str] = None
    aksia_owner_id: Optional[UUID] = None
    source: Optional[str] = None
    summary: Optional[str] = None

    pricing_proposal: Optional[str] = None
    pricing_proposal_details: Optional[str] = None
    expected_decision_date: Optional[date] = None
    expected_revenue: Optional[Decimal] = None
    expected_revenue_notes: Optional[str] = None
    expected_yr1_flar: Optional[Decimal] = None
    expected_longterm_flar: Optional[Decimal] = None
    previous_flar: Optional[Decimal] = None
    rfp_status: Optional[str] = None
    rfp_expected_date: Optional[date] = None
    risk_weight: Optional[str] = None
    next_steps: Optional[str] = None
    next_steps_date: Optional[date] = None

    legacy_onboarding: Optional[bool] = None
    legacy_onboarding_holdings: Optional[str] = None
    potential_coverage: Optional[str] = None

    is_deleted: Optional[bool] = None


class LeadResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    organization_id: UUID
    start_date: date
    end_date: Optional[date] = None
    rating: str
    service_type: Optional[str] = None
    asset_classes: Optional[List[str]] = None
    relationship: Optional[str] = None
    aksia_owner_id: Optional[UUID] = None
    source: Optional[str] = None
    summary: Optional[str] = None

    pricing_proposal: Optional[str] = None
    pricing_proposal_details: Optional[str] = None
    expected_decision_date: Optional[date] = None
    expected_revenue: Optional[Decimal] = None
    expected_revenue_notes: Optional[str] = None
    expected_yr1_flar: Optional[Decimal] = None
    expected_longterm_flar: Optional[Decimal] = None
    previous_flar: Optional[Decimal] = None
    rfp_status: Optional[str] = None
    rfp_expected_date: Optional[date] = None
    risk_weight: Optional[str] = None
    next_steps: Optional[str] = None
    next_steps_date: Optional[date] = None

    legacy_onboarding: Optional[bool] = None
    legacy_onboarding_holdings: Optional[str] = None
    potential_coverage: Optional[str] = None

    is_deleted: bool
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

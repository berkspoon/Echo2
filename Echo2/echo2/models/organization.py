from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class OrganizationCreate(BaseModel):
    company_name: str
    short_name: Optional[str] = None
    relationship_type: str
    organization_type: str
    team_distribution_email: Optional[str] = None
    aum_mn: Optional[Decimal] = None
    website: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    state_province: Optional[str] = None
    street_address: Optional[str] = None
    postal_code: Optional[str] = None

    # Client Questionnaire
    questionnaire_filled_by: Optional[UUID] = None
    questionnaire_date: Optional[date] = None
    client_discloses_info: Optional[bool] = False
    overall_aum_mn: Optional[Decimal] = None
    aum_as_of_date: Optional[date] = None
    aum_source: Optional[str] = None
    hf_target_allocation_pct: Optional[Decimal] = None
    pe_target_allocation_pct: Optional[Decimal] = None
    pc_target_allocation_pct: Optional[Decimal] = None
    re_target_allocation_pct: Optional[Decimal] = None
    ra_target_allocation_pct: Optional[Decimal] = None
    target_allocation_source: Optional[str] = None

    # Confidentiality
    rfp_hold: bool = False
    nda_signed: Optional[bool] = False
    nda_expiration: Optional[bool] = False
    nda_expiration_date: Optional[date] = None

    # Other IDs
    backstop_company_id: Optional[str] = None
    ostrako_id: Optional[str] = None

    is_deleted: bool = False
    created_by: Optional[UUID] = None


class OrganizationUpdate(BaseModel):
    company_name: Optional[str] = None
    short_name: Optional[str] = None
    relationship_type: Optional[str] = None
    organization_type: Optional[str] = None
    team_distribution_email: Optional[str] = None
    aum_mn: Optional[Decimal] = None
    website: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    state_province: Optional[str] = None
    street_address: Optional[str] = None
    postal_code: Optional[str] = None

    questionnaire_filled_by: Optional[UUID] = None
    questionnaire_date: Optional[date] = None
    client_discloses_info: Optional[bool] = None
    overall_aum_mn: Optional[Decimal] = None
    aum_as_of_date: Optional[date] = None
    aum_source: Optional[str] = None
    hf_target_allocation_pct: Optional[Decimal] = None
    pe_target_allocation_pct: Optional[Decimal] = None
    pc_target_allocation_pct: Optional[Decimal] = None
    re_target_allocation_pct: Optional[Decimal] = None
    ra_target_allocation_pct: Optional[Decimal] = None
    target_allocation_source: Optional[str] = None

    rfp_hold: Optional[bool] = None
    nda_signed: Optional[bool] = None
    nda_expiration: Optional[bool] = None
    nda_expiration_date: Optional[date] = None

    backstop_company_id: Optional[str] = None
    ostrako_id: Optional[str] = None

    is_deleted: Optional[bool] = None


class OrganizationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    company_name: str
    short_name: Optional[str] = None
    relationship_type: str
    organization_type: str
    team_distribution_email: Optional[str] = None
    aum_mn: Optional[Decimal] = None
    website: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    state_province: Optional[str] = None
    street_address: Optional[str] = None
    postal_code: Optional[str] = None

    questionnaire_filled_by: Optional[UUID] = None
    questionnaire_date: Optional[date] = None
    client_discloses_info: Optional[bool] = False
    overall_aum_mn: Optional[Decimal] = None
    aum_as_of_date: Optional[date] = None
    aum_source: Optional[str] = None
    hf_target_allocation_pct: Optional[Decimal] = None
    pe_target_allocation_pct: Optional[Decimal] = None
    pc_target_allocation_pct: Optional[Decimal] = None
    re_target_allocation_pct: Optional[Decimal] = None
    ra_target_allocation_pct: Optional[Decimal] = None
    target_allocation_source: Optional[str] = None

    rfp_hold: bool
    nda_signed: Optional[bool] = False
    nda_expiration: Optional[bool] = False
    nda_expiration_date: Optional[date] = None

    backstop_company_id: Optional[str] = None
    ostrako_id: Optional[str] = None

    is_deleted: bool
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

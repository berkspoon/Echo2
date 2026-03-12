from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class PersonCreate(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    asset_classes_of_interest: Optional[List[str]] = None
    coverage_owner: Optional[UUID] = None
    do_not_contact: bool = False
    legal_compliance_notices: bool = False
    backstop_company_id: Optional[str] = None
    ostrako_id: Optional[str] = None
    is_archived: bool = False
    created_by: Optional[UUID] = None


class PersonUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    asset_classes_of_interest: Optional[List[str]] = None
    coverage_owner: Optional[UUID] = None
    do_not_contact: Optional[bool] = None
    legal_compliance_notices: Optional[bool] = None
    backstop_company_id: Optional[str] = None
    ostrako_id: Optional[str] = None
    is_archived: Optional[bool] = None


class PersonResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    asset_classes_of_interest: Optional[List[str]] = None
    coverage_owner: Optional[UUID] = None
    do_not_contact: bool
    legal_compliance_notices: bool
    backstop_company_id: Optional[str] = None
    ostrako_id: Optional[str] = None
    is_archived: bool
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

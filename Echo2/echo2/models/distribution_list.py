from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class DistributionListCreate(BaseModel):
    list_name: str
    list_type: str
    brand: Optional[str] = None
    asset_class: Optional[str] = None
    frequency: Optional[str] = None
    is_official: bool = False
    is_private: bool = True
    owner_id: Optional[UUID] = None
    l2_superset_of: Optional[UUID] = None
    list_mode: str = "static"
    filter_criteria: Optional[dict] = None
    is_active: bool = True
    created_by: Optional[UUID] = None


class DistributionListUpdate(BaseModel):
    list_name: Optional[str] = None
    list_type: Optional[str] = None
    brand: Optional[str] = None
    asset_class: Optional[str] = None
    frequency: Optional[str] = None
    is_official: Optional[bool] = None
    is_private: Optional[bool] = None
    owner_id: Optional[UUID] = None
    l2_superset_of: Optional[UUID] = None
    list_mode: Optional[str] = None
    filter_criteria: Optional[dict] = None
    is_active: Optional[bool] = None


class DistributionListResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    list_name: str
    list_type: str
    brand: Optional[str] = None
    asset_class: Optional[str] = None
    frequency: Optional[str] = None
    is_official: bool
    is_private: bool
    owner_id: Optional[UUID] = None
    l2_superset_of: Optional[UUID] = None
    list_mode: str = "static"
    filter_criteria: Optional[dict] = None
    is_active: bool
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

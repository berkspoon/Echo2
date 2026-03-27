"""Shared database helpers — reference data, audit logging, entity lookups.

Consolidated from duplicated private helpers across all routers.
"""

from datetime import date as date_type
from typing import Optional
from uuid import UUID

from db.client import get_supabase


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

def get_reference_data(
    category: str, parent_value: Optional[str] = None
) -> list[dict]:
    """Fetch active reference data for a dropdown category.

    Args:
        category: The reference_data category (e.g. 'organization_type').
        parent_value: Optional parent filter for hierarchical data
                      (e.g. activity subtypes scoped to a parent type).
    """
    sb = get_supabase()
    query = (
        sb.table("reference_data")
        .select("value, label, parent_value")
        .eq("category", category)
        .eq("is_active", True)
        .order("display_order")
    )
    if parent_value:
        query = query.eq("parent_value", parent_value)
    return query.execute().data or []


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

def log_field_change(
    record_type: str,
    record_id: str,
    field_name: str,
    old_value,
    new_value,
    changed_by: UUID,
) -> None:
    """Write a single field change to the audit_log table."""
    sb = get_supabase()
    sb.table("audit_log").insert({
        "record_type": record_type,
        "record_id": record_id,
        "field_name": field_name,
        "old_value": str(old_value) if old_value is not None else None,
        "new_value": str(new_value) if new_value is not None else None,
        "changed_by": str(changed_by),
    }).execute()


def audit_changes(
    record_type: str,
    record_id: str,
    old_record: dict,
    new_data: dict,
    changed_by: UUID,
) -> None:
    """Compare old record with new data and log every changed field."""
    for field, new_val in new_data.items():
        old_val = old_record.get(field)
        if str(old_val) != str(new_val) and not (old_val is None and new_val is None):
            log_field_change(record_type, record_id, field, old_val, new_val, changed_by)


# ---------------------------------------------------------------------------
# Entity lookups
# ---------------------------------------------------------------------------

def get_org_name(org_id: str) -> str:
    """Look up an organization's company_name by ID."""
    sb = get_supabase()
    resp = (
        sb.table("organizations")
        .select("company_name")
        .eq("id", str(org_id))
        .maybe_single()
        .execute()
    )
    return resp.data["company_name"] if resp.data else "Unknown"


def get_user_name(user_id: str) -> str:
    """Look up a user's display_name by ID."""
    sb = get_supabase()
    resp = (
        sb.table("users")
        .select("display_name")
        .eq("id", str(user_id))
        .maybe_single()
        .execute()
    )
    return resp.data["display_name"] if resp.data else "Unknown"


def batch_resolve_users(user_ids: list[str]) -> dict:
    """Batch resolve user UUIDs to display names.

    Returns: {user_id_str: display_name}
    """
    if not user_ids:
        return {}
    sb = get_supabase()
    unique_ids = list(set(str(uid) for uid in user_ids if uid))
    if not unique_ids:
        return {}
    resp = (
        sb.table("users")
        .select("id, display_name")
        .in_("id", unique_ids)
        .execute()
    )
    return {str(u["id"]): u["display_name"] for u in (resp.data or [])}


def batch_resolve_orgs(org_ids: list[str]) -> dict:
    """Batch resolve organization UUIDs to org data.

    Returns: {org_id_str: {company_name, organization_type, ...}}
    """
    if not org_ids:
        return {}
    sb = get_supabase()
    unique_ids = list(set(str(oid) for oid in org_ids if oid))
    if not unique_ids:
        return {}
    resp = (
        sb.table("organizations")
        .select("*")
        .in_("id", unique_ids)
        .execute()
    )
    return {str(o["id"]): o for o in (resp.data or [])}


# ---------------------------------------------------------------------------
# Task utilities
# ---------------------------------------------------------------------------

def is_overdue(task: dict) -> bool:
    """Return True if task is past due and still open/in-progress."""
    if task.get("status") not in ("open", "in_progress"):
        return False
    if not task.get("due_date"):
        return False
    try:
        due = date_type.fromisoformat(str(task["due_date"])[:10])
        return due < date_type.today()
    except (ValueError, TypeError):
        return False

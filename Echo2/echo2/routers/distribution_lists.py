"""Distribution lists router — full CRUD, member management, send preview/history,
L2-superset-of-L1 enforcement, DNC/RFP Hold suppression."""

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from db.field_service import get_field_definitions, enrich_field_definitions
from db.helpers import get_reference_data, log_field_change, audit_changes, get_user_name
from db.view_config_service import get_view_config
from dependencies import CurrentUser, get_current_user, require_role
from services.grid_service import build_grid_context

router = APIRouter(prefix="/distribution-lists", tags=["distribution_lists"])
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Filter Builder constants
# ---------------------------------------------------------------------------

_ORG_FILTER_FIELDS = [
    {"field_name": "org_city", "display_name": "Org City", "field_type": "text", "dropdown_category": None, "dropdown_options": None},
    {"field_name": "org_country", "display_name": "Org Country", "field_type": "dropdown", "dropdown_category": "country", "dropdown_options": None},
    {"field_name": "org_type", "display_name": "Org Type", "field_type": "dropdown", "dropdown_category": "organization_type", "dropdown_options": None},
    {"field_name": "org_aum_mn", "display_name": "Org AUM ($M)", "field_type": "number", "dropdown_category": None, "dropdown_options": None},
]

_OPERATORS_BY_TYPE = {
    "text":         [("contains", "Contains"), ("not_contains", "Does not contain"), ("eq", "Equals"), ("neq", "Not equals"), ("is_empty", "Is empty"), ("is_not_empty", "Is not empty")],
    "email":        [("contains", "Contains"), ("not_contains", "Does not contain"), ("eq", "Equals"), ("neq", "Not equals"), ("is_empty", "Is empty"), ("is_not_empty", "Is not empty")],
    "phone":        [("contains", "Contains"), ("eq", "Equals"), ("is_empty", "Is empty"), ("is_not_empty", "Is not empty")],
    "url":          [("contains", "Contains"), ("eq", "Equals"), ("is_empty", "Is empty"), ("is_not_empty", "Is not empty")],
    "textarea":     [("contains", "Contains"), ("not_contains", "Does not contain"), ("is_empty", "Is empty"), ("is_not_empty", "Is not empty")],
    "dropdown":     [("eq", "Equals"), ("neq", "Not equals"), ("in", "Is any of"), ("not_in", "Is none of"), ("is_empty", "Is empty"), ("is_not_empty", "Is not empty")],
    "multi_select": [("in", "Contains any of"), ("not_in", "Contains none of"), ("is_empty", "Is empty"), ("is_not_empty", "Is not empty")],
    "number":       [("eq", "Equals"), ("neq", "Not equals"), ("gt", "Greater than"), ("gte", "At least"), ("lt", "Less than"), ("lte", "At most"), ("is_empty", "Is empty"), ("is_not_empty", "Is not empty")],
    "currency":     [("eq", "Equals"), ("neq", "Not equals"), ("gt", "Greater than"), ("gte", "At least"), ("lt", "Less than"), ("lte", "At most"), ("is_empty", "Is empty"), ("is_not_empty", "Is not empty")],
    "date":         [("eq", "On"), ("gt", "After"), ("lt", "Before"), ("is_empty", "Is empty"), ("is_not_empty", "Is not empty")],
    "boolean":      [("eq", "Is")],
    "text_list":    [("contains", "Contains"), ("is_empty", "Is empty"), ("is_not_empty", "Is not empty")],
    "lookup":       [("eq", "Equals"), ("neq", "Not equals"), ("is_empty", "Is empty"), ("is_not_empty", "Is not empty")],
}

# Org virtual field names for identifying org-level filters
_ORG_VIRTUAL_FIELD_NAMES = {"org_city", "org_country", "org_type", "org_aum_mn"}
# Mapping from virtual field name to real org column
_ORG_VIRTUAL_TO_COLUMN = {"org_city": "city", "org_country": "country",
                           "org_type": "organization_type", "org_aum_mn": "aum_mn"}


def _build_filter_fields() -> list[dict]:
    """Build the list of available filter fields (person fields + org virtual fields).

    Reads admin-configurable view config for field whitelists and org virtual fields.
    Falls back to hardcoded defaults if no DB row exists.
    """
    dl_config = get_view_config("dl_filter_fields", default={
        "person_fields": [],
        "org_fields": [
            {"field_name": f["field_name"], "display_name": f["display_name"],
             "field_type": f["field_type"], "dropdown_category": f.get("dropdown_category")}
            for f in _ORG_FILTER_FIELDS
        ],
        "include_field_types": list(_OPERATORS_BY_TYPE.keys()),
    })

    person_fields = get_field_definitions("person", active_only=True)
    filterable_types = set(dl_config.get("include_field_types", _OPERATORS_BY_TYPE.keys()))

    # Person field whitelist (empty = all)
    person_whitelist = set(dl_config.get("person_fields", []))

    result = []
    for fd in person_fields:
        if fd["field_type"] not in filterable_types:
            continue
        if fd.get("storage_type") == "linked":
            continue
        if person_whitelist and fd["field_name"] not in person_whitelist:
            continue
        entry = {
            "field_name": fd["field_name"],
            "display_name": fd.get("display_name", fd["field_name"].replace("_", " ").title()),
            "field_type": fd["field_type"],
            "options": [],
        }
        # For lookup fields, load active users as options
        if fd["field_type"] == "lookup":
            sb = get_supabase()
            users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
            entry["options"] = [{"value": str(u["id"]), "label": u["display_name"]} for u in (users_resp.data or [])]
        result.append(entry)

    # Enrich dropdown options
    for fd in result:
        if fd["field_type"] in ("dropdown", "multi_select") and not fd["options"]:
            orig = next((f for f in person_fields if f["field_name"] == fd["field_name"]), None)
            cat = (orig or {}).get("dropdown_category") or fd["field_name"]
            ref = get_reference_data(cat)
            if ref:
                fd["options"] = [{"value": r["value"], "label": r["label"]} for r in ref]

    # Add org virtual fields from config
    org_fields = dl_config.get("org_fields", [])
    for org_f in org_fields:
        entry = {
            "field_name": org_f["field_name"],
            "display_name": org_f["display_name"],
            "field_type": org_f["field_type"],
            "options": [],
        }
        if org_f.get("dropdown_category"):
            ref = get_reference_data(org_f["dropdown_category"])
            if ref:
                entry["options"] = [{"value": r["value"], "label": r["label"]} for r in ref]
        result.append(entry)
    return result


def _convert_old_to_new_format(old: dict) -> dict:
    """Convert old cf_field=op:value format to new {filters: [...]} format."""
    filters = []
    for key, val in old.items():
        if key == "q" or key.startswith("_"):
            continue
        field = key.replace("cf_", "")
        if not isinstance(val, str) or ":" not in val:
            continue
        op, v = val.split(":", 1)
        if op == "in":
            v = [x.strip() for x in v.split(",") if x.strip()]
        filters.append({"field": field, "operator": op, "value": v})
    return {"filters": filters}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_person_with_org(person_id: str) -> dict | None:
    """Look up a person with their primary org name."""
    sb = get_supabase()
    person_resp = (
        sb.table("people")
        .select("id, first_name, last_name, email, do_not_contact, is_deleted, coverage_owner")
        .eq("id", person_id)
        .maybe_single()
        .execute()
    )
    if not person_resp.data:
        return None
    person = person_resp.data

    # Primary org
    org_link_resp = (
        sb.table("person_organization_links")
        .select("organization_id")
        .eq("person_id", person_id)
        .eq("link_type", "primary")
        .limit(1)
        .execute()
    )
    org_name = None
    org_rfp_hold = False
    if org_link_resp.data:
        org_resp = (
            sb.table("organizations")
            .select("company_name, rfp_hold")
            .eq("id", org_link_resp.data[0]["organization_id"])
            .maybe_single()
            .execute()
        )
        if org_resp.data:
            org_name = org_resp.data["company_name"]
            org_rfp_hold = org_resp.data.get("rfp_hold", False)

    person["org_name"] = org_name
    person["org_rfp_hold"] = org_rfp_hold
    person["full_name"] = f"{person['first_name']} {person['last_name']}"
    return person


def _can_edit_list(dist_list: dict, current_user: CurrentUser) -> bool:
    """Check if the current user can edit this distribution list."""
    if current_user.role == "admin":
        return True
    if dist_list.get("is_official"):
        return False  # Only admin can edit official lists
    # Custom lists: owner or admin/standard/rfp_team
    if current_user.role in ("standard_user", "rfp_team"):
        return str(dist_list.get("owner_id")) == str(current_user.id)
    return False


def _can_manage_members(dist_list: dict, current_user: CurrentUser) -> bool:
    """Check if the current user can add/remove members."""
    if current_user.role == "admin":
        return True
    if current_user.role in ("standard_user", "rfp_team"):
        if dist_list.get("is_official"):
            return True  # Standard users can manage official list members
        return str(dist_list.get("owner_id")) == str(current_user.id) or not dist_list.get("is_private")
    return False


def _can_send(dist_list: dict, current_user: CurrentUser) -> bool:
    """Check if the current user can send from this list."""
    if current_user.role == "admin":
        return True
    if dist_list.get("is_official"):
        return False  # Official list sends restricted to admin (authorized senders TBD)
    if current_user.role in ("standard_user", "rfp_team"):
        return str(dist_list.get("owner_id")) == str(current_user.id)
    return False


def _build_list_data_from_form(form) -> dict:
    """Extract distribution list fields from form data."""
    data = {}
    for text_field in ("list_name", "list_type", "brand", "asset_class", "frequency"):
        val = (form.get(text_field) or "").strip()
        data[text_field] = val if val else None

    # Booleans
    data["is_official"] = form.get("is_official") == "on"
    data["is_private"] = form.get("is_private") == "on"

    # If official, force not private
    if data["is_official"]:
        data["is_private"] = False

    # L2 superset FK
    l2_of = (form.get("l2_superset_of") or "").strip()
    data["l2_superset_of"] = l2_of if l2_of else None

    # D1: Dynamic distribution lists
    data["list_mode"] = (form.get("list_mode") or "static").strip()

    return data


def _validate_list_fields(data: dict) -> list[str]:
    """Validate distribution list fields. Returns list of error strings."""
    errors = []
    if not data.get("list_name"):
        errors.append("List Name is required.")
    if not data.get("list_type"):
        errors.append("List Type is required.")
    return errors


def _get_member_count(list_id: str) -> int:
    """Get count of active members for a distribution list."""
    sb = get_supabase()
    resp = (
        sb.table("distribution_list_members")
        .select("id", count="exact")
        .eq("distribution_list_id", list_id)
        .eq("is_active", True)
        .execute()
    )
    return resp.count or 0


def _resolve_dynamic_members(filter_criteria: dict) -> list[str]:
    """Resolve person IDs matching filter criteria for a dynamic distribution list.

    Supports two formats:
    - New: {"filters": [{"field": "country", "operator": "in", "value": ["US","GB"]}, ...]}
    - Old: {"cf_country": "in:US,GB", "q": "search text", ...}
    """
    # Detect new vs old format
    if "filters" in filter_criteria:
        return _resolve_dynamic_members_new(filter_criteria.get("filters", []))
    return _resolve_dynamic_members_old(filter_criteria)


def _resolve_dynamic_members_old(filter_criteria: dict) -> list[str]:
    """Legacy resolver for old cf_field=op:value format."""
    has_meaningful = any(k.startswith("cf_") for k in filter_criteria) or filter_criteria.get("q")
    if not has_meaningful:
        return []

    sb = get_supabase()

    _OLD_ORG_VIRTUAL = {"org_city": "city", "org_country": "country",
                        "org_type": "organization_type", "org_aum_mn": "aum_mn"}
    org_filters = {}
    people_filters = {}
    for key, val in filter_criteria.items():
        if not key.startswith("cf_"):
            people_filters[key] = val
            continue
        field_name = key[3:]
        if field_name in _OLD_ORG_VIRTUAL:
            org_filters[field_name] = val
        elif field_name == "has_active_leads":
            org_filters[field_name] = val
        else:
            people_filters[key] = val

    allowed_person_ids: set[str] | None = None
    if org_filters:
        org_query = sb.table("organizations").select("id").eq("is_deleted", False)
        for field_name, val in org_filters.items():
            if field_name == "has_active_leads":
                continue
            real_col = _OLD_ORG_VIRTUAL[field_name]
            if ":" not in val:
                continue
            op, operand = val.split(":", 1)
            if op == "contains":
                org_query = org_query.ilike(real_col, f"%{operand}%")
            elif op == "eq":
                org_query = org_query.eq(real_col, operand)
            elif op == "neq":
                org_query = org_query.neq(real_col, operand)
            elif op == "in":
                values = [v.strip() for v in operand.split(",") if v.strip()]
                if values:
                    org_query = org_query.in_(real_col, values)
        org_resp = org_query.limit(5000).execute()
        matching_org_ids = [str(o["id"]) for o in (org_resp.data or [])]
        if matching_org_ids:
            pol_resp = (
                sb.table("person_organization_links")
                .select("person_id")
                .in_("link_type", ["primary", "secondary"])
                .in_("organization_id", matching_org_ids)
                .execute()
            )
            allowed_person_ids = {str(p["person_id"]) for p in (pol_resp.data or [])}
        else:
            return []

    query = sb.table("people").select("id").eq("is_deleted", False).eq("do_not_contact", False)
    if allowed_person_ids is not None:
        if not allowed_person_ids:
            return []
        query = query.in_("id", list(allowed_person_ids))

    q = people_filters.get("q", "")
    if q:
        query = query.or_(f"first_name.ilike.%{q}%,last_name.ilike.%{q}%,email.ilike.%{q}%")
    if people_filters.get("ac"):
        query = query.contains("asset_classes_of_interest", [people_filters["ac"]])

    for key, val in people_filters.items():
        if not key.startswith("cf_"):
            continue
        field_name = key[3:]
        if ":" not in val:
            continue
        op, operand = val.split(":", 1)
        if op == "contains":
            query = query.ilike(field_name, f"%{operand}%")
        elif op == "eq":
            query = query.eq(field_name, operand)
        elif op == "neq":
            query = query.neq(field_name, operand)
        elif op == "in":
            values = [v.strip() for v in operand.split(",") if v.strip()]
            if values:
                query = query.in_(field_name, values)

    resp = query.limit(5000).execute()
    return [str(r["id"]) for r in (resp.data or [])]


def _apply_filter_to_query(query, field_name: str, operator: str, value):
    """Apply a single filter criterion to a Supabase query builder."""
    if operator == "contains":
        return query.ilike(field_name, f"%{value}%")
    elif operator == "not_contains":
        return query.not_.ilike(field_name, f"%{value}%")
    elif operator == "eq":
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return query.eq(field_name, value.lower() == "true")
        return query.eq(field_name, value)
    elif operator == "neq":
        return query.neq(field_name, value)
    elif operator == "in":
        vals = value if isinstance(value, list) else [v.strip() for v in str(value).split(",") if v.strip()]
        if vals:
            return query.in_(field_name, vals)
    elif operator == "not_in":
        vals = value if isinstance(value, list) else [v.strip() for v in str(value).split(",") if v.strip()]
        if vals:
            # Supabase doesn't have a clean not_in, filter in Python later
            pass  # handled post-query
    elif operator == "gt":
        return query.gt(field_name, value)
    elif operator == "gte":
        return query.gte(field_name, value)
    elif operator == "lt":
        return query.lt(field_name, value)
    elif operator == "lte":
        return query.lte(field_name, value)
    elif operator == "is_empty":
        return query.is_(field_name, "null")
    elif operator == "is_not_empty":
        return query.not_.is_(field_name, "null")
    return query


def _resolve_dynamic_members_new(filters: list[dict]) -> list[str]:
    """New format resolver: array of {field, operator, value} filter objects."""
    if not filters:
        return []

    sb = get_supabase()

    # Separate org-level vs person-level filters
    org_filters = [f for f in filters if f.get("field") in _ORG_VIRTUAL_FIELD_NAMES]
    person_filters = [f for f in filters if f.get("field") not in _ORG_VIRTUAL_FIELD_NAMES]

    # Pre-filter by org-level criteria → get allowed person IDs
    allowed_person_ids: set[str] | None = None
    if org_filters:
        org_query = sb.table("organizations").select("id").eq("is_deleted", False)
        for f in org_filters:
            real_col = _ORG_VIRTUAL_TO_COLUMN.get(f["field"], f["field"])
            org_query = _apply_filter_to_query(org_query, real_col, f["operator"], f.get("value", ""))
        org_resp = org_query.limit(5000).execute()
        matching_org_ids = [str(o["id"]) for o in (org_resp.data or [])]
        if matching_org_ids:
            pol_resp = (
                sb.table("person_organization_links")
                .select("person_id")
                .in_("link_type", ["primary", "secondary"])
                .in_("organization_id", matching_org_ids)
                .execute()
            )
            allowed_person_ids = {str(p["person_id"]) for p in (pol_resp.data or [])}
        else:
            return []

    query = sb.table("people").select("id").eq("is_deleted", False).eq("do_not_contact", False)

    if allowed_person_ids is not None:
        if not allowed_person_ids:
            return []
        query = query.in_("id", list(allowed_person_ids))

    # Track not_in filters for post-query filtering
    not_in_filters = []
    for f in person_filters:
        if f["operator"] == "not_in":
            not_in_filters.append(f)
            continue
        query = _apply_filter_to_query(query, f["field"], f["operator"], f.get("value", ""))

    resp = query.limit(5000).execute()
    person_ids = [str(r["id"]) for r in (resp.data or [])]

    # Post-query filter for not_in (Supabase doesn't have clean not_in)
    if not_in_filters and person_ids:
        for f in not_in_filters:
            vals = f.get("value", [])
            if not isinstance(vals, list):
                vals = [v.strip() for v in str(vals).split(",") if v.strip()]
            # Re-query to get the field values for these people
            check_resp = sb.table("people").select(f"id, {f['field']}").in_("id", person_ids).limit(5000).execute()
            excluded = set()
            for row in (check_resp.data or []):
                row_val = row.get(f["field"])
                if isinstance(row_val, list):
                    if any(v in vals for v in row_val):
                        excluded.add(str(row["id"]))
                elif str(row_val or "") in vals:
                    excluded.add(str(row["id"]))
            person_ids = [pid for pid in person_ids if pid not in excluded]

    return person_ids


def _build_send_preview(list_id: str) -> dict:
    """Build a send preview with L2 superset inclusion and DNC/RFP Hold suppression.

    Returns dict with included, excluded_dnc, excluded_rfp_hold, totals, and L2 info.
    """
    sb = get_supabase()

    # 1. Get target list
    target_list = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", list_id)
        .maybe_single()
        .execute()
        .data
    )
    if not target_list:
        return {"included": [], "excluded_dnc": [], "excluded_rfp_hold": [],
                "total_members": 0, "sendable_count": 0, "l2_lists": [], "l2_member_count": 0}

    # 2. Get members — dynamic vs static
    if target_list.get("list_mode") == "dynamic":
        # Resolve dynamic members from filter criteria
        dynamic_ids = set(_resolve_dynamic_members(target_list.get("filter_criteria", {})))
        # Add manual members (explicitly added to dynamic list)
        manual_resp = (
            sb.table("distribution_list_members")
            .select("person_id")
            .eq("distribution_list_id", list_id)
            .eq("is_active", True)
            .eq("is_manual", True)
            .execute()
        )
        manual_ids = {str(m["person_id"]) for m in (manual_resp.data or [])}
        person_ids = dynamic_ids | manual_ids
    else:
        # Static list: get direct active members
        direct_resp = (
            sb.table("distribution_list_members")
            .select("person_id")
            .eq("distribution_list_id", list_id)
            .eq("is_active", True)
            .execute()
        )
        person_ids = {m["person_id"] for m in (direct_resp.data or [])}

    # 3. L2 superset inclusion: find L2 lists that reference this list (this list is L1)
    l2_lists_resp = (
        sb.table("distribution_lists")
        .select("id, list_name")
        .eq("l2_superset_of", list_id)
        .eq("is_active", True)
        .execute()
    )
    l2_lists = l2_lists_resp.data or []
    l2_member_count = 0

    for l2 in l2_lists:
        l2_members_resp = (
            sb.table("distribution_list_members")
            .select("person_id")
            .eq("distribution_list_id", l2["id"])
            .eq("is_active", True)
            .execute()
        )
        for m in (l2_members_resp.data or []):
            if m["person_id"] not in person_ids:
                person_ids.add(m["person_id"])
                l2_member_count += 1

    # 4. Batch-load people, org links, and org details (avoids N+1 queries)
    included = []
    excluded_dnc = []
    excluded_rfp_hold = []

    pid_list = list(person_ids)
    if not pid_list:
        return {
            "included": [], "excluded_dnc": [], "excluded_rfp_hold": [],
            "total_members": 0, "sendable_count": 0, "l2_lists": l2_lists, "l2_member_count": l2_member_count,
        }

    # Batch fetch people
    people_resp = (
        sb.table("people")
        .select("id, first_name, last_name, email, do_not_contact, is_deleted")
        .in_("id", pid_list)
        .execute()
    )
    people_map = {str(p["id"]): p for p in (people_resp.data or [])}

    # Batch fetch primary org links
    pol_resp = (
        sb.table("person_organization_links")
        .select("person_id, organization_id")
        .in_("person_id", pid_list)
        .eq("link_type", "primary")
        .execute()
    )
    person_org_map = {str(lnk["person_id"]): str(lnk["organization_id"]) for lnk in (pol_resp.data or [])}

    # Batch fetch org details
    org_ids_needed = list(set(person_org_map.values()))
    org_map = {}
    if org_ids_needed:
        orgs_resp = (
            sb.table("organizations")
            .select("id, company_name, rfp_hold")
            .in_("id", org_ids_needed)
            .execute()
        )
        org_map = {str(o["id"]): o for o in (orgs_resp.data or [])}

    for pid in pid_list:
        person = people_map.get(str(pid))
        if not person or person.get("is_deleted"):
            continue

        org_id = person_org_map.get(str(pid))
        org = org_map.get(org_id) if org_id else None
        org_name = org["company_name"] if org else None
        org_rfp_hold = org.get("rfp_hold", False) if org else False

        person_info = {
            "id": person["id"],
            "name": f"{person['first_name']} {person['last_name']}",
            "email": person.get("email"),
            "org_name": org_name,
        }

        if person.get("do_not_contact"):
            excluded_dnc.append({**person_info, "reason": "Do Not Contact"})
        elif org_rfp_hold:
            excluded_rfp_hold.append({**person_info, "reason": f"RFP Hold ({org_name or 'Unknown Org'})"})
        else:
            included.append(person_info)

    return {
        "included": sorted(included, key=lambda x: x["name"]),
        "excluded_dnc": sorted(excluded_dnc, key=lambda x: x["name"]),
        "excluded_rfp_hold": sorted(excluded_rfp_hold, key=lambda x: x["name"]),
        "total_members": len(person_ids),
        "sendable_count": len(included),
        "l2_lists": l2_lists,
        "l2_member_count": l2_member_count,
    }


def _load_form_context(sb, current_user, dist_list=None, errors=None):
    """Load all reference data needed for the distribution list form."""
    list_types = get_reference_data("distribution_list_type")
    brands = get_reference_data("brand")
    asset_classes = get_reference_data("asset_class")

    # L1 publication lists (for L2 superset dropdown)
    l1_lists_resp = (
        sb.table("distribution_lists")
        .select("id, list_name, asset_class")
        .eq("is_active", True)
        .eq("is_official", True)
        .eq("list_type", "publication")
        .is_("l2_superset_of", "null")
        .order("list_name")
        .execute()
    )
    l1_lists = l1_lists_resp.data or []

    return {
        "list_types": list_types,
        "brands": brands,
        "asset_classes": asset_classes,
        "l1_lists": l1_lists,
        "dist_list": dist_list,
        "errors": errors or [],
        "user": current_user,
    }


# ---------------------------------------------------------------------------
# PERSON SEARCH (HTMX autocomplete) — GET /distribution-lists/search-people
# ---------------------------------------------------------------------------

@router.get("/search-people", response_class=HTMLResponse)
async def search_people(
    request: Request,
    q: str = Query(""),
    list_id: str = Query(""),
    country: str = Query(""),
    rel_type: str = Query(""),
    fund: str = Query(""),
    mode: str = Query("dropdown"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX endpoint: return person search results for member add autocomplete.
    Excludes DNC people and people already active in the list.
    Supports optional filters: country, relationship type, fund."""
    has_filters = bool(country or rel_type or fund)
    if (not q or len(q) < 2) and not has_filters:
        return HTMLResponse("")

    sb = get_supabase()

    # --- Filter by org attributes if any filters are set ---
    person_id_filter = None
    if has_filters:
        # Find orgs matching country / relationship_type filters
        org_query = sb.table("organizations").select("id").eq("is_deleted", False)
        if country:
            org_query = org_query.eq("country", country)
        if rel_type:
            org_query = org_query.eq("relationship_type", rel_type)
        org_resp = org_query.execute()
        filtered_org_ids = [o["id"] for o in (org_resp.data or [])]

        # If fund filter, further restrict to orgs that have fund prospects for that fund
        if fund and filtered_org_ids:
            fp_resp = (
                sb.table("fund_prospects")
                .select("organization_id")
                .eq("fund_id", fund)
                .eq("is_deleted", False)
                .execute()
            )
            fp_org_ids = {str(fp["organization_id"]) for fp in (fp_resp.data or [])}
            filtered_org_ids = [oid for oid in filtered_org_ids if str(oid) in fp_org_ids]
        elif fund and not filtered_org_ids and not country and not rel_type:
            # Fund filter only, no country/rel_type
            fp_resp = (
                sb.table("fund_prospects")
                .select("organization_id")
                .eq("fund_id", fund)
                .eq("is_deleted", False)
                .execute()
            )
            filtered_org_ids = list({str(fp["organization_id"]) for fp in (fp_resp.data or [])})

        if not filtered_org_ids:
            return HTMLResponse('<div class="px-4 py-2 text-sm text-gray-400">No people match the selected filters</div>')

        # Get person IDs at those orgs
        pol_resp = (
            sb.table("person_organization_links")
            .select("person_id")
            .in_("organization_id", filtered_org_ids)
            .execute()
        )
        person_id_filter = list({str(r["person_id"]) for r in (pol_resp.data or [])})

        if not person_id_filter:
            return HTMLResponse('<div class="px-4 py-2 text-sm text-gray-400">No people match the selected filters</div>')

    # --- Search people by name (or return all matching filter if q is empty) ---
    if q and len(q) >= 2:
        query1 = (
            sb.table("people")
            .select("id, first_name, last_name, email, do_not_contact")
            .eq("is_deleted", False)
            .eq("do_not_contact", False)
            .ilike("last_name", f"%{q}%")
            .order("last_name")
            .limit(15)
        )
        if person_id_filter:
            query1 = query1.in_("id", person_id_filter)
        resp = query1.execute()

        # Also search by first name
        query2 = (
            sb.table("people")
            .select("id, first_name, last_name, email, do_not_contact")
            .eq("is_deleted", False)
            .eq("do_not_contact", False)
            .ilike("first_name", f"%{q}%")
            .order("last_name")
            .limit(15)
        )
        if person_id_filter:
            query2 = query2.in_("id", person_id_filter)
        resp2 = query2.execute()

        # Merge and deduplicate
        seen = set()
        people = []
        for p in (resp.data or []) + (resp2.data or []):
            if p["id"] not in seen:
                seen.add(p["id"])
                people.append(p)
    else:
        # No search text but filters are set — return people matching filters
        query = (
            sb.table("people")
            .select("id, first_name, last_name, email, do_not_contact")
            .eq("is_deleted", False)
            .eq("do_not_contact", False)
            .in_("id", person_id_filter)
            .order("last_name")
            .limit(25)
        )
        resp = query.execute()
        people = resp.data or []

    # Exclude people already active in this list
    if list_id and people:
        existing_resp = (
            sb.table("distribution_list_members")
            .select("person_id")
            .eq("distribution_list_id", list_id)
            .eq("is_active", True)
            .execute()
        )
        existing_ids = {m["person_id"] for m in (existing_resp.data or [])}
        people = [p for p in people if p["id"] not in existing_ids]

    if not people:
        if mode == "table":
            return HTMLResponse('<p class="text-sm text-gray-400 py-4 text-center">No matching people found. Try adjusting your filters.</p>')
        return HTMLResponse('<div class="px-4 py-2 text-sm text-gray-400">No matching people found</div>')

    # Enrich with primary org names (batch lookup for efficiency)
    person_ids_list = [p["id"] for p in people[:25]]
    pol_resp = (
        sb.table("person_organization_links")
        .select("person_id, organization_id")
        .in_("person_id", person_ids_list)
        .eq("link_type", "primary")
        .execute()
    )
    person_org_map = {str(r["person_id"]): str(r["organization_id"]) for r in (pol_resp.data or [])}
    org_ids = list(set(person_org_map.values()))
    org_names = {}
    if org_ids:
        orgs_resp = sb.table("organizations").select("id, company_name").in_("id", org_ids).execute()
        org_names = {str(o["id"]): o["company_name"] for o in (orgs_resp.data or [])}

    # --- TABLE MODE: return a full table for the people selector ---
    if mode == "table":
        rows = []
        for p in people[:25]:
            pid = str(p["id"])
            org_id = person_org_map.get(pid)
            org_name = org_names.get(org_id, "") if org_id else ""
            full_name = f"{p['first_name']} {p['last_name']}"
            email_str = p.get("email") or "—"

            rows.append(
                f'<tr class="hover:bg-gray-50" id="person-row-{pid}">'
                f'<td class="px-4 py-2.5 text-sm font-medium text-gray-900">{full_name}</td>'
                f'<td class="px-4 py-2.5 text-sm text-gray-600">{email_str}</td>'
                f'<td class="px-4 py-2.5 text-sm text-gray-600">{org_name or "—"}</td>'
                f'<td class="px-4 py-2.5 text-sm">'
                f'<button type="button" '
                f'hx-post="/distribution-lists/{list_id}/members/add" '
                f'hx-vals=\'{{"person_id": "{pid}"}}\' '
                f'hx-target="#person-row-{pid}" '
                f'hx-swap="outerHTML" '
                f'class="inline-flex items-center px-3 py-1 text-xs font-medium text-white bg-brand-500 rounded hover:bg-brand-600">'
                f'+ Add</button>'
                f'</td>'
                f'</tr>'
            )

        count_note = f'<p class="text-xs text-gray-400 mt-2">Showing {min(len(people), 25)} of {len(people)} results</p>' if len(people) > 25 else f'<p class="text-xs text-gray-400 mt-2">{len(people)} result{"s" if len(people) != 1 else ""} found</p>'

        table_html = (
            f'<div class="overflow-x-auto border border-gray-200 rounded-lg">'
            f'<table class="min-w-full divide-y divide-gray-200">'
            f'<thead class="bg-gray-50">'
            f'<tr>'
            f'<th class="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>'
            f'<th class="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Email</th>'
            f'<th class="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Organization</th>'
            f'<th class="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>'
            f'</tr>'
            f'</thead>'
            f'<tbody class="divide-y divide-gray-200">'
            + "\n".join(rows)
            + f'</tbody></table></div>'
            + count_note
        )
        return HTMLResponse(table_html)

    # --- DROPDOWN MODE (legacy): return autocomplete items ---
    html_parts = []
    for p in people[:10]:
        pid = str(p["id"])
        org_id = person_org_map.get(pid)
        org_name = org_names.get(org_id, "") if org_id else ""
        full_name = f"{p['first_name']} {p['last_name']}"
        email_str = p.get("email") or ""

        html_parts.append(
            f'<div class="flex items-center justify-between px-4 py-2 hover:bg-brand-50">'
            f'<div>'
            f'<div class="text-sm font-medium text-gray-900">{full_name}</div>'
            f'<div class="text-xs text-gray-400">{email_str}{" — " + org_name if org_name else ""}</div>'
            f'</div>'
            f'<button type="button" '
            f'hx-post="/distribution-lists/{list_id}/members/add" '
            f'hx-vals=\'{{"person_id": "{p["id"]}"}}\' '
            f'hx-target="#members-content" '
            f'hx-swap="innerHTML" '
            f'class="ml-2 px-2 py-1 text-xs font-medium text-brand-600 bg-brand-50 rounded hover:bg-brand-100">'
            f'Add</button>'
            f'</div>'
        )
    return HTMLResponse("\n".join(html_parts))


# ---------------------------------------------------------------------------
# CREATE FORM — GET /distribution-lists/new  (must be before /{list_id})
# ---------------------------------------------------------------------------

@router.get("/new", response_class=HTMLResponse)
async def new_list_form(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the new distribution list form."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])
    sb = get_supabase()
    context = _load_form_context(sb, current_user)
    context["request"] = request
    return templates.TemplateResponse("distribution_lists/form.html", context)


# ---------------------------------------------------------------------------
# LIST — GET /distribution-lists
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def list_distribution_lists(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List distribution lists with filtering, search, sorting, and pagination."""
    params = dict(request.query_params)
    list_view = params.get("list_view", "custom")  # 'custom' or 'official'

    extra_filters = {
        "_user_id": str(current_user.id),
        "_user_role": current_user.role,
        "_list_view": list_view,
    }
    ctx = build_grid_context("distribution_list", request, current_user, base_url="/distribution-lists", extra_filters=extra_filters)

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("components/_grid.html", {"request": request, **ctx})

    list_types = get_reference_data("list_type")
    brands = get_reference_data("brand")
    asset_classes = get_reference_data("asset_class")

    ctx.update({
        "user": current_user,
        "total_count": ctx["pagination"]["total"],
        "search": ctx["filters"].get("q", ""),
        "list_type": ctx["filters"].get("type", ""),
        "brand": ctx["filters"].get("brand", ""),
        "asset_class": ctx["filters"].get("asset_class", ""),
        "list_view": list_view,
        "list_types": list_types,
        "brands": brands,
        "asset_classes": asset_classes,
        "lists": ctx["rows"],
    })
    return templates.TemplateResponse("distribution_lists/list.html", {"request": request, **ctx})


# ---------------------------------------------------------------------------
# FILTER EDITOR — GET /distribution-lists/{list_id}/filter-editor
# feedback: [padelsbach] DL creation via people grid filtering
# ---------------------------------------------------------------------------

@router.get("/{list_id}/filter-editor", response_class=HTMLResponse)
async def filter_editor(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX partial: filter-builder form for defining dynamic list filter criteria."""
    sb = get_supabase()
    dist_list = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .maybe_single()
        .execute()
        .data
    )
    if not dist_list:
        raise HTTPException(status_code=404, detail="List not found")

    if not _can_edit_list(dist_list, current_user):
        return HTMLResponse('<p class="text-sm text-red-600">Permission denied.</p>')

    # Load filter fields for the builder
    filter_fields = _build_filter_fields()

    # Parse existing filter_criteria into new format (handle old format too)
    existing_criteria = dist_list.get("filter_criteria") or {}
    if existing_criteria and "filters" not in existing_criteria:
        existing_criteria = _convert_old_to_new_format(existing_criteria)
    existing_filters = existing_criteria.get("filters", [])

    context = {
        "request": request,
        "user": current_user,
        "list_id": str(list_id),
        "dist_list": dist_list,
        "filter_fields": filter_fields,
        "existing_filters": existing_filters,
        "operators_by_type": _OPERATORS_BY_TYPE,
    }
    return templates.TemplateResponse("distribution_lists/_filter_editor.html", context)


@router.post("/{list_id}/preview-filter-count", response_class=HTMLResponse)
async def preview_filter_count(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return the count of people matching the given filter criteria."""
    body = await request.json()
    filters = body.get("filters", [])
    if not filters:
        return HTMLResponse('<span class="text-gray-400">Add filters to see matching count</span>')
    try:
        count = len(_resolve_dynamic_members({"filters": filters}))
    except Exception:
        return HTMLResponse('<span class="text-red-500">Error evaluating filters</span>')
    return HTMLResponse(
        f'<span class="text-brand-600 font-semibold">{count} people match</span>'
    )


@router.post("/{list_id}/save-filters", response_class=HTMLResponse)
async def save_list_filters(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Save filter criteria for a dynamic distribution list."""
    sb = get_supabase()
    dist_list = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .maybe_single()
        .execute()
        .data
    )
    if not dist_list:
        raise HTTPException(status_code=404, detail="List not found")
    if not _can_edit_list(dist_list, current_user):
        raise HTTPException(status_code=403, detail="Permission denied")

    body = await request.json()
    filters = body.get("filters", [])

    if not filters:
        return HTMLResponse(
            '<div class="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">'
            'At least one filter is required to save.'
            '</div>'
        )

    filter_criteria = {"filters": filters}

    # Resolve count before saving so user can see impact
    member_count = len(_resolve_dynamic_members(filter_criteria))

    sb.table("distribution_lists").update({
        "filter_criteria": filter_criteria,
        "list_mode": "dynamic",
    }).eq("id", str(list_id)).execute()

    return HTMLResponse(
        f'<div class="bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-green-700">'
        f'Filters saved. {member_count} people match the current criteria.'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# DETAIL — GET /distribution-lists/{list_id}
# ---------------------------------------------------------------------------

@router.get("/{list_id}", response_class=HTMLResponse)
async def get_distribution_list(
    request: Request,
    list_id: UUID,
    tab: str = Query("members"),
    m_page: int = Query(1, ge=1, alias="m_page"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Distribution list detail page with tabs: members, send_history."""
    sb = get_supabase()

    resp = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    dist_list = resp.data
    if not dist_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    # Owner name
    owner_name = get_user_name(str(dist_list["owner_id"])) if dist_list.get("owner_id") else None

    # L2 superset info
    l1_list = None
    if dist_list.get("l2_superset_of"):
        l1_resp = (
            sb.table("distribution_lists")
            .select("id, list_name")
            .eq("id", dist_list["l2_superset_of"])
            .maybe_single()
            .execute()
        )
        l1_list = l1_resp.data if l1_resp.data else None

    # Reverse lookup: find L2 lists that reference this list (if this is L1)
    l2_lists_resp = (
        sb.table("distribution_lists")
        .select("id, list_name")
        .eq("l2_superset_of", str(list_id))
        .eq("is_active", True)
        .execute()
    )
    l2_lists = l2_lists_resp.data or []

    # Member count
    member_count = _get_member_count(str(list_id))

    # Members tab data (paginated)
    m_page_size = 25
    m_offset = (m_page - 1) * m_page_size
    members_resp = (
        sb.table("distribution_list_members")
        .select("id, person_id, coverage_owner_id, joined_at", count="exact")
        .eq("distribution_list_id", str(list_id))
        .eq("is_active", True)
        .order("joined_at", desc=True)
        .range(m_offset, m_offset + m_page_size - 1)
        .execute()
    )
    members = members_resp.data or []
    members_total = members_resp.count or 0
    members_total_pages = max(1, (members_total + m_page_size - 1) // m_page_size)

    # Enrich members with person info
    for m in members:
        person = _get_person_with_org(m["person_id"])
        if person:
            m["person_name"] = person["full_name"]
            m["person_email"] = person.get("email")
            m["person_org"] = person.get("org_name")
        else:
            m["person_name"] = "Unknown"
            m["person_email"] = None
            m["person_org"] = None
        if m.get("coverage_owner_id"):
            m["coverage_owner_name"] = get_user_name(str(m["coverage_owner_id"]))
        else:
            m["coverage_owner_name"] = None

    # Send history
    history_resp = (
        sb.table("send_history")
        .select("id, sent_by, sent_at, subject, recipient_count, status")
        .eq("distribution_list_id", str(list_id))
        .order("sent_at", desc=True)
        .limit(50)
        .execute()
    )
    send_history = history_resp.data or []
    for sh in send_history:
        if sh.get("sent_by"):
            sh["sender_name"] = get_user_name(str(sh["sent_by"]))
        else:
            sh["sender_name"] = "Unknown"

    # Reference data for type labels
    type_labels = {t["value"]: t["label"] for t in get_reference_data("distribution_list_type")}

    # Load filter options for member search
    countries = (
        sb.table("reference_data")
        .select("value, label")
        .eq("category", "country")
        .eq("is_active", True)
        .order("label")
        .execute()
        .data or []
    )
    relationship_types = (
        sb.table("reference_data")
        .select("value, label")
        .eq("category", "relationship_type")
        .eq("is_active", True)
        .order("label")
        .execute()
        .data or []
    )
    funds = (
        sb.table("funds")
        .select("id, fund_name, ticker")
        .eq("is_active", True)
        .order("fund_name")
        .execute()
        .data or []
    )

    # Dynamic members (for dynamic lists): resolve and enrich first page
    dynamic_members = []
    dynamic_total = 0
    if dist_list.get("list_mode") == "dynamic":
        dynamic_ids = _resolve_dynamic_members(dist_list.get("filter_criteria", {}))
        dynamic_total = len(dynamic_ids)
        # Paginate: show first 25 dynamic members
        dm_page_ids = dynamic_ids[:25]
        if dm_page_ids:
            dm_people_resp = (
                sb.table("people")
                .select("id, first_name, last_name, email")
                .in_("id", dm_page_ids)
                .execute()
            )
            dm_people_map = {str(p["id"]): p for p in (dm_people_resp.data or [])}
            # Batch resolve primary orgs
            dm_pol_resp = (
                sb.table("person_organization_links")
                .select("person_id, organization_id")
                .in_("person_id", dm_page_ids)
                .eq("link_type", "primary")
                .execute()
            )
            dm_org_map_local = {str(lnk["person_id"]): str(lnk["organization_id"]) for lnk in (dm_pol_resp.data or [])}
            dm_org_ids = list(set(dm_org_map_local.values()))
            dm_orgs = {}
            if dm_org_ids:
                dm_orgs_resp = sb.table("organizations").select("id, company_name").in_("id", dm_org_ids).execute()
                dm_orgs = {str(o["id"]): o["company_name"] for o in (dm_orgs_resp.data or [])}
            for pid in dm_page_ids:
                person = dm_people_map.get(str(pid))
                if person:
                    org_id = dm_org_map_local.get(str(pid))
                    dynamic_members.append({
                        "person_id": person["id"],
                        "person_name": f"{person['first_name']} {person['last_name']}",
                        "person_email": person.get("email"),
                        "person_org": dm_orgs.get(org_id) if org_id else None,
                    })

    context = {
        "request": request,
        "user": current_user,
        "dist_list": dist_list,
        "owner_name": owner_name,
        "l1_list": l1_list,
        "l2_lists": l2_lists,
        "member_count": member_count,
        "members": members,
        "members_total": members_total,
        "members_total_pages": members_total_pages,
        "m_page": m_page,
        "dynamic_members": dynamic_members,
        "dynamic_total": dynamic_total,
        "send_history": send_history,
        "type_labels": type_labels,
        "active_tab": tab,
        "can_edit": _can_edit_list(dist_list, current_user),
        "can_manage": _can_manage_members(dist_list, current_user),
        "can_send": _can_send(dist_list, current_user),
        "countries": countries,
        "relationship_types": relationship_types,
        "funds": funds,
    }

    # Only return tab partial for explicit HTMX tab clicks, not hx-boost page navigations
    if request.headers.get("HX-Request") and tab:
        template_name = f"distribution_lists/_tab_{tab}.html"
        return templates.TemplateResponse(template_name, context)
    return templates.TemplateResponse("distribution_lists/detail.html", context)


# ---------------------------------------------------------------------------
# SEND PREVIEW — GET /distribution-lists/{list_id}/send-preview
# ---------------------------------------------------------------------------

@router.get("/{list_id}/send-preview", response_class=HTMLResponse)
async def send_preview(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX endpoint: build and return send preview with DNC/RFP Hold suppression."""
    sb = get_supabase()
    dist_list = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .maybe_single()
        .execute()
        .data
    )
    if not dist_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    preview = _build_send_preview(str(list_id))

    context = {
        "request": request,
        "user": current_user,
        "dist_list": dist_list,
        "preview": preview,
        "can_send": _can_send(dist_list, current_user),
    }
    return templates.TemplateResponse("distribution_lists/_send_preview.html", context)


# ---------------------------------------------------------------------------
# SEND — POST /distribution-lists/{list_id}/send
# ---------------------------------------------------------------------------

@router.post("/{list_id}/send", response_class=HTMLResponse)
async def execute_send(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Execute a send: build current snapshot, save to send_history.
    Actual email delivery via Power Automate is Phase 2."""
    sb = get_supabase()
    dist_list = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .maybe_single()
        .execute()
        .data
    )
    if not dist_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    if not _can_send(dist_list, current_user):
        raise HTTPException(status_code=403, detail="You do not have permission to send from this list")

    form = await request.form()
    subject = (form.get("subject") or "").strip()
    body = (form.get("body") or "").strip()

    if not subject:
        preview = _build_send_preview(str(list_id))
        context = {
            "request": request,
            "user": current_user,
            "dist_list": dist_list,
            "preview": preview,
            "can_send": True,
            "errors": ["Subject is required."],
        }
        return templates.TemplateResponse("distribution_lists/_send_preview.html", context)

    # Build fresh snapshot
    preview = _build_send_preview(str(list_id))
    recipient_snapshot = json.dumps(preview["included"])

    # Save send history
    sb.table("send_history").insert({
        "distribution_list_id": str(list_id),
        "sent_by": str(current_user.id),
        "subject": subject,
        "body": body or None,
        "recipient_count": preview["sendable_count"],
        "recipient_snapshot": recipient_snapshot,
        "status": "sent",
    }).execute()

    log_field_change(
        "distribution_list", str(list_id), "send_executed",
        None, f"Sent to {preview['sendable_count']} recipients: {subject}",
        current_user.id,
    )

    if request.headers.get("HX-Request"):
        return HTMLResponse(
            f'<div class="rounded-md bg-green-50 border border-green-200 p-4">'
            f'<p class="text-sm text-green-700">Send recorded successfully. '
            f'{preview["sendable_count"]} recipients. '
            f'<a href="/distribution-lists/{list_id}" class="font-medium underline">Back to list</a></p></div>'
        )
    return RedirectResponse(url=f"/distribution-lists/{list_id}", status_code=303)


# ---------------------------------------------------------------------------
# SEND HISTORY DETAIL — GET /distribution-lists/{list_id}/send-history/{send_id}
# ---------------------------------------------------------------------------

@router.get("/{list_id}/send-history/{send_id}", response_class=HTMLResponse)
async def get_send_detail(
    request: Request,
    list_id: UUID,
    send_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return send history detail with recipient snapshot."""
    sb = get_supabase()
    resp = (
        sb.table("send_history")
        .select("*")
        .eq("id", str(send_id))
        .eq("distribution_list_id", str(list_id))
        .maybe_single()
        .execute()
    )
    send = resp.data
    if not send:
        raise HTTPException(status_code=404, detail="Send record not found")

    send["sender_name"] = get_user_name(str(send["sent_by"])) if send.get("sent_by") else "Unknown"

    # Parse recipient snapshot
    try:
        recipients = json.loads(send["recipient_snapshot"]) if isinstance(send["recipient_snapshot"], str) else send["recipient_snapshot"]
    except (json.JSONDecodeError, TypeError):
        recipients = []

    html = (
        f'<div class="space-y-4">'
        f'<div class="grid grid-cols-2 gap-4">'
        f'<div><dt class="text-xs font-medium text-gray-500 uppercase">Subject</dt>'
        f'<dd class="mt-1 text-sm text-gray-900">{send["subject"]}</dd></div>'
        f'<div><dt class="text-xs font-medium text-gray-500 uppercase">Sent By</dt>'
        f'<dd class="mt-1 text-sm text-gray-900">{send["sender_name"]}</dd></div>'
        f'<div><dt class="text-xs font-medium text-gray-500 uppercase">Date</dt>'
        f'<dd class="mt-1 text-sm text-gray-900">{send["sent_at"][:16] if send.get("sent_at") else "—"}</dd></div>'
        f'<div><dt class="text-xs font-medium text-gray-500 uppercase">Recipients</dt>'
        f'<dd class="mt-1 text-sm text-gray-900">{send["recipient_count"]}</dd></div>'
        f'</div>'
    )
    if send.get("body"):
        html += f'<div><dt class="text-xs font-medium text-gray-500 uppercase">Body</dt><dd class="mt-1 text-sm text-gray-900 whitespace-pre-wrap">{send["body"]}</dd></div>'

    if recipients:
        html += '<div><dt class="text-xs font-medium text-gray-500 uppercase mb-2">Recipient Snapshot</dt>'
        html += '<div class="max-h-60 overflow-auto border border-gray-200 rounded">'
        html += '<table class="min-w-full divide-y divide-gray-200 text-xs">'
        html += '<thead class="bg-gray-50"><tr><th class="px-3 py-2 text-left">Name</th><th class="px-3 py-2 text-left">Email</th><th class="px-3 py-2 text-left">Org</th></tr></thead><tbody>'
        for r in recipients:
            html += f'<tr class="border-t"><td class="px-3 py-1">{r.get("name", "—")}</td><td class="px-3 py-1">{r.get("email", "—")}</td><td class="px-3 py-1">{r.get("org_name", "—")}</td></tr>'
        html += '</tbody></table></div></div>'

    html += '</div>'
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# CREATE — POST /distribution-lists
# ---------------------------------------------------------------------------

@router.post("/", response_class=HTMLResponse)
async def create_distribution_list(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new distribution list."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    form = await request.form()
    list_data = _build_list_data_from_form(form)

    # Only admin can create official lists
    if list_data.get("is_official") and current_user.role != "admin":
        list_data["is_official"] = False

    errors = _validate_list_fields(list_data)
    if errors:
        sb = get_supabase()
        context = _load_form_context(sb, current_user, dist_list=list_data, errors=errors)
        context["request"] = request
        return templates.TemplateResponse("distribution_lists/form.html", context)

    # Set system fields
    list_data["owner_id"] = str(current_user.id)
    list_data["created_by"] = str(current_user.id)

    sb = get_supabase()
    resp = sb.table("distribution_lists").insert(list_data).execute()

    if resp.data:
        new_list = resp.data[0]
        log_field_change("distribution_list", str(new_list["id"]), "_created", None, "record created", current_user.id)
        return RedirectResponse(url=f"/distribution-lists/{new_list['id']}", status_code=303)

    raise HTTPException(status_code=500, detail="Failed to create distribution list")


# ---------------------------------------------------------------------------
# EDIT FORM — GET /distribution-lists/{list_id}/edit
# ---------------------------------------------------------------------------

@router.get("/{list_id}/edit", response_class=HTMLResponse)
async def edit_list_form(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the edit distribution list form."""
    sb = get_supabase()
    resp = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    dist_list = resp.data
    if not dist_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    if not _can_edit_list(dist_list, current_user):
        raise HTTPException(status_code=403, detail="You do not have permission to edit this list")

    context = _load_form_context(sb, current_user, dist_list=dist_list)
    context["request"] = request
    return templates.TemplateResponse("distribution_lists/form.html", context)


# ---------------------------------------------------------------------------
# UPDATE — POST /distribution-lists/{list_id}
# ---------------------------------------------------------------------------

@router.post("/{list_id}", response_class=HTMLResponse)
async def update_distribution_list(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an existing distribution list."""
    sb = get_supabase()

    old_resp = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    old_list = old_resp.data
    if not old_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    if not _can_edit_list(old_list, current_user):
        raise HTTPException(status_code=403, detail="You do not have permission to edit this list")

    form = await request.form()
    list_data = _build_list_data_from_form(form)

    # Only admin can set official
    if list_data.get("is_official") and current_user.role != "admin":
        list_data["is_official"] = old_list.get("is_official", False)

    errors = _validate_list_fields(list_data)
    if errors:
        merged = {**old_list, **list_data}
        context = _load_form_context(sb, current_user, dist_list=merged, errors=errors)
        context["request"] = request
        return templates.TemplateResponse("distribution_lists/form.html", context)

    # Audit log
    audit_changes("distribution_list", str(list_id), old_list, list_data, current_user.id)

    # Update
    sb.table("distribution_lists").update(list_data).eq("id", str(list_id)).execute()

    return RedirectResponse(url=f"/distribution-lists/{list_id}", status_code=303)


# ---------------------------------------------------------------------------
# ARCHIVE (soft-deactivate) — POST /distribution-lists/{list_id}/archive
# ---------------------------------------------------------------------------

@router.post("/{list_id}/archive", response_class=HTMLResponse)
async def archive_distribution_list(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-deactivate a distribution list."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    sb.table("distribution_lists").update({"is_active": False}).eq("id", str(list_id)).execute()
    log_field_change("distribution_list", str(list_id), "is_active", True, False, current_user.id)

    if request.headers.get("HX-Request"):
        return HTMLResponse('<p class="text-sm text-green-600">Distribution list archived.</p>')
    return RedirectResponse(url="/distribution-lists", status_code=303)


# ---------------------------------------------------------------------------
# ADD MEMBER — POST /distribution-lists/{list_id}/members/add
# ---------------------------------------------------------------------------

@router.post("/{list_id}/members/add", response_class=HTMLResponse)
async def add_member(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Add a person to the distribution list. Handles reactivation of removed members."""
    sb = get_supabase()

    # Verify list exists
    dist_list = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .maybe_single()
        .execute()
        .data
    )
    if not dist_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    if not _can_manage_members(dist_list, current_user):
        return HTMLResponse('<div class="text-sm text-red-600 p-2">Permission denied.</div>')

    form = await request.form()
    person_id = (form.get("person_id") or "").strip()
    if not person_id:
        return HTMLResponse('<div class="text-sm text-red-600 p-2">No person selected.</div>')

    # Validate person
    person = _get_person_with_org(person_id)
    if not person:
        return HTMLResponse('<div class="text-sm text-red-600 p-2">Person not found.</div>')
    if person.get("is_deleted"):
        return HTMLResponse('<div class="text-sm text-red-600 p-2">Cannot add: person is archived.</div>')
    if person.get("do_not_contact"):
        return HTMLResponse('<div class="text-sm text-red-600 p-2">Cannot add: person is flagged as Do Not Contact.</div>')

    # Check for existing membership (including inactive)
    existing = (
        sb.table("distribution_list_members")
        .select("id, is_active")
        .eq("distribution_list_id", str(list_id))
        .eq("person_id", person_id)
        .execute()
    )

    now_str = datetime.now(timezone.utc).isoformat()

    if existing.data:
        row = existing.data[0]
        if row["is_active"]:
            return HTMLResponse('<div class="text-sm text-yellow-600 p-2">This person is already a member.</div>')
        # Reactivate
        sb.table("distribution_list_members").update({
            "is_active": True,
            "joined_at": now_str,
            "removed_at": None,
            "removal_reason": None,
            "coverage_owner_id": person.get("coverage_owner"),
        }).eq("id", row["id"]).execute()
    else:
        # Insert new membership
        sb.table("distribution_list_members").insert({
            "distribution_list_id": str(list_id),
            "person_id": person_id,
            "coverage_owner_id": person.get("coverage_owner"),
            "is_active": True,
        }).execute()

    log_field_change(
        "distribution_list", str(list_id), "member_added",
        None, f"{person['full_name']} ({person_id})",
        current_user.id,
    )

    # If targeted at a specific person row (table mode), return an "Added" row
    # feedback: [padelsbach] trigger members list refresh when adding a member
    hx_target = request.headers.get("HX-Target", "")
    if hx_target.startswith("person-row-"):
        full_name = person["full_name"]
        resp = HTMLResponse(
            f'<tr class="bg-green-50">'
            f'<td class="px-4 py-2.5 text-sm font-medium text-green-700">{full_name}</td>'
            f'<td colspan="3" class="px-4 py-2.5 text-sm text-green-600">'
            f'<svg class="inline h-4 w-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>'
            f'Added to list</td>'
            f'</tr>'
        )
        resp.headers["HX-Trigger"] = "membersUpdated"
        return resp

    # Return updated members tab content
    return await _render_members_tab(request, str(list_id), current_user, dist_list)


# ---------------------------------------------------------------------------
# REMOVE MEMBER — POST /distribution-lists/{list_id}/members/{member_id}/remove
# ---------------------------------------------------------------------------

@router.post("/{list_id}/members/{member_id}/remove", response_class=HTMLResponse)
async def remove_member(
    request: Request,
    list_id: UUID,
    member_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-remove a member from the distribution list."""
    sb = get_supabase()

    dist_list = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .maybe_single()
        .execute()
        .data
    )
    if not dist_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    if not _can_manage_members(dist_list, current_user):
        return HTMLResponse('<div class="text-sm text-red-600 p-2">Permission denied.</div>')

    # Get member info for audit log before removing
    member_resp = (
        sb.table("distribution_list_members")
        .select("id, person_id")
        .eq("id", str(member_id))
        .eq("distribution_list_id", str(list_id))
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    if not member_resp.data:
        return HTMLResponse('<div class="text-sm text-red-600 p-2">Member not found.</div>')

    member = member_resp.data
    person = _get_person_with_org(member["person_id"])
    person_label = person["full_name"] if person else member["person_id"]

    now_str = datetime.now(timezone.utc).isoformat()

    # Soft-remove
    sb.table("distribution_list_members").update({
        "is_active": False,
        "removed_at": now_str,
        "removal_reason": "manual",
    }).eq("id", str(member_id)).execute()

    log_field_change(
        "distribution_list", str(list_id), "member_removed",
        f"{person_label} ({member['person_id']})", None,
        current_user.id,
    )

    # Return updated members tab content
    return await _render_members_tab(request, str(list_id), current_user, dist_list)


# ---------------------------------------------------------------------------
# Helper: render members tab (reused after add/remove)
# ---------------------------------------------------------------------------

async def _render_members_tab(
    request: Request,
    list_id: str,
    current_user: CurrentUser,
    dist_list: dict,
    m_page: int = 1,
) -> HTMLResponse:
    """Render the members tab partial."""
    sb = get_supabase()
    m_page_size = 25
    m_offset = (m_page - 1) * m_page_size

    members_resp = (
        sb.table("distribution_list_members")
        .select("id, person_id, coverage_owner_id, joined_at", count="exact")
        .eq("distribution_list_id", list_id)
        .eq("is_active", True)
        .order("joined_at", desc=True)
        .range(m_offset, m_offset + m_page_size - 1)
        .execute()
    )
    members = members_resp.data or []
    members_total = members_resp.count or 0
    members_total_pages = max(1, (members_total + m_page_size - 1) // m_page_size)

    for m in members:
        person = _get_person_with_org(m["person_id"])
        if person:
            m["person_name"] = person["full_name"]
            m["person_email"] = person.get("email")
            m["person_org"] = person.get("org_name")
        else:
            m["person_name"] = "Unknown"
            m["person_email"] = None
            m["person_org"] = None
        if m.get("coverage_owner_id"):
            m["coverage_owner_name"] = get_user_name(str(m["coverage_owner_id"]))
        else:
            m["coverage_owner_name"] = None

    # Load filter options for member search
    countries = (
        sb.table("reference_data")
        .select("value, label")
        .eq("category", "country")
        .eq("is_active", True)
        .order("label")
        .execute()
        .data or []
    )
    relationship_types = (
        sb.table("reference_data")
        .select("value, label")
        .eq("category", "relationship_type")
        .eq("is_active", True)
        .order("label")
        .execute()
        .data or []
    )
    funds = (
        sb.table("funds")
        .select("id, fund_name, ticker")
        .eq("is_active", True)
        .order("fund_name")
        .execute()
        .data or []
    )

    context = {
        "request": request,
        "user": current_user,
        "dist_list": dist_list,
        "members": members,
        "members_total": members_total,
        "members_total_pages": members_total_pages,
        "m_page": m_page,
        "member_count": members_total,
        "can_manage": _can_manage_members(dist_list, current_user),
        "countries": countries,
        "relationship_types": relationship_types,
        "funds": funds,
    }
    return templates.TemplateResponse("distribution_lists/_tab_members.html", context)


# ---------------------------------------------------------------------------
# REMOVE MEMBER BY PERSON ID — POST /distribution-lists/{list_id}/remove-member
# (Called from person detail page DL tab — accepts person_id in form data)
# ---------------------------------------------------------------------------

@router.post("/{list_id}/remove-member", response_class=HTMLResponse)
async def remove_member_by_person(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Remove a person from a distribution list given list_id + person_id.
    Used from person detail page distribution lists tab."""
    require_role(current_user, ["admin", "standard_user"])

    sb = get_supabase()
    form = await request.form()
    person_id = (form.get("person_id") or "").strip()
    if not person_id:
        return HTMLResponse('<div class="text-sm text-red-600 p-2">No person specified.</div>')

    # Find the active membership
    member_resp = (
        sb.table("distribution_list_members")
        .select("id, person_id")
        .eq("distribution_list_id", str(list_id))
        .eq("person_id", person_id)
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    if not member_resp.data:
        return HTMLResponse('<div class="text-sm text-yellow-600 p-2">Membership not found or already removed.</div>')

    member = member_resp.data
    person = _get_person_with_org(person_id)
    person_label = person["full_name"] if person else person_id

    now_str = datetime.now(timezone.utc).isoformat()

    # Soft-remove
    sb.table("distribution_list_members").update({
        "is_active": False,
        "removed_at": now_str,
        "removal_reason": "manual",
    }).eq("id", member["id"]).execute()

    log_field_change(
        "distribution_list", str(list_id), "member_removed",
        f"{person_label} ({person_id})", None,
        current_user.id,
    )

    # Return updated distribution list memberships for this person
    # (reload the person's DL tab content)
    dl_resp = (
        sb.table("distribution_list_members")
        .select("id, joined_at, is_active, distribution_list:distribution_lists(id, list_name, list_type, asset_class, brand)")
        .eq("person_id", person_id)
        .eq("is_active", True)
        .execute()
    )
    distribution_lists = dl_resp.data or []

    # Load person for context
    person_resp = (
        sb.table("people")
        .select("*")
        .eq("id", person_id)
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    person_data = person_resp.data or {}

    context = {
        "request": request,
        "user": current_user,
        "person": person_data,
        "distribution_lists": distribution_lists,
    }
    return templates.TemplateResponse("people/_tab_distribution_lists.html", context)


# ---------------------------------------------------------------------------
# ADD ALL FILTERED — POST /distribution-lists/{list_id}/add-filtered
# (Bulk add all people matching current search filters)
# ---------------------------------------------------------------------------

@router.post("/{list_id}/add-filtered", response_class=HTMLResponse)
async def add_filtered_members(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Bulk add all people matching the current search/filter criteria to a distribution list.
    Skips DNC people and already-active members. Returns count of additions."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()

    # Verify list exists
    dist_list = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .maybe_single()
        .execute()
        .data
    )
    if not dist_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    if not _can_manage_members(dist_list, current_user):
        return HTMLResponse('<div class="text-sm text-red-600 p-2">Permission denied.</div>')

    form = await request.form()
    country = (form.get("country") or "").strip()
    rel_type = (form.get("rel_type") or "").strip()
    fund = (form.get("fund") or "").strip()
    q = (form.get("q") or "").strip()

    has_filters = bool(country or rel_type or fund)
    if not has_filters and (not q or len(q) < 2):
        return HTMLResponse(
            '<div class="rounded-md bg-yellow-50 border border-yellow-200 p-3 mt-2">'
            '<p class="text-sm text-yellow-700">Please set at least one filter or search term before using Add All.</p>'
            '</div>'
        )

    # --- Step 1: Find matching people (same logic as search_people) ---
    person_id_filter = None
    if has_filters:
        org_query = sb.table("organizations").select("id").eq("is_deleted", False)
        if country:
            org_query = org_query.eq("country", country)
        if rel_type:
            org_query = org_query.eq("relationship_type", rel_type)
        org_resp = org_query.execute()
        filtered_org_ids = [o["id"] for o in (org_resp.data or [])]

        if fund and filtered_org_ids:
            # Check leads with lead_type='fundraise' for fund filter
            fp_resp = (
                sb.table("leads")
                .select("organization_id")
                .eq("fund_id", fund)
                .eq("lead_type", "fundraise")
                .eq("is_deleted", False)
                .execute()
            )
            fp_org_ids = {str(fp["organization_id"]) for fp in (fp_resp.data or [])}
            # Also check legacy fund_prospects table
            fp_legacy = (
                sb.table("fund_prospects")
                .select("organization_id")
                .eq("fund_id", fund)
                .eq("is_deleted", False)
                .execute()
            )
            fp_org_ids.update({str(fp["organization_id"]) for fp in (fp_legacy.data or [])})
            filtered_org_ids = [oid for oid in filtered_org_ids if str(oid) in fp_org_ids]
        elif fund and not filtered_org_ids and not country and not rel_type:
            fp_resp = (
                sb.table("leads")
                .select("organization_id")
                .eq("fund_id", fund)
                .eq("lead_type", "fundraise")
                .eq("is_deleted", False)
                .execute()
            )
            filtered_org_ids = list({str(fp["organization_id"]) for fp in (fp_resp.data or [])})
            fp_legacy = (
                sb.table("fund_prospects")
                .select("organization_id")
                .eq("fund_id", fund)
                .eq("is_deleted", False)
                .execute()
            )
            filtered_org_ids.extend(list({str(fp["organization_id"]) for fp in (fp_legacy.data or [])}))
            filtered_org_ids = list(set(filtered_org_ids))

        if not filtered_org_ids:
            return HTMLResponse(
                '<div class="rounded-md bg-yellow-50 border border-yellow-200 p-3 mt-2">'
                '<p class="text-sm text-yellow-700">No people matched the selected filters. 0 members added.</p>'
                '</div>'
            )

        pol_resp = (
            sb.table("person_organization_links")
            .select("person_id")
            .in_("organization_id", filtered_org_ids)
            .execute()
        )
        person_id_filter = list({str(r["person_id"]) for r in (pol_resp.data or [])})

        if not person_id_filter:
            return HTMLResponse(
                '<div class="rounded-md bg-yellow-50 border border-yellow-200 p-3 mt-2">'
                '<p class="text-sm text-yellow-700">No people matched the selected filters. 0 members added.</p>'
                '</div>'
            )

    # Query matching people (no limit — we want all matching for bulk add)
    people = []
    if q and len(q) >= 2:
        query1 = (
            sb.table("people")
            .select("id, first_name, last_name, email, do_not_contact, coverage_owner")
            .eq("is_deleted", False)
            .eq("do_not_contact", False)
            .ilike("last_name", f"%{q}%")
            .order("last_name")
            .limit(500)
        )
        if person_id_filter:
            query1 = query1.in_("id", person_id_filter)
        resp1 = query1.execute()

        query2 = (
            sb.table("people")
            .select("id, first_name, last_name, email, do_not_contact, coverage_owner")
            .eq("is_deleted", False)
            .eq("do_not_contact", False)
            .ilike("first_name", f"%{q}%")
            .order("last_name")
            .limit(500)
        )
        if person_id_filter:
            query2 = query2.in_("id", person_id_filter)
        resp2 = query2.execute()

        seen = set()
        for p in (resp1.data or []) + (resp2.data or []):
            if p["id"] not in seen:
                seen.add(p["id"])
                people.append(p)
    else:
        query = (
            sb.table("people")
            .select("id, first_name, last_name, email, do_not_contact, coverage_owner")
            .eq("is_deleted", False)
            .eq("do_not_contact", False)
            .in_("id", person_id_filter)
            .order("last_name")
            .limit(500)
        )
        resp = query.execute()
        people = resp.data or []

    if not people:
        return HTMLResponse(
            '<div class="rounded-md bg-yellow-50 border border-yellow-200 p-3 mt-2">'
            '<p class="text-sm text-yellow-700">No eligible people found. 0 members added.</p>'
            '</div>'
        )

    # --- Step 2: Get existing active members to skip ---
    existing_resp = (
        sb.table("distribution_list_members")
        .select("person_id, id, is_active")
        .eq("distribution_list_id", str(list_id))
        .execute()
    )
    existing_active = {m["person_id"] for m in (existing_resp.data or []) if m["is_active"]}
    existing_inactive = {m["person_id"]: m["id"] for m in (existing_resp.data or []) if not m["is_active"]}

    # --- Step 3: Add each person (skip DNC, skip already-member) ---
    now_str = datetime.now(timezone.utc).isoformat()
    added_count = 0
    skipped_dnc = 0
    skipped_existing = 0

    for p in people:
        pid = str(p["id"])

        # Skip DNC (should already be excluded by query, but double-check)
        if p.get("do_not_contact"):
            skipped_dnc += 1
            continue

        # Skip already-active members
        if pid in existing_active:
            skipped_existing += 1
            continue

        # Reactivate or insert
        if pid in existing_inactive:
            sb.table("distribution_list_members").update({
                "is_active": True,
                "joined_at": now_str,
                "removed_at": None,
                "removal_reason": None,
                "coverage_owner_id": p.get("coverage_owner"),
            }).eq("id", existing_inactive[pid]).execute()
        else:
            sb.table("distribution_list_members").insert({
                "distribution_list_id": str(list_id),
                "person_id": pid,
                "coverage_owner_id": p.get("coverage_owner"),
                "is_active": True,
            }).execute()

        log_field_change(
            "distribution_list", str(list_id), "member_added",
            None, f"{p['first_name']} {p['last_name']} ({pid})",
            current_user.id,
        )
        added_count += 1

    # Build summary message
    parts = [f"{added_count} member{'s' if added_count != 1 else ''} added"]
    if skipped_existing:
        parts.append(f"{skipped_existing} already on list")
    if skipped_dnc:
        parts.append(f"{skipped_dnc} skipped (DNC)")

    return HTMLResponse(
        f'<div class="rounded-md bg-green-50 border border-green-200 p-3 mt-2" id="add-all-result">'
        f'<div class="flex items-center">'
        f'<svg class="h-5 w-5 text-green-500 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
        f'<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>'
        f'<p class="text-sm text-green-700 font-medium">{". ".join(parts)}.</p>'
        f'</div>'
        f'<p class="text-xs text-green-600 mt-1">Refresh the members list to see all changes.</p>'
        f'</div>'
    )

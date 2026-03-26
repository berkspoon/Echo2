"""Grid service — centralised list/query logic for the reusable grid component.

Replaces per-router list query, enrichment, pagination, and filter logic with
a single metadata-driven system that every entity list route calls.
"""

from datetime import date as date_type
from typing import Optional
from uuid import UUID

from db.client import get_supabase
from db.field_service import (
    get_field_definitions,
    enrich_field_definitions,
    load_custom_values_batch,
)
from db.helpers import (
    batch_resolve_users,
    batch_resolve_orgs,
    get_reference_data,
    is_overdue,
)


# ── Entity → table mapping ─────────────────────────────────────────────────

_ENTITY_TABLES = {
    "organization": "organizations",
    "person": "people",
    "lead": "leads",
    "activity": "activities",
    "contract": "contracts",
    "task": "tasks",
    "distribution_list": "distribution_lists",
}

# ── Default columns per entity (mirrors existing _list_table.html) ──────────

_DEFAULT_COLUMNS: dict[str, list[str]] = {
    "organization": [
        "company_name", "relationship_type", "organization_type", "country", "aum_mn",
    ],
    "person": [
        "first_name", "last_name", "email", "phone", "job_title",
    ],
    "lead": [
        "organization_id", "lead_type", "rating", "service_type",
        "aksia_owner_id", "expected_revenue", "expected_yr1_flar", "start_date",
    ],
    "activity": [
        "effective_date", "title", "activity_type", "author_id",
    ],
    "contract": [
        "organization_id", "service_type", "asset_classes", "client_coverage",
        "actual_revenue", "start_date",
    ],
    "task": [
        "status", "title", "due_date", "assigned_to", "source", "linked_record_type",
    ],
    "distribution_list": [
        "list_name", "list_type", "list_mode", "brand", "asset_class", "frequency",
        "created_at",
    ],
}

# Columns that are always selected from the DB regardless of visible columns
_BASE_SELECT: dict[str, str] = {
    "organization": "id, company_name, short_name, relationship_type, organization_type, country, city, aum_mn, rfp_hold, website, created_at",
    "person": "id, first_name, last_name, email, phone, job_title, do_not_contact, coverage_owner, asset_classes_of_interest, created_at",
    "lead": "id, organization_id, lead_type, rating, service_type, relationship, aksia_owner_id, expected_revenue, expected_yr1_flar, start_date, end_date, summary, fund_id, share_class, target_allocation_mn, soft_circle_mn, probability_pct, created_at, is_deleted",
    "activity": "id, title, effective_date, activity_type, subtype, author_id, details, follow_up_required, created_at",
    "contract": "id, organization_id, originating_lead_id, start_date, service_type, asset_classes, client_coverage, actual_revenue, created_at",
    "task": "id, title, status, due_date, assigned_to, source, notes, linked_record_type, linked_record_id, created_by, created_at",
    "distribution_list": "id, list_name, list_type, brand, asset_class, frequency, is_official, is_private, owner_id, l2_superset_of, list_mode, filter_criteria, created_at",
}

# Valid sort columns per entity (superset — field_defs checked at runtime too)
_VALID_SORT: dict[str, set[str]] = {
    "organization": {"company_name", "relationship_type", "organization_type", "country", "aum_mn", "created_at"},
    "person": {"first_name", "last_name", "email", "job_title", "phone", "created_at"},
    "lead": {"rating", "service_type", "expected_revenue", "expected_yr1_flar", "start_date", "created_at"},
    "activity": {"effective_date", "title", "activity_type", "created_at"},
    "contract": {"start_date", "actual_revenue", "service_type", "created_at"},
    "task": {"due_date", "created_at", "status", "title"},
    "distribution_list": {"list_name", "list_type", "brand", "created_at"},
}

_DEFAULT_SORT: dict[str, tuple[str, str]] = {
    "organization": ("company_name", "asc"),
    "person": ("last_name", "asc"),
    "lead": ("start_date", "desc"),
    "activity": ("effective_date", "desc"),
    "contract": ("start_date", "desc"),
    "task": ("due_date", "asc"),
    "distribution_list": ("list_name", "asc"),
}

# Lead stages considered inactive (won/lost/closed/declined)
_INACTIVE_STAGES = (
    "won", "lost_dropped_out", "lost_selected_other",
    "lost_nobody_hired", "closed", "declined",
)

# ── Virtual / computed columns (not stored in DB or field_definitions) ────
_VIRTUAL_COLUMNS: dict[str, list[dict]] = {
    "organization": [
        {
            "field_name": "active_leads_count",
            "display_name": "Active Leads",
            "field_type": "number",
            "sortable": False,
            "filterable": False,
            "section_name": "Computed",
            "is_system": True,
            "is_active": True,
            "is_required": False,
            "visibility_rules": None,
            "dropdown_category": None,
            "storage_type": "virtual",
        },
        # feedback: [padelsbach] cross-entity aggregate column
        {
            "field_name": "contact_count",
            "display_name": "Contacts",
            "field_type": "number",
            "sortable": False,
            "filterable": False,
            "section_name": "Computed",
            "is_system": True,
            "is_active": True,
            "is_required": False,
            "visibility_rules": None,
            "dropdown_category": None,
            "storage_type": "virtual",
            "grid_default_visible": False,
        },
        # feedback: [padelsbach] active lead boolean filter
        {
            "field_name": "has_active_leads",
            "display_name": "Has Active Leads",
            "field_type": "boolean",
            "sortable": False,
            "filterable": True,
            "section_name": "Computed",
            "is_system": True,
            "is_active": True,
            "is_required": False,
            "visibility_rules": None,
            "dropdown_category": None,
            "storage_type": "virtual",
            "grid_default_visible": False,
        },
    ],
    # feedback: [padelsbach] cross-entity linked org columns on people grid
    "person": [
        {
            "field_name": "org_city",
            "display_name": "Org City",
            "field_type": "text",
            "sortable": False,
            "filterable": True,
            "section_name": "Organization",
            "is_system": True,
            "is_active": True,
            "is_required": False,
            "visibility_rules": None,
            "dropdown_category": None,
            "storage_type": "virtual",
            "grid_default_visible": False,
        },
        {
            "field_name": "org_country",
            "display_name": "Org Country",
            "field_type": "text",
            "sortable": False,
            "filterable": True,
            "section_name": "Organization",
            "is_system": True,
            "is_active": True,
            "is_required": False,
            "visibility_rules": None,
            "dropdown_category": None,
            "storage_type": "virtual",
            "grid_default_visible": False,
        },
        {
            "field_name": "org_type",
            "display_name": "Org Type",
            "field_type": "text",
            "sortable": False,
            "filterable": True,
            "section_name": "Organization",
            "is_system": True,
            "is_active": True,
            "is_required": False,
            "visibility_rules": None,
            "dropdown_category": None,
            "storage_type": "virtual",
            "grid_default_visible": False,
        },
        {
            "field_name": "org_aum_mn",
            "display_name": "Org AUM ($M)",
            "field_type": "currency",
            "sortable": False,
            "filterable": True,
            "section_name": "Organization",
            "is_system": True,
            "is_active": True,
            "is_required": False,
            "visibility_rules": None,
            "dropdown_category": None,
            "storage_type": "virtual",
            "grid_default_visible": False,
        },
        # feedback: [padelsbach] active lead boolean filter on people grid
        {
            "field_name": "has_active_leads",
            "display_name": "Has Active Leads",
            "field_type": "boolean",
            "sortable": False,
            "filterable": True,
            "section_name": "Computed",
            "is_system": True,
            "is_active": True,
            "is_required": False,
            "visibility_rules": None,
            "dropdown_category": None,
            "storage_type": "virtual",
            "grid_default_visible": False,
        },
    ],
    # feedback: [padelsbach] cross-entity linked org columns on leads grid
    "lead": [
        {
            "field_name": "org_country",
            "display_name": "Org Country",
            "field_type": "text",
            "sortable": False,
            "filterable": True,
            "section_name": "Organization",
            "is_system": True,
            "is_active": True,
            "is_required": False,
            "visibility_rules": None,
            "dropdown_category": None,
            "storage_type": "virtual",
            "grid_default_visible": False,
        },
        {
            "field_name": "org_city",
            "display_name": "Org City",
            "field_type": "text",
            "sortable": False,
            "filterable": True,
            "section_name": "Organization",
            "is_system": True,
            "is_active": True,
            "is_required": False,
            "visibility_rules": None,
            "dropdown_category": None,
            "storage_type": "virtual",
            "grid_default_visible": False,
        },
        {
            "field_name": "org_type",
            "display_name": "Org Type",
            "field_type": "text",
            "sortable": False,
            "filterable": True,
            "section_name": "Organization",
            "is_system": True,
            "is_active": True,
            "is_required": False,
            "visibility_rules": None,
            "dropdown_category": None,
            "storage_type": "virtual",
            "grid_default_visible": False,
        },
        {
            "field_name": "org_aum_mn",
            "display_name": "Org AUM ($M)",
            "field_type": "currency",
            "sortable": False,
            "filterable": True,
            "section_name": "Organization",
            "is_system": True,
            "is_active": True,
            "is_required": False,
            "visibility_rules": None,
            "dropdown_category": None,
            "storage_type": "virtual",
            "grid_default_visible": False,
        },
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# build_grid_context — main entry point
# ═══════════════════════════════════════════════════════════════════════════

def build_grid_context(
    entity_type: str,
    request,
    user,
    *,
    base_url: str = "",
    extra_filters: Optional[dict] = None,
    extra_columns: Optional[list[dict]] = None,
    saved_view_id: Optional[str] = None,
    grid_container_id_override: Optional[str] = None,
    export_mode: bool = False,
) -> dict:
    """Build everything the _grid.html template needs.

    Args:
        entity_type: e.g. 'organization', 'lead'
        request: FastAPI Request
        user: current_user dependency
        base_url: the list endpoint URL for HTMX reloads
        extra_filters: pre-applied filters (e.g. lead_type, assigned_to)
        extra_columns: non-field-def computed columns
        saved_view_id: UUID of a saved view to load
        grid_container_id_override: custom container ID (useful for drilldowns)
        export_mode: if True, fetch all matching rows (no page_size cap)

    Returns:
        dict with keys: columns, rows, pagination, sort_by, sort_dir,
        filters, saved_views, current_view_id, entity_type, base_url,
        users, extra_columns, grid_container_id
    """
    params = dict(request.query_params)

    # 1. Field definitions
    field_defs = get_field_definitions(entity_type, active_only=True)
    field_defs = enrich_field_definitions(field_defs)

    # 1b. Merge virtual/computed columns so they appear in column selector
    virtual_cols = _VIRTUAL_COLUMNS.get(entity_type, [])
    if virtual_cols:
        existing_names = {fd["field_name"] for fd in field_defs}
        for vc in virtual_cols:
            if vc["field_name"] not in existing_names:
                field_defs.append(dict(vc))

    # 2. Saved view (if any)
    saved_view = None
    if saved_view_id or params.get("view_id"):
        vid = saved_view_id or params.get("view_id")
        saved_view = _load_saved_view(vid)

    # 3. Visible columns
    visible_columns = _resolve_visible_columns(
        entity_type, field_defs, saved_view, params.get("visible_columns")
    )

    # Build column defs list (ordered)
    fd_map = {fd["field_name"]: fd for fd in field_defs}
    columns = []
    for col_name in visible_columns:
        fd = fd_map.get(col_name)
        if fd:
            columns.append(fd)
        # skip deactivated fields gracefully

    # 4. Sort
    default_sort_col, default_sort_dir = _DEFAULT_SORT.get(entity_type, ("created_at", "desc"))
    sort_by = params.get("sort_by", "")
    sort_dir = params.get("sort_dir", "")
    if saved_view and not sort_by:
        sort_by = saved_view.get("sort_by") or default_sort_col
        sort_dir = saved_view.get("sort_dir") or default_sort_dir
    if not sort_by:
        sort_by = default_sort_col
    if not sort_dir:
        sort_dir = default_sort_dir
    valid_sorts = _VALID_SORT.get(entity_type, set())
    if sort_by not in valid_sorts:
        sort_by = default_sort_col

    # 5. Pagination
    if export_mode:
        page = 1
        page_size = 50000  # fetch all rows for export
    else:
        page = max(1, int(params.get("page", "1")))
        page_size = min(100, max(10, int(params.get("page_size", "25"))))

    # 6. Filters — merge saved-view filters with query-param overrides
    filters = {}
    if saved_view:
        filters.update(saved_view.get("filters") or {})
    # Extract filter query params (anything that matches a field_name or known alias)
    filters.update(_extract_filters(entity_type, params, fd_map))
    if extra_filters:
        filters.update(extra_filters)

    # 6b. Per-column filters (cf_ prefixed params)
    col_filters = _extract_column_filters(params)
    # Also load col_filters from saved view if present
    if saved_view and saved_view.get("filters") and isinstance(saved_view["filters"], dict):
        for k, v in saved_view["filters"].items():
            if k.startswith("cf_") and k not in col_filters:
                col_filters[k] = v

    # 7. Execute query
    rows, total_count = _execute_query(
        entity_type, filters, sort_by, sort_dir, page, page_size,
        col_filters=col_filters,
        field_defs=field_defs,
    )

    # 8. Enrich rows
    _enrich_rows(entity_type, rows, field_defs)

    # 9. Pagination dict
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    pagination = {
        "page": page,
        "page_size": page_size,
        "total": total_count,
        "total_pages": total_pages,
    }

    # 10. Load saved views for selector
    saved_views = _load_saved_views_for_user(str(user.id), entity_type)

    # 11. Users list (for lookup-type filter dropdowns)
    sb = get_supabase()
    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
    users_list = users_resp.data or []

    # Grid container ID — entity-specific to avoid conflicts
    container_id = grid_container_id_override or f"{entity_type.replace('_', '-')}-grid-container"

    return {
        "columns": columns,
        "rows": rows,
        "pagination": pagination,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "filters": filters,
        "col_filters": col_filters,
        "saved_views": saved_views,
        "current_view_id": (saved_view or {}).get("id"),
        "entity_type": entity_type,
        "base_url": base_url,
        "users": users_list,
        "extra_columns": extra_columns or [],
        "grid_container_id": container_id,
        "field_defs": field_defs,
        "current_user_id": str(user.id),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Query execution
# ═══════════════════════════════════════════════════════════════════════════

def _execute_query(
    entity_type: str,
    filters: dict,
    sort_by: str,
    sort_dir: str,
    page: int,
    page_size: int,
    *,
    col_filters: Optional[dict] = None,
    field_defs: Optional[list[dict]] = None,
) -> tuple[list[dict], int]:
    """Run the Supabase query with filters, sort, pagination. Returns (rows, total)."""
    sb = get_supabase()
    table = _ENTITY_TABLES[entity_type]
    select_cols = _BASE_SELECT[entity_type]

    query = sb.table(table).select(select_cols, count="exact")

    # Soft-delete filter
    if entity_type == "distribution_list":
        query = query.eq("is_active", True)
    else:
        query = query.eq("is_deleted", False)

    # Apply filters
    query = _apply_filters(entity_type, query, filters)

    # feedback: [padelsbach] pre-filter for has_active_leads virtual column
    if col_filters and "cf_has_active_leads" in col_filters:
        want_active = "true" in col_filters.pop("cf_has_active_leads").lower()
        _nil = ["00000000-0000-0000-0000-000000000000"]
        # Find org IDs with active leads
        all_leads_resp = sb.table("leads").select("organization_id, rating").eq("is_deleted", False).execute()
        active_org_ids: set[str] = set()
        for l in (all_leads_resp.data or []):
            if l.get("rating") not in _INACTIVE_STAGES:
                active_org_ids.add(str(l["organization_id"]))
        if entity_type == "organization":
            if want_active:
                query = query.in_("id", list(active_org_ids) or _nil)
            else:
                # Orgs WITHOUT active leads: get all non-deleted org IDs, subtract active
                all_orgs_resp = sb.table("organizations").select("id").eq("is_deleted", False).execute()
                all_org_ids = {str(o["id"]) for o in (all_orgs_resp.data or [])}
                no_leads_ids = list(all_org_ids - active_org_ids)
                query = query.in_("id", no_leads_ids or _nil)
        elif entity_type == "person":
            # Find person IDs at orgs with active leads via primary org link
            if active_org_ids:
                pol_resp = (
                    sb.table("person_organization_links")
                    .select("person_id")
                    .in_("link_type", ["primary", "secondary"])
                    .in_("organization_id", list(active_org_ids))
                    .execute()
                )
                person_ids_with_leads = list({str(p["person_id"]) for p in (pol_resp.data or [])})
            else:
                person_ids_with_leads = []
            if want_active:
                query = query.in_("id", person_ids_with_leads or _nil)
            else:
                # People WITHOUT active leads: get all non-deleted person IDs, subtract
                all_people_resp = sb.table("people").select("id").eq("is_deleted", False).execute()
                all_person_ids = {str(p["id"]) for p in (all_people_resp.data or [])}
                no_leads_ids = list(all_person_ids - set(person_ids_with_leads))
                query = query.in_("id", no_leads_ids or _nil)

    # Pre-filter for org-linked virtual/linked columns
    # These don't exist on the entity table — resolve via organizations table first
    # Start with hardcoded virtual columns, then extend with admin-configured linked fields
    _ORG_LINKED_COLS = {
        "org_city": "city", "org_country": "country",
        "org_type": "organization_type", "org_aum_mn": "aum_mn",
    }
    # Dynamically add linked fields that point to organization
    if field_defs:
        for fd in field_defs:
            if fd.get("storage_type") == "linked" and fd.get("linked_config"):
                lc = fd["linked_config"]
                if lc.get("source_entity") == "organization" and fd["field_name"] not in _ORG_LINKED_COLS:
                    _ORG_LINKED_COLS[fd["field_name"]] = lc["source_field"]
    if col_filters and entity_type in ("person", "lead"):
        org_cf = {}
        for k in list(col_filters.keys()):
            field_name = k[3:] if k.startswith("cf_") else k
            if field_name in _ORG_LINKED_COLS:
                org_cf[field_name] = col_filters.pop(k)
        if org_cf:
            org_query = sb.table("organizations").select("id").eq("is_deleted", False)
            for virt_name, real_col in _ORG_LINKED_COLS.items():
                if virt_name not in org_cf:
                    continue
                val = org_cf[virt_name]
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
                elif op == "gte":
                    org_query = org_query.gte(real_col, operand)
                elif op == "lte":
                    org_query = org_query.lte(real_col, operand)
            org_resp = org_query.limit(5000).execute()
            matching_org_ids = [str(o["id"]) for o in (org_resp.data or [])]
            _nil_id = ["00000000-0000-0000-0000-000000000000"]
            if entity_type == "person":
                if matching_org_ids:
                    pol_resp = (
                        sb.table("person_organization_links")
                        .select("person_id")
                        .in_("link_type", ["primary", "secondary"])
                        .in_("organization_id", matching_org_ids)
                        .execute()
                    )
                    person_ids = list({str(p["person_id"]) for p in (pol_resp.data or [])})
                    query = query.in_("id", person_ids or _nil_id)
                else:
                    query = query.in_("id", _nil_id)
            elif entity_type == "lead":
                query = query.in_("organization_id", matching_org_ids or _nil_id)

    # Apply per-column filters (remaining non-virtual filters)
    if col_filters:
        query = _apply_column_filters(query, col_filters, entity_type)

    # Sort
    desc = sort_dir.lower() == "desc"
    if entity_type == "task" and sort_by == "due_date":
        query = query.order(sort_by, desc=desc, nullsfirst=False if not desc else True)
    else:
        query = query.order(sort_by, desc=desc)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    resp = query.execute()
    return resp.data or [], resp.count or 0


def _apply_filters(entity_type: str, query, filters: dict):
    """Apply entity-aware filters to a Supabase query builder."""

    # ── Pre-filter by explicit ID list (used by dashboard drilldowns) ──
    if filters.get("_lead_ids"):
        query = query.in_("id", filters["_lead_ids"])

    # ── Text search (q) ────────────────────────────────────────────────
    q = filters.get("q", "")
    if q:
        if entity_type == "organization":
            query = query.ilike("company_name", f"%{q}%")
        elif entity_type == "person":
            query = query.or_(f"first_name.ilike.%{q}%,last_name.ilike.%{q}%,email.ilike.%{q}%")
        elif entity_type == "lead":
            # Search handled via org_ids (post-query or pre-filter)
            pass  # handled separately below
        elif entity_type == "activity":
            query = query.or_(f"title.ilike.%{q}%,details.ilike.%{q}%")
        elif entity_type == "contract":
            pass  # search by org name — handled separately below
        elif entity_type == "task":
            query = query.or_(f"title.ilike.%{q}%,notes.ilike.%{q}%")
        elif entity_type == "distribution_list":
            query = query.ilike("list_name", f"%{q}%")

    # ── Entity-specific filters ─────────────────────────────────────────

    if entity_type == "organization":
        if filters.get("relationship"):
            query = query.eq("relationship_type", filters["relationship"])
        if filters.get("type"):
            query = query.eq("organization_type", filters["type"])
        if filters.get("country"):
            query = query.eq("country", filters["country"])

    elif entity_type == "person":
        if filters.get("ac"):
            query = query.contains("asset_classes_of_interest", [filters["ac"]])
        dnc = filters.get("dnc", "")
        if dnc == "yes":
            query = query.eq("do_not_contact", True)
        elif dnc == "no":
            query = query.eq("do_not_contact", False)

    elif entity_type == "lead":
        if filters.get("lead_type"):
            lt = filters["lead_type"]
            if lt in ("fundraise", "product"):
                query = query.in_("lead_type", ["fundraise", "product"])
            elif lt == "advisory":
                query = query.or_("lead_type.eq.advisory,lead_type.is.null")
            else:
                query = query.eq("lead_type", lt)
        if filters.get("stage"):
            query = query.eq("rating", filters["stage"])
        if filters.get("owner"):
            query = query.eq("aksia_owner_id", filters["owner"])
        if filters.get("service"):
            query = query.eq("service_type", filters["service"])
        if filters.get("rel"):
            query = query.eq("relationship", filters["rel"])
        if filters.get("fund"):
            query = query.eq("fund_id", filters["fund"])
        if filters.get("view") == "my":
            if filters.get("_user_id"):
                query = query.eq("aksia_owner_id", filters["_user_id"])
        # Search by org name for leads
        if q:
            sb = get_supabase()
            org_resp = (
                sb.table("organizations")
                .select("id")
                .eq("is_deleted", False)
                .ilike("company_name", f"%{q}%")
                .limit(200)
                .execute()
            )
            org_ids = [str(o["id"]) for o in (org_resp.data or [])]
            if org_ids:
                query = query.in_("organization_id", org_ids)
            else:
                query = query.in_("organization_id", ["00000000-0000-0000-0000-000000000000"])

    elif entity_type == "activity":
        if filters.get("type"):
            query = query.eq("activity_type", filters["type"])
        if filters.get("author"):
            query = query.eq("author_id", filters["author"])

    elif entity_type == "contract":
        if filters.get("service"):
            query = query.eq("service_type", filters["service"])
        # Search by org name for contracts
        if q:
            sb = get_supabase()
            org_resp = (
                sb.table("organizations")
                .select("id")
                .eq("is_deleted", False)
                .ilike("company_name", f"%{q}%")
                .limit(200)
                .execute()
            )
            org_ids = [str(o["id"]) for o in (org_resp.data or [])]
            if org_ids:
                query = query.in_("organization_id", org_ids)
            else:
                query = query.in_("organization_id", ["00000000-0000-0000-0000-000000000000"])

    elif entity_type == "task":
        if filters.get("status"):
            query = query.eq("status", filters["status"])
        if filters.get("assignee"):
            query = query.eq("assigned_to", filters["assignee"])
        if filters.get("source"):
            query = query.eq("source", filters["source"])
        if filters.get("linked_type"):
            query = query.eq("linked_record_type", filters["linked_type"])
        if filters.get("overdue") == "true":
            query = query.lt("due_date", str(date_type.today())).in_("status", ["open", "in_progress"])

    elif entity_type == "distribution_list":
        if filters.get("type"):
            query = query.eq("list_type", filters["type"])
        if filters.get("brand"):
            query = query.eq("brand", filters["brand"])
        if filters.get("asset_class"):
            query = query.eq("asset_class", filters["asset_class"])
        # Tab-based view: official vs custom/private
        list_view = filters.get("_list_view", "custom")
        if list_view == "official":
            query = query.eq("is_official", True)
        else:
            # Custom/private view — apply privacy filter for non-admins
            query = query.eq("is_official", False)
            if filters.get("_user_role") != "admin" and filters.get("_user_id"):
                uid = filters["_user_id"]
                query = query.or_(f"owner_id.eq.{uid},is_private.eq.false")

    # ── Date range (generic) ─────────────────────────────────────────────
    date_field = _date_field_for_entity(entity_type)
    if date_field:
        if filters.get("from"):
            query = query.gte(date_field, filters["from"])
        if filters.get("to"):
            query = query.lte(date_field, filters["to"])

    # ── Org-scoped filter (for "My Organizations" via pre-computed IDs) ──
    if filters.get("_org_ids"):
        query = query.in_("id", filters["_org_ids"])

    # ── Activity ID filter (for "My Activities") ──
    if filters.get("_activity_ids"):
        query = query.in_("id", filters["_activity_ids"])

    return query


def _date_field_for_entity(entity_type: str) -> Optional[str]:
    return {
        "lead": "start_date",
        "activity": "effective_date",
        "contract": "start_date",
        "task": "due_date",
    }.get(entity_type)


# ═══════════════════════════════════════════════════════════════════════════
# Row enrichment
# ═══════════════════════════════════════════════════════════════════════════

def _resolve_linked_fields(entity_type: str, rows: list[dict], field_defs: list[dict]) -> None:
    """Resolve admin-configured linked fields (storage_type='linked').

    Linked fields pull data from a related entity via a defined link path.
    E.g., a Person field that shows their organization's city.
    """
    if not rows:
        return

    linked_fields = [
        fd for fd in field_defs
        if fd.get("storage_type") == "linked" and fd.get("linked_config")
    ]
    if not linked_fields:
        return

    sb = get_supabase()

    # Group linked fields by (source_entity, link_via) for batching
    groups: dict[tuple[str, str], list[dict]] = {}
    for fd in linked_fields:
        lc = fd["linked_config"]
        key = (lc["source_entity"], lc.get("link_via", "direct"))
        groups.setdefault(key, []).append(fd)

    for (source_entity, link_via), fields_in_group in groups.items():
        source_fields = list({fd["linked_config"]["source_field"] for fd in fields_in_group})
        select_cols = "id, " + ", ".join(source_fields)

        source_table = {
            "organization": "organizations",
            "person": "people",
            "lead": "leads",
            "activity": "activities",
            "contract": "contracts",
        }.get(source_entity, f"{source_entity}s")

        if link_via == "person_organization_links":
            # Person → Organization via junction table
            row_ids = [str(r["id"]) for r in rows]
            pol_resp = (
                sb.table("person_organization_links")
                .select("person_id, organization_id")
                .in_("person_id", row_ids)
                .eq("link_type", "primary")
                .execute()
            )
            entity_to_source = {str(lnk["person_id"]): str(lnk["organization_id"]) for lnk in (pol_resp.data or [])}
            source_ids = list(set(entity_to_source.values()))

        elif link_via == "direct":
            # Direct FK: entity has a column named <source_entity>_id
            fk_col = f"{source_entity}_id"
            source_ids = list({str(r[fk_col]) for r in rows if r.get(fk_col)})
            entity_to_source = {str(r["id"]): str(r[fk_col]) for r in rows if r.get(fk_col)}

        else:
            continue

        if not source_ids:
            for row in rows:
                for fd in fields_in_group:
                    row[fd["field_name"]] = None
            continue

        source_resp = sb.table(source_table).select(select_cols).in_("id", source_ids).execute()
        source_map = {str(s["id"]): s for s in (source_resp.data or [])}

        for row in rows:
            src_id = entity_to_source.get(str(row["id"]))
            src_data = source_map.get(src_id) if src_id else None
            for fd in fields_in_group:
                src_field = fd["linked_config"]["source_field"]
                # Only set if not already populated by entity-specific enrichment
                if fd["field_name"] not in row:
                    row[fd["field_name"]] = src_data.get(src_field) if src_data else None


def _enrich_rows(entity_type: str, rows: list[dict], field_defs: list[dict]) -> None:
    """In-place enrichment: resolve lookups, compute display values."""
    if not rows:
        return

    if entity_type == "organization":
        _enrich_organizations(rows)
    elif entity_type == "person":
        _enrich_people(rows)
    elif entity_type == "lead":
        _enrich_leads(rows)
    elif entity_type == "activity":
        _enrich_activities(rows)
    elif entity_type == "contract":
        _enrich_contracts(rows)
    elif entity_type == "task":
        _enrich_tasks(rows)
    elif entity_type == "distribution_list":
        _enrich_distribution_lists(rows)

    # Resolve admin-configured linked fields (storage_type='linked')
    _resolve_linked_fields(entity_type, rows, field_defs)

    # Load EAV values for custom fields (all entities)
    entity_ids = [str(r["id"]) for r in rows if r.get("id")]
    if entity_ids:
        eav_map = load_custom_values_batch(entity_type, entity_ids)
        for row in rows:
            eid = str(row.get("id", ""))
            if eid in eav_map:
                row.update(eav_map[eid])


def _enrich_organizations(rows: list[dict]) -> None:
    """Enrich orgs with active-leads count (for Lead Finder view)."""
    sb = get_supabase()
    org_ids = [str(r["id"]) for r in rows]
    if not org_ids:
        return

    # Batch query: count active leads per org in a single RPC-free call.
    # supabase-py doesn't support GROUP BY natively, so we fetch minimal
    # rows and aggregate in Python (still a single round trip).
    leads_resp = (
        sb.table("leads")
        .select("organization_id")
        .eq("is_deleted", False)
        .in_("organization_id", org_ids)
        .execute()
    )
    # Count per org, excluding inactive stages
    count_map: dict[str, int] = {}
    for lead in (leads_resp.data or []):
        oid = str(lead["organization_id"])
        count_map[oid] = count_map.get(oid, 0) + 1

    # Now subtract inactive leads
    inactive_resp = (
        sb.table("leads")
        .select("organization_id")
        .eq("is_deleted", False)
        .in_("organization_id", org_ids)
        .in_("rating", list(_INACTIVE_STAGES))
        .execute()
    )
    inactive_map: dict[str, int] = {}
    for lead in (inactive_resp.data or []):
        oid = str(lead["organization_id"])
        inactive_map[oid] = inactive_map.get(oid, 0) + 1

    for row in rows:
        oid = str(row["id"])
        total = count_map.get(oid, 0)
        inactive = inactive_map.get(oid, 0)
        row["active_leads_count"] = total - inactive
        # feedback: [padelsbach] has_active_leads boolean
        row["has_active_leads"] = (total - inactive) > 0

    # feedback: [padelsbach] contact_count virtual column
    pol_resp = (
        sb.table("person_organization_links")
        .select("organization_id")
        .in_("organization_id", org_ids)
        .execute()
    )
    contact_count_map: dict[str, int] = {}
    for link in (pol_resp.data or []):
        oid = str(link["organization_id"])
        contact_count_map[oid] = contact_count_map.get(oid, 0) + 1
    for row in rows:
        row["contact_count"] = contact_count_map.get(str(row["id"]), 0)


def _enrich_people(rows: list[dict]) -> None:
    """Resolve primary organization for each person."""
    sb = get_supabase()
    person_ids = [str(r["id"]) for r in rows]
    if not person_ids:
        return

    pol_resp = (
        sb.table("person_organization_links")
        .select("person_id, organization_id, link_type")
        .in_("person_id", person_ids)
        .eq("link_type", "primary")
        .execute()
    )
    person_org_map = {}
    for link in (pol_resp.data or []):
        person_org_map[str(link["person_id"])] = str(link["organization_id"])

    org_ids = list(set(person_org_map.values()))
    org_map = batch_resolve_orgs(org_ids) if org_ids else {}

    # feedback: [padelsbach] has_active_leads for people via their primary org
    active_org_set: set[str] = set()
    if org_ids:
        leads_resp = (
            sb.table("leads")
            .select("organization_id, rating")
            .eq("is_deleted", False)
            .in_("organization_id", org_ids)
            .execute()
        )
        for lead in (leads_resp.data or []):
            if lead.get("rating") not in _INACTIVE_STAGES:
                active_org_set.add(str(lead["organization_id"]))

    for row in rows:
        org_id = person_org_map.get(str(row["id"]))
        if org_id and org_id in org_map:
            org_info = org_map[org_id]
            row["primary_org"] = org_info
        else:
            org_info = None
            row["primary_org"] = None
        # feedback: [padelsbach] cross-entity org columns on people grid
        row["org_city"] = org_info.get("city") if org_info else None
        row["org_country"] = org_info.get("country") if org_info else None
        row["org_type"] = org_info.get("organization_type") if org_info else None
        row["org_aum_mn"] = org_info.get("aum_mn") if org_info else None
        row["has_active_leads"] = org_id in active_org_set if org_id else False


def _enrich_leads(rows: list[dict]) -> None:
    """Resolve org names, owner names, fund tickers."""
    org_ids = list({str(r["organization_id"]) for r in rows if r.get("organization_id")})
    org_map = batch_resolve_orgs(org_ids) if org_ids else {}

    owner_ids = list({str(r["aksia_owner_id"]) for r in rows if r.get("aksia_owner_id")})
    user_map = batch_resolve_users(owner_ids) if owner_ids else {}

    # Fund tickers
    fund_ids = list({str(r["fund_id"]) for r in rows if r.get("fund_id")})
    fund_map = {}
    if fund_ids:
        sb = get_supabase()
        fund_resp = sb.table("funds").select("id, ticker").in_("id", fund_ids).execute()
        fund_map = {str(f["id"]): f["ticker"] for f in (fund_resp.data or [])}

    for row in rows:
        oid = str(row.get("organization_id", ""))
        org = org_map.get(oid)
        row["org_name"] = org["company_name"] if org else "Unknown"
        row["owner_name"] = user_map.get(str(row.get("aksia_owner_id", "")), "")
        row["fund_ticker"] = fund_map.get(str(row.get("fund_id", "")), "")
        # feedback: [padelsbach] cross-entity org columns on leads grid
        org_info = org_map.get(oid, {}) if oid else {}
        row["org_country"] = org_info.get("country") if isinstance(org_info, dict) else None
        row["org_city"] = org_info.get("city") if isinstance(org_info, dict) else None
        row["org_type"] = org_info.get("organization_type") if isinstance(org_info, dict) else None
        row["org_aum_mn"] = org_info.get("aum_mn") if isinstance(org_info, dict) else None


def _enrich_activities(rows: list[dict]) -> None:
    """Resolve author names and linked orgs."""
    sb = get_supabase()

    # Author names
    author_ids = list({str(r["author_id"]) for r in rows if r.get("author_id")})
    user_map = batch_resolve_users(author_ids) if author_ids else {}

    # Linked orgs
    activity_ids = [str(r["id"]) for r in rows]
    aol_resp = (
        sb.table("activity_organization_links")
        .select("activity_id, organization_id")
        .in_("activity_id", activity_ids)
        .execute()
    )
    # Group org IDs by activity
    act_org_ids: dict[str, list[str]] = {}
    all_org_ids: set[str] = set()
    for link in (aol_resp.data or []):
        aid = str(link["activity_id"])
        oid = str(link["organization_id"])
        act_org_ids.setdefault(aid, []).append(oid)
        all_org_ids.add(oid)

    org_map = batch_resolve_orgs(list(all_org_ids)) if all_org_ids else {}

    for row in rows:
        row["author_name"] = user_map.get(str(row.get("author_id", "")), "Unknown")
        aid = str(row["id"])
        linked_org_ids = act_org_ids.get(aid, [])
        row["linked_orgs"] = [
            {"id": oid, "company_name": (org_map.get(oid) or {}).get("company_name", "Unknown")}
            for oid in linked_org_ids
        ]


def _enrich_contracts(rows: list[dict]) -> None:
    """Resolve org names."""
    org_ids = list({str(r["organization_id"]) for r in rows if r.get("organization_id")})
    org_map = batch_resolve_orgs(org_ids) if org_ids else {}

    for row in rows:
        oid = str(row.get("organization_id", ""))
        org = org_map.get(oid)
        row["org_name"] = org["company_name"] if org else "Unknown"


def _enrich_tasks(rows: list[dict]) -> None:
    """Resolve assigned-to names, linked records, overdue status."""
    sb = get_supabase()

    # Assigned-to names
    user_ids = list({str(r["assigned_to"]) for r in rows if r.get("assigned_to")})
    user_map = batch_resolve_users(user_ids) if user_ids else {}

    # Linked records — batch by type
    by_type: dict[str, set[str]] = {}
    for t in rows:
        rt = t.get("linked_record_type")
        ri = t.get("linked_record_id")
        if rt and ri:
            by_type.setdefault(rt, set()).add(str(ri))

    record_map: dict[tuple, dict] = {}

    if "activity" in by_type:
        ids = list(by_type["activity"])
        resp = sb.table("activities").select("id, title").in_("id", ids).execute()
        for r in (resp.data or []):
            record_map[("activity", str(r["id"]))] = {
                "name": r.get("title") or "Untitled Activity",
                "url": f"/activities/{r['id']}",
                "type": "activity",
            }

    if "lead" in by_type:
        ids = list(by_type["lead"])
        resp = sb.table("leads").select("id, organization_id, summary").in_("id", ids).execute()
        lead_org_ids = {str(r["organization_id"]) for r in (resp.data or []) if r.get("organization_id")}
        org_names = {}
        if lead_org_ids:
            org_resp = sb.table("organizations").select("id, company_name").in_("id", list(lead_org_ids)).execute()
            org_names = {str(o["id"]): o["company_name"] for o in (org_resp.data or [])}
        for r in (resp.data or []):
            org_name = org_names.get(str(r.get("organization_id", "")), "Unknown Org")
            record_map[("lead", str(r["id"]))] = {
                "name": org_name,
                "url": f"/leads/{r['id']}",
                "subtitle": r.get("summary") or "",
                "type": "lead",
            }

    if "fund_prospect" in by_type:
        ids = list(by_type["fund_prospect"])
        resp = sb.table("leads").select("id, organization_id, fund_id, lead_type").in_("id", ids).execute()
        found_ids = {str(r["id"]) for r in (resp.data or [])}
        remaining = [i for i in ids if i not in found_ids]
        fp_rows = []
        if remaining:
            fp_resp = sb.table("fund_prospects").select("id, organization_id, fund_id").in_("id", remaining).execute()
            fp_rows = fp_resp.data or []
        all_fp = list(resp.data or []) + fp_rows
        fp_org_ids = {str(r["organization_id"]) for r in all_fp if r.get("organization_id")}
        fp_fund_ids = {str(r["fund_id"]) for r in all_fp if r.get("fund_id")}
        org_names = {}
        fund_tickers = {}
        if fp_org_ids:
            org_resp = sb.table("organizations").select("id, company_name").in_("id", list(fp_org_ids)).execute()
            org_names = {str(o["id"]): o["company_name"] for o in (org_resp.data or [])}
        if fp_fund_ids:
            fund_resp = sb.table("funds").select("id, ticker").in_("id", list(fp_fund_ids)).execute()
            fund_tickers = {str(f["id"]): f["ticker"] for f in (fund_resp.data or [])}
        for r in all_fp:
            org_name = org_names.get(str(r.get("organization_id", "")), "Unknown Org")
            ticker = fund_tickers.get(str(r.get("fund_id", "")), "?")
            record_map[("fund_prospect", str(r["id"]))] = {
                "name": f"{org_name} ({ticker})",
                "url": f"/leads/{r['id']}",
                "type": "fund_prospect",
            }

    if "organization" in by_type:
        ids = list(by_type["organization"])
        resp = sb.table("organizations").select("id, company_name").in_("id", ids).execute()
        for r in (resp.data or []):
            record_map[("organization", str(r["id"]))] = {
                "name": r["company_name"],
                "url": f"/organizations/{r['id']}",
                "type": "organization",
            }

    if "person" in by_type:
        ids = list(by_type["person"])
        resp = sb.table("people").select("id, first_name, last_name").in_("id", ids).execute()
        for r in (resp.data or []):
            record_map[("person", str(r["id"]))] = {
                "name": f"{r['first_name']} {r['last_name']}",
                "url": f"/people/{r['id']}",
                "type": "person",
            }

    _SOURCE_LABELS = {
        "manual": "Manual",
        "activity_follow_up": "Activity Follow-Up",
        "lead_next_steps": "Lead Next Steps",
        "fund_prospect_next_steps": "Fundraise Lead Next Steps",
    }

    for row in rows:
        row["is_overdue"] = is_overdue(row)
        row["assigned_to_name"] = user_map.get(str(row.get("assigned_to", "")), "Unknown")
        key = (row.get("linked_record_type"), str(row.get("linked_record_id", "")))
        row["linked_record_info"] = record_map.get(key)
        row["source_label"] = _SOURCE_LABELS.get(row.get("source", ""), row.get("source", ""))


def _enrich_distribution_lists(rows: list[dict]) -> None:
    """Resolve owner names and member counts."""
    sb = get_supabase()

    owner_ids = list({str(r["owner_id"]) for r in rows if r.get("owner_id")})
    user_map = batch_resolve_users(owner_ids) if owner_ids else {}

    # Member counts — batch
    list_ids = [str(r["id"]) for r in rows]
    count_map: dict[str, int] = {}
    if list_ids:
        for lid in list_ids:
            resp = (
                sb.table("distribution_list_members")
                .select("id", count="exact")
                .eq("distribution_list_id", lid)
                .eq("is_active", True)
                .execute()
            )
            count_map[lid] = resp.count or 0

    for row in rows:
        row["owner_name"] = user_map.get(str(row.get("owner_id", "")), "")
        row["member_count"] = count_map.get(str(row["id"]), 0)


# ═══════════════════════════════════════════════════════════════════════════
# Filter extraction from query params
# ═══════════════════════════════════════════════════════════════════════════

def _extract_filters(entity_type: str, params: dict, fd_map: dict) -> dict:
    """Pull known filter params from the request query string."""
    filters: dict = {}

    # Common text search
    if params.get("q"):
        filters["q"] = params["q"]

    # Entity-specific known param aliases
    _ALIASES: dict[str, dict[str, str]] = {
        "organization": {"relationship": "relationship", "type": "type", "country": "country"},
        "person": {"ac": "ac", "dnc": "dnc"},
        "lead": {
            "stage": "stage", "owner": "owner", "service": "service",
            "rel": "rel", "lead_type": "lead_type", "fund": "fund", "view": "view",
        },
        "activity": {"type": "type", "author": "author"},
        "contract": {"service": "service"},
        "task": {
            "status": "status", "assignee": "assignee", "source": "source",
            "linked_type": "linked_type", "overdue": "overdue",
        },
        "distribution_list": {
            "type": "type", "brand": "brand", "asset_class": "asset_class",
            "list_view": "list_view",
        },
    }

    aliases = _ALIASES.get(entity_type, {})
    for param_name, filter_key in aliases.items():
        val = params.get(param_name, "")
        if val:
            filters[filter_key] = val

    # Date range (generic)
    if params.get("from"):
        filters["from"] = params["from"]
    if params.get("to"):
        filters["to"] = params["to"]

    return filters


# ═══════════════════════════════════════════════════════════════════════════
# Per-column filter extraction and application
# ═══════════════════════════════════════════════════════════════════════════

def _extract_column_filters(params: dict) -> dict:
    """Scan query params for cf_ prefix, parse operator:value pairs.

    URL format: cf_<field_name>=<operator>:<value>
    Examples:
        cf_company_name=contains:Aksia
        cf_aum_mn=gte:100
        cf_relationship_type=in:client,prospect
        cf_start_date=between:2025-01-01,2025-12-31
        cf_rfp_hold=eq:true
    """
    col_filters: dict = {}
    for key, val in params.items():
        if key.startswith("cf_") and val:
            col_filters[key] = val
    return col_filters


def _apply_column_filters(query, col_filters: dict, entity_type: str):
    """Apply per-column filters to a Supabase query builder.

    Each entry is cf_<field_name>=<operator>:<value>.
    Supported operators: contains, not_contains, eq, neq, in, gte, lte, gt, lt, between, is_empty, is_not_empty
    """
    for key, raw_val in col_filters.items():
        field_name = key[3:]  # strip cf_ prefix

        # Ensure the column exists in the table's select list
        base_cols = _BASE_SELECT.get(entity_type, "")
        known_cols = {c.strip() for c in base_cols.split(",")}
        if field_name not in known_cols:
            continue  # skip EAV / unknown columns for now

        # Parse operator:value
        if ":" in raw_val:
            op, value = raw_val.split(":", 1)
        else:
            op = "eq"
            value = raw_val

        op = op.lower().strip()

        if op == "contains":
            query = query.ilike(field_name, f"%{value}%")
        elif op == "not_contains":
            query = query.not_.ilike(field_name, f"%{value}%")
        elif op == "eq":
            # Handle booleans
            if value.lower() in ("true", "false"):
                query = query.eq(field_name, value.lower() == "true")
            else:
                query = query.eq(field_name, value)
        elif op == "neq":
            query = query.neq(field_name, value)
        elif op == "in":
            vals = [v.strip() for v in value.split(",") if v.strip()]
            if vals:
                query = query.in_(field_name, vals)
        elif op == "gte":
            query = query.gte(field_name, value)
        elif op == "lte":
            query = query.lte(field_name, value)
        elif op == "gt":
            query = query.gt(field_name, value)
        elif op == "lt":
            query = query.lt(field_name, value)
        elif op == "between":
            parts = [v.strip() for v in value.split(",")]
            if len(parts) == 2:
                query = query.gte(field_name, parts[0]).lte(field_name, parts[1])
        elif op == "is_empty":
            query = query.is_(field_name, "null")
        elif op == "is_not_empty":
            query = query.not_.is_(field_name, "null")

    return query


# ═══════════════════════════════════════════════════════════════════════════
# Visible columns resolution
# ═══════════════════════════════════════════════════════════════════════════

_TOGGLABLE_EXCEPTIONS: dict[str, set[str]] = {
    "organization": {"relationship_type", "organization_type"},
    "lead": {"rating", "share_class"},
    "task": {"assigned_to", "status"},
}


def _pin_required_columns_left(
    entity_type: str, field_defs: list[dict], cols: list[str]
) -> list[str]:
    """Ensure required columns (non-togglable) are always first in the list."""
    exceptions = _TOGGLABLE_EXCEPTIONS.get(entity_type, set())
    pinned = {
        fd["field_name"]
        for fd in field_defs
        if fd.get("is_required") and fd["field_name"] not in exceptions
    }
    required_cols = [c for c in cols if c in pinned]
    other_cols = [c for c in cols if c not in pinned]
    return required_cols + other_cols


def _resolve_visible_columns(
    entity_type: str,
    field_defs: list[dict],
    saved_view: Optional[dict],
    visible_columns_param: Optional[str],
) -> list[str]:
    """Determine which columns to show, with required columns pinned left."""
    if visible_columns_param:
        raw = [c.strip() for c in visible_columns_param.split(",") if c.strip()]
    elif saved_view and saved_view.get("columns"):
        cols = saved_view["columns"]
        raw = cols if isinstance(cols, list) and cols else get_default_columns(entity_type, field_defs)
    else:
        raw = get_default_columns(entity_type, field_defs)

    return _pin_required_columns_left(entity_type, field_defs, raw)


def get_default_columns(entity_type: str, field_defs: list[dict]) -> list[str]:
    """Return default visible column names for an entity."""
    defaults = _DEFAULT_COLUMNS.get(entity_type)
    if defaults:
        return list(defaults)
    # Fallback: first 8 fields
    return [fd["field_name"] for fd in field_defs[:8]]


# ═══════════════════════════════════════════════════════════════════════════
# Saved views CRUD
# ═══════════════════════════════════════════════════════════════════════════

def _load_saved_view(view_id: str) -> Optional[dict]:
    sb = get_supabase()
    resp = sb.table("saved_views").select("*").eq("id", view_id).maybe_single().execute()
    return resp.data


def _load_saved_views_for_user(user_id: str, entity_type: str) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("saved_views")
        .select("id, view_name, is_default, is_shared, user_id")
        .eq("entity_type", entity_type)
        .or_(f"user_id.eq.{user_id},is_shared.eq.true")
        .order("view_name")
        .execute()
    )
    views = resp.data or []
    # feedback: [padelsbach] enrich team screeners with owner display names
    team_owner_ids = list({str(v["user_id"]) for v in views if str(v["user_id"]) != user_id})
    if team_owner_ids:
        owner_map = batch_resolve_users(team_owner_ids)
        for v in views:
            uid = str(v["user_id"])
            if uid != user_id and uid in owner_map:
                info = owner_map[uid]
                v["owner_name"] = info.get("display_name", "team") if isinstance(info, dict) else str(info)
    return views


def save_view(
    user_id: str,
    entity_type: str,
    view_name: str,
    columns: list[str],
    filters: dict,
    sort_by: str,
    sort_dir: str,
    is_shared: bool = False,
    is_default: bool = False,
) -> dict:
    """Create or update a saved view."""
    sb = get_supabase()

    if is_default:
        # Unset other defaults for this user+entity
        sb.table("saved_views").update({"is_default": False}).eq(
            "user_id", user_id
        ).eq("entity_type", entity_type).eq("is_default", True).execute()

    row = {
        "user_id": user_id,
        "entity_type": entity_type,
        "view_name": view_name,
        "columns": columns,
        "filters": filters,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "is_shared": is_shared,
        "is_default": is_default,
    }
    resp = sb.table("saved_views").insert(row).execute()
    return resp.data[0] if resp.data else {}


def delete_view(view_id: str, user_id: str, is_admin: bool = False) -> bool:
    """Delete a saved view. Only owner or admin."""
    sb = get_supabase()
    resp = sb.table("saved_views").select("user_id").eq("id", view_id).maybe_single().execute()
    if not resp.data:
        return False
    if str(resp.data["user_id"]) != user_id and not is_admin:
        return False
    sb.table("saved_views").delete().eq("id", view_id).execute()
    return True


def set_default_view(view_id: str, user_id: str, entity_type: str) -> bool:
    """Mark a view as the default for this user+entity."""
    sb = get_supabase()
    # Unset other defaults
    sb.table("saved_views").update({"is_default": False}).eq(
        "user_id", user_id
    ).eq("entity_type", entity_type).eq("is_default", True).execute()
    # Set this one
    sb.table("saved_views").update({"is_default": True}).eq("id", view_id).execute()
    return True


def update_view(
    view_id: str,
    user_id: str,
    columns: list[str],
    filters: dict,
    sort_by: str,
    sort_dir: str,
) -> bool:
    """Overwrite an existing saved view with new grid state. Only owner can overwrite."""
    sb = get_supabase()
    resp = sb.table("saved_views").select("user_id").eq("id", view_id).maybe_single().execute()
    if not resp.data:
        return False
    if str(resp.data["user_id"]) != user_id:
        return False
    sb.table("saved_views").update({
        "columns": columns,
        "filters": filters,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
    }).eq("id", view_id).execute()
    return True


def duplicate_view(view_id: str, user_id: str, new_name: str) -> Optional[dict]:
    """Clone a saved view with a new name. The clone belongs to the requesting user."""
    sb = get_supabase()
    resp = sb.table("saved_views").select("*").eq("id", view_id).maybe_single().execute()
    if not resp.data:
        return None
    original = resp.data
    row = {
        "user_id": user_id,
        "entity_type": original["entity_type"],
        "view_name": new_name,
        "columns": original.get("columns"),
        "filters": original.get("filters"),
        "sort_by": original.get("sort_by"),
        "sort_dir": original.get("sort_dir"),
        "is_shared": False,
        "is_default": False,
    }
    insert_resp = sb.table("saved_views").insert(row).execute()
    return insert_resp.data[0] if insert_resp.data else None


def rename_view(view_id: str, user_id: str, new_name: str) -> bool:
    """Rename a saved view. Only owner can rename."""
    sb = get_supabase()
    resp = sb.table("saved_views").select("user_id").eq("id", view_id).maybe_single().execute()
    if not resp.data:
        return False
    if str(resp.data["user_id"]) != user_id:
        return False
    sb.table("saved_views").update({"view_name": new_name}).eq("id", view_id).execute()
    return True

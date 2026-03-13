"""Activities router — full CRUD, search, filters, pagination, audit logging, follow-up task generation."""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from dependencies import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/activities", tags=["activities"])
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_reference_data(category: str, parent_value: Optional[str] = None) -> list[dict]:
    """Fetch active reference data for a dropdown category."""
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


def _log_field_change(
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


def _audit_changes(
    record_id: str,
    old_record: dict,
    new_data: dict,
    changed_by: UUID,
) -> None:
    """Compare old record with new data and log every changed field."""
    for field, new_val in new_data.items():
        old_val = old_record.get(field)
        if str(old_val) != str(new_val) and not (old_val is None and new_val is None):
            _log_field_change("activity", record_id, field, old_val, new_val, changed_by)


def _sync_activity_org_links(activity_id: str, org_ids: list[str]) -> None:
    """Replace all org links for an activity with the given list."""
    sb = get_supabase()
    # Remove existing links
    sb.table("activity_organization_links").delete().eq("activity_id", activity_id).execute()
    # Insert new links
    for org_id in org_ids:
        if org_id:
            sb.table("activity_organization_links").insert({
                "activity_id": activity_id,
                "organization_id": org_id,
            }).execute()


def _sync_activity_person_links(activity_id: str, person_ids: list[str]) -> None:
    """Replace all person links for an activity with the given list."""
    sb = get_supabase()
    # Remove existing links
    sb.table("activity_people_links").delete().eq("activity_id", activity_id).execute()
    # Insert new links
    for person_id in person_ids:
        if person_id:
            sb.table("activity_people_links").insert({
                "activity_id": activity_id,
                "person_id": person_id,
            }).execute()


def _create_follow_up_task(activity: dict, changed_by: UUID) -> None:
    """Auto-generate a task when follow_up_required is enabled."""
    sb = get_supabase()
    title = activity.get("title") or "Activity follow-up"
    sb.table("tasks").insert({
        "title": f"Follow up: {title}",
        "due_date": activity.get("follow_up_date"),
        "assigned_to": str(activity["author_id"]),
        "status": "open",
        "notes": activity.get("follow_up_notes") or "",
        "source": "activity_follow_up",
        "linked_record_type": "activity",
        "linked_record_id": str(activity["id"]),
        "created_by": str(changed_by),
    }).execute()


def _build_activity_data_from_form(form: dict) -> dict:
    """Extract activity fields from form data."""
    data = {}

    # Text fields
    title = (form.get("title") or "").strip()
    data["title"] = title if title else None

    # Required fields
    data["effective_date"] = (form.get("effective_date") or "").strip()
    data["activity_type"] = (form.get("activity_type") or "").strip()
    data["details"] = (form.get("details") or "").strip()

    # Optional text
    subtype = (form.get("subtype") or "").strip()
    data["subtype"] = subtype if subtype else None

    # Author
    data["author_id"] = (form.get("author_id") or "").strip()

    # Follow-up
    data["follow_up_required"] = form.get("follow_up_required") == "on"
    follow_up_date = (form.get("follow_up_date") or "").strip()
    data["follow_up_date"] = follow_up_date if follow_up_date else None
    follow_up_notes = (form.get("follow_up_notes") or "").strip()
    data["follow_up_notes"] = follow_up_notes if follow_up_notes else None

    # Fund tags (multi-select)
    fund_tags = form.getlist("fund_tags") if hasattr(form, "getlist") else []
    data["fund_tags"] = list(fund_tags) if fund_tags else None

    return data


# ---------------------------------------------------------------------------
# ORG SEARCH (HTMX autocomplete) — GET /activities/search-orgs
# ---------------------------------------------------------------------------

@router.get("/search-orgs", response_class=HTMLResponse)
async def search_orgs(
    request: Request,
    q: str = Query(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX endpoint: return org search results for autocomplete."""
    if not q or len(q) < 2:
        return HTMLResponse("")

    sb = get_supabase()
    resp = (
        sb.table("organizations")
        .select("id, company_name, organization_type, city, country")
        .eq("is_archived", False)
        .ilike("company_name", f"%{q}%")
        .order("company_name")
        .limit(10)
        .execute()
    )
    orgs = resp.data or []

    if not orgs:
        return HTMLResponse('<div class="px-4 py-2 text-sm text-gray-400">No organizations found</div>')

    html_parts = []
    for org in orgs:
        location = ", ".join(filter(None, [org.get("city"), org.get("country")]))
        safe_name = org["company_name"].replace("'", "&#39;").replace('"', "&quot;")
        html_parts.append(
            f'<button type="button" '
            f'class="w-full text-left px-4 py-2 hover:bg-brand-50 text-sm" '
            f"onclick=\"addOrg('{org['id']}', '{safe_name}')\">"
            f'<div class="font-medium text-gray-900">{org["company_name"]}</div>'
            f'<div class="text-xs text-gray-400">{(org.get("organization_type") or "").replace("_", " ").title()}'
            f'{" — " + location if location else ""}</div>'
            f'</button>'
        )
    return HTMLResponse("\n".join(html_parts))


# ---------------------------------------------------------------------------
# PERSON SEARCH (HTMX autocomplete) — GET /activities/search-people
# ---------------------------------------------------------------------------

@router.get("/search-people", response_class=HTMLResponse)
async def search_people(
    request: Request,
    q: str = Query(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX endpoint: return person search results for autocomplete."""
    if not q or len(q) < 2:
        return HTMLResponse("")

    sb = get_supabase()
    resp = (
        sb.table("people")
        .select("id, first_name, last_name, email, job_title")
        .eq("is_archived", False)
        .or_(f"first_name.ilike.%{q}%,last_name.ilike.%{q}%,email.ilike.%{q}%")
        .order("last_name")
        .limit(10)
        .execute()
    )
    people = resp.data or []

    if not people:
        return HTMLResponse('<div class="px-4 py-2 text-sm text-gray-400">No people found</div>')

    html_parts = []
    for p in people:
        safe_name = f"{p['first_name']} {p['last_name']}".replace("'", "&#39;").replace('"', "&quot;")
        html_parts.append(
            f'<button type="button" '
            f'class="w-full text-left px-4 py-2 hover:bg-brand-50 text-sm" '
            f"onclick=\"addPerson('{p['id']}', '{safe_name}')\">"
            f'<div class="font-medium text-gray-900">{p["first_name"]} {p["last_name"]}</div>'
            f'<div class="text-xs text-gray-400">{p.get("job_title") or ""}'
            f'{" — " + p["email"] if p.get("email") else ""}</div>'
            f'</button>'
        )
    return HTMLResponse("\n".join(html_parts))


# ---------------------------------------------------------------------------
# SUBTYPES (HTMX) — GET /activities/subtypes
# ---------------------------------------------------------------------------

@router.get("/subtypes", response_class=HTMLResponse)
async def get_subtypes(
    request: Request,
    activity_type: str = Query(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX endpoint: return subtype dropdown options for a given activity type."""
    if not activity_type:
        return HTMLResponse('<option value="">— Select subtype —</option>')

    subtypes = _get_reference_data("activity_subtype", parent_value=activity_type)
    if not subtypes:
        return HTMLResponse('<option value="">No subtypes</option>')

    html = '<option value="">— Select subtype —</option>'
    for st in subtypes:
        html += f'<option value="{st["value"]}">{st["label"]}</option>'
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# LIST — GET /activities
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def list_activities(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=10, le=100),
    search: str = Query("", alias="q"),
    activity_type: str = Query("", alias="type"),
    author_id: str = Query("", alias="author"),
    org_id: str = Query("", alias="org"),
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    sort_by: str = Query("effective_date"),
    sort_dir: str = Query("desc"),
):
    """List activities with filtering, search, sorting, and pagination."""
    sb = get_supabase()

    query = (
        sb.table("activities")
        .select("id, title, effective_date, activity_type, subtype, author_id, details, follow_up_required, created_at", count="exact")
        .eq("is_archived", False)
    )

    # Full-text search on details
    if search:
        query = query.or_(f"title.ilike.%{search}%,details.ilike.%{search}%")

    # Type filter
    if activity_type:
        query = query.eq("activity_type", activity_type)

    # Author filter
    if author_id:
        query = query.eq("author_id", author_id)

    # Date range
    if date_from:
        query = query.gte("effective_date", date_from)
    if date_to:
        query = query.lte("effective_date", date_to)

    # Sorting
    valid_sort_cols = ["effective_date", "title", "activity_type", "created_at"]
    if sort_by not in valid_sort_cols:
        sort_by = "effective_date"
    desc = sort_dir.lower() == "desc"
    query = query.order(sort_by, desc=desc)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    resp = query.execute()
    activities = resp.data or []
    total_count = resp.count or 0
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    # Enrich with author name and linked orgs
    for act in activities:
        # Author name
        if act.get("author_id"):
            author_resp = (
                sb.table("users")
                .select("display_name")
                .eq("id", str(act["author_id"]))
                .maybe_single()
                .execute()
            )
            act["author_name"] = author_resp.data["display_name"] if author_resp.data else "Unknown"
        else:
            act["author_name"] = "Unknown"

        # Linked orgs
        org_resp = (
            sb.table("activity_organization_links")
            .select("organization:organizations(id, company_name)")
            .eq("activity_id", str(act["id"]))
            .execute()
        )
        act["linked_orgs"] = [
            r["organization"] for r in (org_resp.data or []) if r.get("organization")
        ]

    # If filtering by org, we need to filter after enrichment
    if org_id:
        activities = [
            a for a in activities
            if any(o["id"] == org_id for o in a.get("linked_orgs", []))
        ]

    # Reference data for filters
    activity_types = _get_reference_data("activity_type")
    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()

    context = {
        "request": request,
        "user": current_user,
        "activities": activities,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "search": search,
        "activity_type": activity_type,
        "author_id": author_id,
        "org_id": org_id,
        "date_from": date_from,
        "date_to": date_to,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "activity_types": activity_types,
        "users": users_resp.data or [],
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("activities/_list_table.html", context)
    return templates.TemplateResponse("activities/list.html", context)


# ---------------------------------------------------------------------------
# CREATE FORM — GET /activities/new  (must be before /{activity_id})
# ---------------------------------------------------------------------------

@router.get("/new", response_class=HTMLResponse)
async def new_activity_form(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    org_id: str = Query("", alias="org"),
    person_id: str = Query("", alias="person"),
):
    """Render the new activity form. Optionally pre-fill org or person from query params."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()

    # Pre-fill org if provided
    pre_orgs = []
    if org_id:
        org_resp = (
            sb.table("organizations")
            .select("id, company_name")
            .eq("id", org_id)
            .eq("is_archived", False)
            .maybe_single()
            .execute()
        )
        if org_resp.data:
            pre_orgs = [org_resp.data]

    # Pre-fill person if provided
    pre_people = []
    if person_id:
        person_resp = (
            sb.table("people")
            .select("id, first_name, last_name")
            .eq("id", person_id)
            .eq("is_archived", False)
            .maybe_single()
            .execute()
        )
        if person_resp.data:
            p = person_resp.data
            p["display_name"] = f"{p['first_name']} {p['last_name']}"
            pre_people = [p]

    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
    funds_resp = sb.table("funds").select("id, fund_name, ticker").eq("is_active", True).order("fund_name").execute()

    context = {
        "request": request,
        "user": current_user,
        "activity": None,
        "pre_orgs": pre_orgs,
        "pre_people": pre_people,
        "activity_types": _get_reference_data("activity_type"),
        "activity_subtypes": [],
        "users": users_resp.data or [],
        "funds": funds_resp.data or [],
    }
    return templates.TemplateResponse("activities/form.html", context)


# ---------------------------------------------------------------------------
# DETAIL — GET /activities/{activity_id}
# ---------------------------------------------------------------------------

@router.get("/{activity_id}", response_class=HTMLResponse)
async def get_activity(
    request: Request,
    activity_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Activity detail page."""
    sb = get_supabase()

    resp = (
        sb.table("activities")
        .select("*")
        .eq("id", str(activity_id))
        .eq("is_archived", False)
        .maybe_single()
        .execute()
    )
    activity = resp.data
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Author name
    author_name = "Unknown"
    if activity.get("author_id"):
        author_resp = (
            sb.table("users")
            .select("display_name")
            .eq("id", str(activity["author_id"]))
            .maybe_single()
            .execute()
        )
        if author_resp.data:
            author_name = author_resp.data["display_name"]

    # Linked organizations
    org_links_resp = (
        sb.table("activity_organization_links")
        .select("organization:organizations(id, company_name, organization_type)")
        .eq("activity_id", str(activity_id))
        .execute()
    )
    linked_orgs = [
        r["organization"] for r in (org_links_resp.data or []) if r.get("organization")
    ]

    # Linked people
    people_links_resp = (
        sb.table("activity_people_links")
        .select("person:people(id, first_name, last_name, email, job_title)")
        .eq("activity_id", str(activity_id))
        .execute()
    )
    linked_people = [
        r["person"] for r in (people_links_resp.data or []) if r.get("person")
    ]

    # Fund tag names
    fund_names = []
    if activity.get("fund_tags"):
        for fid in activity["fund_tags"]:
            fund_resp = sb.table("funds").select("fund_name, ticker").eq("id", str(fid)).maybe_single().execute()
            if fund_resp.data:
                fund_names.append(fund_resp.data)

    # Related tasks (follow-up tasks)
    tasks_resp = (
        sb.table("tasks")
        .select("id, title, due_date, status, assigned_to")
        .eq("linked_record_type", "activity")
        .eq("linked_record_id", str(activity_id))
        .eq("is_archived", False)
        .order("created_at", desc=True)
        .execute()
    )
    related_tasks = tasks_resp.data or []

    context = {
        "request": request,
        "user": current_user,
        "activity": activity,
        "author_name": author_name,
        "linked_orgs": linked_orgs,
        "linked_people": linked_people,
        "fund_names": fund_names,
        "related_tasks": related_tasks,
    }
    return templates.TemplateResponse("activities/detail.html", context)


# ---------------------------------------------------------------------------
# CREATE — POST /activities
# ---------------------------------------------------------------------------

@router.post("/", response_class=HTMLResponse)
async def create_activity(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new activity."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    form = await request.form()
    form_data = dict(form)
    activity_data = _build_activity_data_from_form(form)

    # Linked orgs and people from form
    org_ids = form.getlist("linked_org_ids") if hasattr(form, "getlist") else []
    org_ids = [oid for oid in org_ids if oid]
    person_ids = form.getlist("linked_person_ids") if hasattr(form, "getlist") else []
    person_ids = [pid for pid in person_ids if pid]

    # Validation
    errors = []
    if not activity_data.get("effective_date"):
        errors.append("Effective Date is required.")
    if not activity_data.get("activity_type"):
        errors.append("Activity Type is required.")
    if not activity_data.get("details"):
        errors.append("Activity Details is required.")
    if not activity_data.get("author_id"):
        errors.append("Author is required.")
    if not org_ids:
        errors.append("At least one Linked Organization is required.")

    if errors:
        sb = get_supabase()
        users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
        funds_resp = sb.table("funds").select("id, fund_name, ticker").eq("is_active", True).order("fund_name").execute()

        # Rebuild pre-selected orgs and people for re-rendering
        pre_orgs = []
        for oid in org_ids:
            org_resp = sb.table("organizations").select("id, company_name").eq("id", oid).maybe_single().execute()
            if org_resp.data:
                pre_orgs.append(org_resp.data)
        pre_people = []
        for pid in person_ids:
            p_resp = sb.table("people").select("id, first_name, last_name").eq("id", pid).maybe_single().execute()
            if p_resp.data:
                p = p_resp.data
                p["display_name"] = f"{p['first_name']} {p['last_name']}"
                pre_people.append(p)

        subtypes = _get_reference_data("activity_subtype", parent_value=activity_data.get("activity_type")) if activity_data.get("activity_type") else []

        context = {
            "request": request,
            "user": current_user,
            "activity": activity_data,
            "pre_orgs": pre_orgs,
            "pre_people": pre_people,
            "errors": errors,
            "activity_types": _get_reference_data("activity_type"),
            "activity_subtypes": subtypes,
            "users": users_resp.data or [],
            "funds": funds_resp.data or [],
        }
        return templates.TemplateResponse("activities/form.html", context)

    # Default author to current user if not set
    if not activity_data.get("author_id"):
        activity_data["author_id"] = str(current_user.id)

    activity_data["created_by"] = str(current_user.id)

    sb = get_supabase()
    resp = sb.table("activities").insert(activity_data).execute()

    if resp.data:
        new_activity = resp.data[0]
        activity_id = new_activity["id"]

        # Create org and person links
        _sync_activity_org_links(str(activity_id), org_ids)
        _sync_activity_person_links(str(activity_id), person_ids)

        # Audit log
        _log_field_change("activity", str(activity_id), "_created", None, "record created", current_user.id)

        # Auto-generate follow-up task
        if new_activity.get("follow_up_required"):
            _create_follow_up_task(new_activity, current_user.id)

        return RedirectResponse(url=f"/activities/{activity_id}", status_code=303)

    raise HTTPException(status_code=500, detail="Failed to create activity")


# ---------------------------------------------------------------------------
# EDIT FORM — GET /activities/{activity_id}/edit
# ---------------------------------------------------------------------------

@router.get("/{activity_id}/edit", response_class=HTMLResponse)
async def edit_activity_form(
    request: Request,
    activity_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the edit activity form."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()
    resp = (
        sb.table("activities")
        .select("*")
        .eq("id", str(activity_id))
        .eq("is_archived", False)
        .maybe_single()
        .execute()
    )
    activity = resp.data
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Linked orgs
    org_links_resp = (
        sb.table("activity_organization_links")
        .select("organization:organizations(id, company_name)")
        .eq("activity_id", str(activity_id))
        .execute()
    )
    pre_orgs = [
        r["organization"] for r in (org_links_resp.data or []) if r.get("organization")
    ]

    # Linked people
    people_links_resp = (
        sb.table("activity_people_links")
        .select("person:people(id, first_name, last_name)")
        .eq("activity_id", str(activity_id))
        .execute()
    )
    pre_people = []
    for r in (people_links_resp.data or []):
        if r.get("person"):
            p = r["person"]
            p["display_name"] = f"{p['first_name']} {p['last_name']}"
            pre_people.append(p)

    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
    funds_resp = sb.table("funds").select("id, fund_name, ticker").eq("is_active", True).order("fund_name").execute()

    # Load subtypes for the current activity type
    subtypes = _get_reference_data("activity_subtype", parent_value=activity.get("activity_type")) if activity.get("activity_type") else []

    context = {
        "request": request,
        "user": current_user,
        "activity": activity,
        "pre_orgs": pre_orgs,
        "pre_people": pre_people,
        "activity_types": _get_reference_data("activity_type"),
        "activity_subtypes": subtypes,
        "users": users_resp.data or [],
        "funds": funds_resp.data or [],
    }
    return templates.TemplateResponse("activities/form.html", context)


# ---------------------------------------------------------------------------
# UPDATE — POST /activities/{activity_id}
# ---------------------------------------------------------------------------

@router.post("/{activity_id}", response_class=HTMLResponse)
async def update_activity(
    request: Request,
    activity_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an existing activity."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()

    old_resp = (
        sb.table("activities")
        .select("*")
        .eq("id", str(activity_id))
        .eq("is_archived", False)
        .maybe_single()
        .execute()
    )
    old_activity = old_resp.data
    if not old_activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    form = await request.form()
    form_data = dict(form)
    activity_data = _build_activity_data_from_form(form)

    # Linked orgs and people
    org_ids = form.getlist("linked_org_ids") if hasattr(form, "getlist") else []
    org_ids = [oid for oid in org_ids if oid]
    person_ids = form.getlist("linked_person_ids") if hasattr(form, "getlist") else []
    person_ids = [pid for pid in person_ids if pid]

    # Validation
    errors = []
    if not activity_data.get("effective_date"):
        errors.append("Effective Date is required.")
    if not activity_data.get("activity_type"):
        errors.append("Activity Type is required.")
    if not activity_data.get("details"):
        errors.append("Activity Details is required.")
    if not activity_data.get("author_id"):
        errors.append("Author is required.")
    if not org_ids:
        errors.append("At least one Linked Organization is required.")

    if errors:
        users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
        funds_resp = sb.table("funds").select("id, fund_name, ticker").eq("is_active", True).order("fund_name").execute()

        pre_orgs = []
        for oid in org_ids:
            org_resp = sb.table("organizations").select("id, company_name").eq("id", oid).maybe_single().execute()
            if org_resp.data:
                pre_orgs.append(org_resp.data)
        pre_people = []
        for pid in person_ids:
            p_resp = sb.table("people").select("id, first_name, last_name").eq("id", pid).maybe_single().execute()
            if p_resp.data:
                p = p_resp.data
                p["display_name"] = f"{p['first_name']} {p['last_name']}"
                pre_people.append(p)

        subtypes = _get_reference_data("activity_subtype", parent_value=activity_data.get("activity_type")) if activity_data.get("activity_type") else []

        context = {
            "request": request,
            "user": current_user,
            "activity": {**old_activity, **activity_data},
            "pre_orgs": pre_orgs,
            "pre_people": pre_people,
            "errors": errors,
            "activity_types": _get_reference_data("activity_type"),
            "activity_subtypes": subtypes,
            "users": users_resp.data or [],
            "funds": funds_resp.data or [],
        }
        return templates.TemplateResponse("activities/form.html", context)

    # Audit log every changed field
    _audit_changes(str(activity_id), old_activity, activity_data, current_user.id)

    # Update
    sb.table("activities").update(activity_data).eq("id", str(activity_id)).execute()

    # Sync links
    _sync_activity_org_links(str(activity_id), org_ids)
    _sync_activity_person_links(str(activity_id), person_ids)

    # Follow-up task: if follow_up was just toggled ON, create task
    was_follow_up = old_activity.get("follow_up_required", False)
    is_follow_up = activity_data.get("follow_up_required", False)
    if is_follow_up and not was_follow_up:
        updated_activity = {**old_activity, **activity_data, "id": str(activity_id)}
        _create_follow_up_task(updated_activity, current_user.id)

    return RedirectResponse(url=f"/activities/{activity_id}", status_code=303)


# ---------------------------------------------------------------------------
# ARCHIVE (soft delete) — POST /activities/{activity_id}/archive
# ---------------------------------------------------------------------------

@router.post("/{activity_id}/archive", response_class=HTMLResponse)
async def archive_activity(
    request: Request,
    activity_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-delete an activity."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    sb.table("activities").update({"is_archived": True}).eq("id", str(activity_id)).execute()
    _log_field_change("activity", str(activity_id), "is_archived", False, True, current_user.id)

    if request.headers.get("HX-Request"):
        return HTMLResponse('<p class="text-sm text-green-600">Activity archived.</p>')
    return RedirectResponse(url="/activities", status_code=303)

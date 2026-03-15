"""Activities router — full CRUD, search, filters, pagination, audit logging, follow-up task generation."""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from db.helpers import get_reference_data, log_field_change, audit_changes
from db.field_service import get_field_definitions, enrich_field_definitions
from services.form_service import build_form_context, parse_form_data, validate_form_data, get_users_for_lookup
from services.grid_service import build_grid_context
from dependencies import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/activities", tags=["activities"])
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _create_follow_up_task(activity: dict, changed_by: UUID, assignee_id: str = None) -> None:
    """Auto-generate a task when follow_up_required is enabled.

    If *assignee_id* is provided, the task is assigned to that user;
    otherwise it defaults to the activity author.
    """
    sb = get_supabase()
    title = activity.get("title") or "Activity follow-up"
    assigned_to = assignee_id if assignee_id else str(activity["author_id"])
    sb.table("tasks").insert({
        "title": f"Follow up: {title}",
        "due_date": activity.get("follow_up_date"),
        "assigned_to": assigned_to,
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
        .eq("is_deleted", False)
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
        .eq("is_deleted", False)
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
# ORG PEOPLE SUGGESTIONS — GET /activities/org-people
# ---------------------------------------------------------------------------

@router.get("/org-people", response_class=HTMLResponse)
async def org_people(
    request: Request,
    org_id: str = Query(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX endpoint: return people at a given org as quick-add suggestions."""
    if not org_id:
        return HTMLResponse("")

    sb = get_supabase()

    # Get org name
    org_resp = sb.table("organizations").select("company_name").eq("id", org_id).maybe_single().execute()
    org_name = org_resp.data["company_name"] if org_resp.data else "Organization"

    # Get people at org
    links_resp = (
        sb.table("person_organization_links")
        .select("person_id")
        .eq("organization_id", org_id)
        .in_("link_type", ["primary", "secondary"])
        .execute()
    )
    person_ids = [r["person_id"] for r in (links_resp.data or [])]

    if not person_ids:
        return HTMLResponse("")

    people_resp = (
        sb.table("people")
        .select("id, first_name, last_name, email, job_title")
        .in_("id", person_ids)
        .eq("is_deleted", False)
        .order("last_name")
        .limit(20)
        .execute()
    )
    people = people_resp.data or []

    if not people:
        return HTMLResponse("")

    html_parts = [
        f'<div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">People at {org_name}</div>'
    ]
    for p in people:
        safe_name = f"{p['first_name']} {p['last_name']}".replace("'", "&#39;").replace('"', "&quot;")
        subtitle = p.get("job_title") or ""
        if p.get("email"):
            subtitle += (" — " + p["email"]) if subtitle else p["email"]
        html_parts.append(
            f'<button type="button" '
            f'class="w-full text-left px-3 py-2 rounded-md bg-blue-50 hover:bg-blue-100 text-sm mb-1" '
            f"onclick=\"addPerson('{p['id']}', '{safe_name}')\">"
            f'<div class="font-medium text-gray-900">{p["first_name"]} {p["last_name"]}</div>'
            f'<div class="text-xs text-gray-500">{subtitle}</div>'
            f'</button>'
        )
    return HTMLResponse("\n".join(html_parts))


# ---------------------------------------------------------------------------
# PERSON PRIMARY ORG — GET /activities/person-primary-org
# ---------------------------------------------------------------------------

@router.get("/person-primary-org")
async def person_primary_org(
    request: Request,
    person_id: str = Query(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return the primary organization for a person as JSON."""
    if not person_id:
        return JSONResponse({"org_id": None})

    sb = get_supabase()

    # Find the primary org link
    link_resp = (
        sb.table("person_organization_links")
        .select("organization_id")
        .eq("person_id", person_id)
        .eq("link_type", "primary")
        .maybe_single()
        .execute()
    )

    if not link_resp.data:
        return JSONResponse({"org_id": None})

    org_id = link_resp.data["organization_id"]

    # Get org name
    org_resp = (
        sb.table("organizations")
        .select("id, company_name")
        .eq("id", org_id)
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )

    if not org_resp.data:
        return JSONResponse({"org_id": None})

    return JSONResponse({"org_id": str(org_resp.data["id"]), "company_name": org_resp.data["company_name"]})


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

    subtypes = get_reference_data("activity_subtype", parent_value=activity_type)
    if not subtypes:
        return HTMLResponse('<option value="">No subtypes</option>')

    html = '<option value="">— Select subtype —</option>'
    for st in subtypes:
        html += f'<option value="{st["value"]}">{st["label"]}</option>'
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# MY ACTIVITIES — GET /activities/my-activities
# ---------------------------------------------------------------------------

@router.get("/my-activities", response_class=HTMLResponse)
async def my_activities(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List activities related to the current user's coverage."""
    sb = get_supabase()

    # Multi-step coverage query to find activity IDs
    my_activity_ids = set()

    # 1. Activities authored by user
    auth_resp = sb.table("activities").select("id").eq("author_id", str(current_user.id)).eq("is_deleted", False).execute()
    my_activity_ids |= {str(a["id"]) for a in (auth_resp.data or [])}

    # 2. Activities linked to people where user is coverage owner
    covered_people = sb.table("people").select("id").eq("coverage_owner", str(current_user.id)).eq("is_deleted", False).execute()
    person_ids = [str(p["id"]) for p in (covered_people.data or [])]
    if person_ids:
        apl_resp = sb.table("activity_people_links").select("activity_id").in_("person_id", person_ids).execute()
        my_activity_ids |= {str(r["activity_id"]) for r in (apl_resp.data or [])}

    # 3. Activities linked to orgs where user owns leads
    owned_leads = sb.table("leads").select("organization_id").eq("aksia_owner_id", str(current_user.id)).eq("is_deleted", False).execute()
    org_ids = list({str(l["organization_id"]) for l in (owned_leads.data or []) if l.get("organization_id")})
    if org_ids:
        aol_resp = sb.table("activity_organization_links").select("activity_id").in_("organization_id", org_ids).execute()
        my_activity_ids |= {str(r["activity_id"]) for r in (aol_resp.data or [])}

    if not my_activity_ids:
        my_activity_ids = {"00000000-0000-0000-0000-000000000000"}

    ctx = build_grid_context("activity", request, current_user, base_url="/activities/my-activities",
                             extra_filters={"_activity_ids": list(my_activity_ids)})

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("components/_grid.html", {"request": request, **ctx})

    activity_types = get_reference_data("activity_type")
    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()

    ctx.update({
        "user": current_user,
        "view_mode": "my_activities",
        "total_count": ctx["pagination"]["total"],
        "search": ctx["filters"].get("q", ""),
        "activity_type": ctx["filters"].get("type", ""),
        "author_id": ctx["filters"].get("author", ""),
        "org_id": ctx["filters"].get("org", ""),
        "date_from": ctx["filters"].get("from", ""),
        "date_to": ctx["filters"].get("to", ""),
        "activity_types": activity_types,
        "users": users_resp.data or [],
    })
    return templates.TemplateResponse("activities/list.html", {"request": request, **ctx})


# ---------------------------------------------------------------------------
# LIST — GET /activities
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def list_activities(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List activities with filtering, search, sorting, and pagination."""
    ctx = build_grid_context("activity", request, current_user, base_url="/activities")

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("components/_grid.html", {"request": request, **ctx})

    sb = get_supabase()
    activity_types = get_reference_data("activity_type")
    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()

    ctx.update({
        "user": current_user,
        "view_mode": "all_activities",
        "total_count": ctx["pagination"]["total"],
        "search": ctx["filters"].get("q", ""),
        "activity_type": ctx["filters"].get("type", ""),
        "author_id": ctx["filters"].get("author", ""),
        "org_id": ctx["filters"].get("org", ""),
        "date_from": ctx["filters"].get("from", ""),
        "date_to": ctx["filters"].get("to", ""),
        "activity_types": activity_types,
        "users": users_resp.data or [],
    })
    return templates.TemplateResponse("activities/list.html", {"request": request, **ctx})


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
            .eq("is_deleted", False)
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
            .eq("is_deleted", False)
            .maybe_single()
            .execute()
        )
        if person_resp.data:
            p = person_resp.data
            p["display_name"] = f"{p['first_name']} {p['last_name']}"
            pre_people = [p]

    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
    users_list = users_resp.data or []
    funds_resp = sb.table("funds").select("id, fund_name, ticker").eq("is_active", True).order("fund_name").execute()

    form_ctx = build_form_context("activity", record=None, extra_context={"users": users_list})

    context = {
        "request": request,
        "user": current_user,
        "activity": None,
        "pre_orgs": pre_orgs,
        "pre_people": pre_people,
        "activity_types": get_reference_data("activity_type"),
        "activity_subtypes": [],
        "users": users_list,
        "funds": funds_resp.data or [],
        "sections": form_ctx["sections"],
        "field_defs": form_ctx["field_defs"],
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
        .eq("is_deleted", False)
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
        .eq("is_deleted", False)
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

    # Use dynamic form service for parsing and validation
    field_defs = get_field_definitions("activity", active_only=True)
    field_defs = enrich_field_definitions(field_defs)
    activity_data = parse_form_data("activity", form, field_defs)

    # Linked orgs and people from form (entity-specific, not in field_defs)
    org_ids = form.getlist("linked_org_ids") if hasattr(form, "getlist") else []
    org_ids = [oid for oid in org_ids if oid]
    person_ids = form.getlist("linked_person_ids") if hasattr(form, "getlist") else []
    person_ids = [pid for pid in person_ids if pid]

    # Dynamic validation from field_defs
    errors = validate_form_data("activity", activity_data, field_defs)

    # Entity-specific validation (not captured by field_defs)
    if not org_ids:
        errors.append("At least one Linked Organization is required.")
    if activity_data.get("follow_up_required") and not activity_data.get("follow_up_notes"):
        errors.append("Follow-Up Notes is required when Follow-Up Required is checked.")

    if errors:
        sb = get_supabase()
        users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
        users_list = users_resp.data or []
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

        subtypes = get_reference_data("activity_subtype", parent_value=activity_data.get("activity_type")) if activity_data.get("activity_type") else []

        form_ctx = build_form_context("activity", record=None, extra_context={"users": users_list})

        context = {
            "request": request,
            "user": current_user,
            "activity": activity_data,
            "pre_orgs": pre_orgs,
            "pre_people": pre_people,
            "errors": errors,
            "activity_types": get_reference_data("activity_type"),
            "activity_subtypes": subtypes,
            "users": users_list,
            "funds": funds_resp.data or [],
            "sections": form_ctx["sections"],
            "field_defs": form_ctx["field_defs"],
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
        log_field_change("activity", str(activity_id), "_created", None, "record created", current_user.id)

        # Auto-generate follow-up task
        if new_activity.get("follow_up_required"):
            assignee_id = (form_data.get("follow_up_assignee_id") or "").strip() or None
            _create_follow_up_task(new_activity, current_user.id, assignee_id=assignee_id)

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
        .eq("is_deleted", False)
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
    users_list = users_resp.data or []
    funds_resp = sb.table("funds").select("id, fund_name, ticker").eq("is_active", True).order("fund_name").execute()

    # Load subtypes for the current activity type
    subtypes = get_reference_data("activity_subtype", parent_value=activity.get("activity_type")) if activity.get("activity_type") else []

    form_ctx = build_form_context("activity", record=activity, extra_context={"users": users_list})

    context = {
        "request": request,
        "user": current_user,
        "activity": activity,
        "pre_orgs": pre_orgs,
        "pre_people": pre_people,
        "activity_types": get_reference_data("activity_type"),
        "activity_subtypes": subtypes,
        "users": users_list,
        "funds": funds_resp.data or [],
        "sections": form_ctx["sections"],
        "field_defs": form_ctx["field_defs"],
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
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    old_activity = old_resp.data
    if not old_activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    form = await request.form()
    form_data = dict(form)

    # Use dynamic form service for parsing and validation
    field_defs = get_field_definitions("activity", active_only=True)
    field_defs = enrich_field_definitions(field_defs)
    activity_data = parse_form_data("activity", form, field_defs)

    # Linked orgs and people (entity-specific, not in field_defs)
    org_ids = form.getlist("linked_org_ids") if hasattr(form, "getlist") else []
    org_ids = [oid for oid in org_ids if oid]
    person_ids = form.getlist("linked_person_ids") if hasattr(form, "getlist") else []
    person_ids = [pid for pid in person_ids if pid]

    # Dynamic validation from field_defs
    errors = validate_form_data("activity", activity_data, field_defs, record=old_activity)

    # Entity-specific validation (not captured by field_defs)
    if not org_ids:
        errors.append("At least one Linked Organization is required.")
    if activity_data.get("follow_up_required") and not activity_data.get("follow_up_notes"):
        errors.append("Follow-Up Notes is required when Follow-Up Required is checked.")

    if errors:
        users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
        users_list = users_resp.data or []
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

        subtypes = get_reference_data("activity_subtype", parent_value=activity_data.get("activity_type")) if activity_data.get("activity_type") else []

        form_ctx = build_form_context("activity", record=old_activity, extra_context={"users": users_list})

        context = {
            "request": request,
            "user": current_user,
            "activity": {**old_activity, **activity_data},
            "pre_orgs": pre_orgs,
            "pre_people": pre_people,
            "errors": errors,
            "activity_types": get_reference_data("activity_type"),
            "activity_subtypes": subtypes,
            "users": users_list,
            "funds": funds_resp.data or [],
            "sections": form_ctx["sections"],
            "field_defs": form_ctx["field_defs"],
        }
        return templates.TemplateResponse("activities/form.html", context)

    # Audit log every changed field
    audit_changes("activity", str(activity_id), old_activity, activity_data, current_user.id)

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
        assignee_id = (form_data.get("follow_up_assignee_id") or "").strip() or None
        _create_follow_up_task(updated_activity, current_user.id, assignee_id=assignee_id)

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
    sb.table("activities").update({"is_deleted": True}).eq("id", str(activity_id)).execute()
    log_field_change("activity", str(activity_id), "is_deleted", False, True, current_user.id)

    if request.headers.get("HX-Request"):
        return HTMLResponse('<p class="text-sm text-green-600">Activity archived.</p>')
    return RedirectResponse(url="/activities", status_code=303)

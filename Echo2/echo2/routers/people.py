"""People router — full CRUD, search, duplicate detection, DNC enforcement, audit logging."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from db.helpers import get_reference_data, log_field_change, audit_changes
from db.field_service import get_field_definitions, enrich_field_definitions
from services.form_service import build_form_context, parse_form_data, validate_form_data, get_users_for_lookup
from dependencies import CurrentUser, get_current_user, require_role
from services.grid_service import build_grid_context

router = APIRouter(prefix="/people", tags=["people"])
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_duplicates(
    first_name: str,
    last_name: str,
    email: Optional[str] = None,
    exclude_id: Optional[str] = None,
    source_id: Optional[str] = None,
) -> list[dict]:
    """Return potential duplicate people based on email match or name similarity."""
    sb = get_supabase()
    duplicates = []

    # Exact email match
    if email:
        email_resp = (
            sb.table("people")
            .select("id, first_name, last_name, email, job_title")
            .eq("is_deleted", False)
            .eq("email", email)
            .execute()
        )
        if email_resp.data:
            for row in email_resp.data:
                row["org_name"] = None
            duplicates.extend(email_resp.data)

    # Fuzzy name match via pg_trgm
    name_resp = sb.rpc("check_person_name_similarity", {
        "search_first": first_name,
        "search_last": last_name,
        "similarity_threshold": 0.4,
    }).execute()
    if name_resp.data:
        existing_ids = {d["id"] for d in duplicates}
        for row in name_resp.data:
            if row["id"] not in existing_ids:
                duplicates.append(row)

    # Enrich email-matched rows with primary org name
    for dupe in duplicates:
        if dupe.get("org_name") is None and dupe.get("id"):
            link_resp = (
                sb.table("person_organization_links")
                .select("organization:organizations(company_name)")
                .eq("person_id", str(dupe["id"]))
                .eq("link_type", "primary")
                .limit(1)
                .execute()
            )
            if link_resp.data and link_resp.data[0].get("organization"):
                dupe["org_name"] = link_resp.data[0]["organization"]["company_name"]

    # Exclude self when editing
    if exclude_id:
        duplicates = [d for d in duplicates if str(d["id"]) != exclude_id]

    # Filter out suppressed pairs
    if source_id:
        supp_resp = sb.table("duplicate_suppressions").select("record_id_a, record_id_b").eq("entity_type", "person").or_(f"record_id_a.eq.{source_id},record_id_b.eq.{source_id}").execute()
        if supp_resp.data:
            suppressed_ids = set()
            for s in supp_resp.data:
                suppressed_ids.add(s["record_id_a"])
                suppressed_ids.add(s["record_id_b"])
            suppressed_ids.discard(source_id)
            duplicates = [d for d in duplicates if str(d["id"]) not in suppressed_ids]

    return duplicates


def _enforce_do_not_contact(person_id: str, changed_by: UUID) -> int:
    """Remove person from all distribution lists when DNC is enabled. Returns count removed."""
    sb = get_supabase()
    memberships = (
        sb.table("distribution_list_members")
        .select("id, distribution_list_id")
        .eq("person_id", person_id)
        .execute()
    )
    removed = 0
    for m in (memberships.data or []):
        sb.table("distribution_list_members").delete().eq("id", m["id"]).execute()
        log_field_change(
            "person", person_id, "distribution_list_removal",
            m["distribution_list_id"], None, changed_by,
        )
        removed += 1
    return removed


def _build_person_data_from_form(form) -> dict:
    """Extract person fields from form data, handling type conversion."""
    data = {}

    # Text fields
    for f in ["first_name", "last_name", "email", "phone", "job_title",
              "backstop_company_id", "ostrako_id"]:
        val = form.get(f, "").strip() if form.get(f) else ""
        data[f] = val if val else None

    # Required text fields (keep value even if empty for validation)
    data["first_name"] = (form.get("first_name") or "").strip()
    data["last_name"] = (form.get("last_name") or "").strip()

    # Multi-select: asset classes of interest
    asset_classes = form.getlist("asset_classes_of_interest") if hasattr(form, "getlist") else []
    data["asset_classes_of_interest"] = list(asset_classes) if asset_classes else None

    # Coverage owner (user UUID)
    coverage = (form.get("coverage_owner") or "").strip()
    data["coverage_owner"] = coverage if coverage else None

    # Booleans (checkboxes)
    data["do_not_contact"] = form.get("do_not_contact") == "on"
    data["legal_compliance_notices"] = form.get("legal_compliance_notices") == "on"

    return data


def _sync_org_links(person_id: str, form: dict, changed_by: UUID) -> None:
    """Create/update organization links from form data."""
    sb = get_supabase()

    primary_org_id = (form.get("primary_organization_id") or "").strip()
    primary_job_title = (form.get("primary_job_title_at_org") or "").strip() or None

    if not primary_org_id:
        return

    # Check existing primary
    existing = (
        sb.table("person_organization_links")
        .select("id, organization_id, link_type")
        .eq("person_id", person_id)
        .eq("link_type", "primary")
        .execute()
    )

    today = str(__import__("datetime").date.today())

    if existing.data:
        old_link = existing.data[0]
        if old_link["organization_id"] != primary_org_id:
            # Mark old primary as former with end_date
            sb.table("person_organization_links").update({
                "link_type": "former",
                "end_date": today,
            }).eq("id", old_link["id"]).execute()
            log_field_change("person", person_id, "primary_organization",
                              old_link["organization_id"], primary_org_id, changed_by)

            # Check if there's already a link to the new org
            new_existing = (
                sb.table("person_organization_links")
                .select("id")
                .eq("person_id", person_id)
                .eq("organization_id", primary_org_id)
                .execute()
            )
            if new_existing.data:
                sb.table("person_organization_links").update({
                    "link_type": "primary",
                    "job_title_at_org": primary_job_title,
                    "start_date": today,
                    "end_date": None,
                }).eq("id", new_existing.data[0]["id"]).execute()
            else:
                sb.table("person_organization_links").insert({
                    "person_id": person_id,
                    "organization_id": primary_org_id,
                    "link_type": "primary",
                    "job_title_at_org": primary_job_title,
                    "start_date": today,
                }).execute()
        else:
            # Same org, just update job title
            sb.table("person_organization_links").update({
                "job_title_at_org": primary_job_title,
            }).eq("id", old_link["id"]).execute()
    else:
        # No existing primary — create one with start_date
        sb.table("person_organization_links").insert({
            "person_id": person_id,
            "organization_id": primary_org_id,
            "link_type": "primary",
            "job_title_at_org": primary_job_title,
            "start_date": today,
        }).execute()


# ---------------------------------------------------------------------------
# ORG SEARCH (HTMX autocomplete) — GET /people/search-orgs
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
            f"onclick=\"selectOrg('{org['id']}', '{safe_name}')\">"
            f'<div class="font-medium text-gray-900">{org["company_name"]}</div>'
            f'<div class="text-xs text-gray-400">{(org.get("organization_type") or "").replace("_", " ").title()}'
            f'{" — " + location if location else ""}</div>'
            f'</button>'
        )
    return HTMLResponse("\n".join(html_parts))


# ---------------------------------------------------------------------------
# LIST — GET /people
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def list_people(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List people with filtering, search, sorting, and pagination."""
    ctx = build_grid_context("person", request, current_user, base_url="/people")

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("components/_grid.html", {"request": request, **ctx})

    ctx.update({
        "user": current_user,
        "view_mode": "all_people",
        "total_count": ctx["pagination"]["total"],
        "search": ctx["filters"].get("q", ""),
        "asset_class": ctx["filters"].get("ac", ""),
        "dnc": ctx["filters"].get("dnc", ""),
        "organization_id": ctx["filters"].get("org", ""),
        "asset_classes": get_reference_data("asset_class"),
    })
    return templates.TemplateResponse("people/list.html", {"request": request, **ctx})


# ---------------------------------------------------------------------------
# MY PEOPLE — GET /people/my-people
# ---------------------------------------------------------------------------

@router.get("/my-people", response_class=HTMLResponse)
async def my_people(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List people where the current user is coverage owner."""
    sb = get_supabase()
    my_resp = (
        sb.table("people")
        .select("id")
        .eq("coverage_owner", str(current_user.id))
        .eq("is_deleted", False)
        .execute()
    )
    my_ids = [str(p["id"]) for p in (my_resp.data or [])]
    if not my_ids:
        my_ids = ["00000000-0000-0000-0000-000000000000"]

    ctx = build_grid_context("person", request, current_user, base_url="/people/my-people",
                             extra_filters={"_org_ids": my_ids})

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("components/_grid.html", {"request": request, **ctx})

    ctx.update({
        "user": current_user,
        "view_mode": "my_people",
        "total_count": ctx["pagination"]["total"],
        "search": ctx["filters"].get("q", ""),
        "asset_class": ctx["filters"].get("ac", ""),
        "dnc": ctx["filters"].get("dnc", ""),
        "organization_id": ctx["filters"].get("org", ""),
        "asset_classes": get_reference_data("asset_class"),
    })
    return templates.TemplateResponse("people/list.html", {"request": request, **ctx})


# ---------------------------------------------------------------------------
# CREATE FORM — GET /people/new  (must be before /{person_id})
# ---------------------------------------------------------------------------

@router.get("/new", response_class=HTMLResponse)
async def new_person_form(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    org_id: str = Query("", alias="org"),
):
    """Render the new person form. Optionally pre-fill org from query param."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()
    pre_org = None
    if org_id:
        org_resp = (
            sb.table("organizations")
            .select("id, company_name")
            .eq("id", org_id)
            .eq("is_deleted", False)
            .maybe_single()
            .execute()
        )
        pre_org = org_resp.data

    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
    users_list = users_resp.data or []

    form_ctx = build_form_context("person", record=None, extra_context={"users": users_list})

    context = {
        "request": request,
        "user": current_user,
        "person": None,
        "person_org_links": [],
        "pre_org": pre_org,
        "asset_classes": get_reference_data("asset_class"),
        "users": users_list,
        "sections": form_ctx["sections"],
        "field_defs": form_ctx["field_defs"],
    }
    return templates.TemplateResponse("people/form.html", context)


# ---------------------------------------------------------------------------
# DUPLICATE CHECK (HTMX) — GET /people/check-duplicates
# ---------------------------------------------------------------------------

@router.get("/check-duplicates", response_class=HTMLResponse)
async def check_duplicates(
    request: Request,
    first_name: str = Query(""),
    last_name: str = Query(""),
    email: str = Query(""),
    exclude_id: str = Query(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX endpoint: return duplicate warning HTML fragment."""
    if not last_name or len(last_name) < 2:
        return HTMLResponse("")

    dupes = _check_duplicates(first_name, last_name, email or None, exclude_id or None, source_id=exclude_id or None)
    if not dupes:
        return HTMLResponse("")

    context = {
        "request": request,
        "duplicates": dupes,
        "source_id": exclude_id or None,
        "entity_type": "person",
    }
    return templates.TemplateResponse("people/_duplicate_warning.html", context)


# ---------------------------------------------------------------------------
# SUPPRESS DUPLICATE — POST /people/{person_id}/suppress-duplicate
# ---------------------------------------------------------------------------

@router.post("/{person_id}/suppress-duplicate", response_class=HTMLResponse)
async def suppress_duplicate(
    request: Request,
    person_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Suppress a duplicate pair so it no longer shows as a warning."""
    form = await request.form()
    other_id = form.get("other_id", "")
    if not other_id:
        raise HTTPException(status_code=400, detail="Missing other_id")

    # Normalize: smaller UUID as record_id_a
    id_a, id_b = (min(person_id, other_id), max(person_id, other_id))

    sb = get_supabase()
    sb.table("duplicate_suppressions").upsert({
        "entity_type": "person",
        "record_id_a": id_a,
        "record_id_b": id_b,
        "suppressed_by": str(current_user.id),
    }).execute()

    log_field_change("person", person_id, "duplicate_suppressed", other_id, "suppressed", current_user.id)

    # Re-run duplicate check and return updated list
    person_resp = sb.table("people").select("first_name, last_name, email").eq("id", person_id).maybe_single().execute()
    if person_resp.data:
        dupes = _check_duplicates(
            person_resp.data["first_name"], person_resp.data["last_name"],
            person_resp.data.get("email"), exclude_id=person_id, source_id=person_id,
        )
    else:
        dupes = []

    context = {
        "request": request,
        "duplicates": dupes,
        "source_id": person_id,
        "entity_type": "person",
    }
    return templates.TemplateResponse("people/_duplicate_warning.html", context)


# ---------------------------------------------------------------------------
# DETAIL — GET /people/{person_id}
# ---------------------------------------------------------------------------

@router.get("/{person_id}", response_class=HTMLResponse)
async def get_person(
    request: Request,
    person_id: UUID,
    tab: str = Query("organizations"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Person detail page with tabbed linked records."""
    sb = get_supabase()

    resp = (
        sb.table("people")
        .select("*")
        .eq("id", str(person_id))
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    person = resp.data
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    # Linked organizations
    org_links_resp = (
        sb.table("person_organization_links")
        .select("id, link_type, job_title_at_org, organization:organizations(id, company_name, organization_type, relationship_type, city, country)")
        .eq("person_id", str(person_id))
        .execute()
    )
    org_links = org_links_resp.data or []

    # Linked activities
    activities_resp = (
        sb.table("activity_people_links")
        .select("activity:activities(id, title, effective_date, activity_type, subtype, details, created_at)")
        .eq("person_id", str(person_id))
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    activities = activities_resp.data or []

    # Distribution list memberships
    dl_resp = (
        sb.table("distribution_list_members")
        .select("id, joined_at, is_active, distribution_list:distribution_lists(id, list_name, list_type, asset_class, brand)")
        .eq("person_id", str(person_id))
        .eq("is_active", True)
        .execute()
    )
    distribution_lists = dl_resp.data or []

    # Coverage owner name
    coverage_name = None
    if person.get("coverage_owner"):
        user_resp = (
            sb.table("users")
            .select("display_name")
            .eq("id", str(person["coverage_owner"]))
            .maybe_single()
            .execute()
        )
        if user_resp.data:
            coverage_name = user_resp.data["display_name"]

    context = {
        "request": request,
        "user": current_user,
        "person": person,
        "org_links": org_links,
        "activities": activities,
        "distribution_lists": distribution_lists,
        "coverage_name": coverage_name,
        "active_tab": tab,
    }

    # Only return tab partial for explicit HTMX tab clicks, not hx-boost page navigations
    if request.headers.get("HX-Request") and tab:
        return templates.TemplateResponse(f"people/_tab_{tab}.html", context)
    return templates.TemplateResponse("people/detail.html", context)


# ---------------------------------------------------------------------------
# CREATE — POST /people
# ---------------------------------------------------------------------------

@router.post("/", response_class=HTMLResponse)
async def create_person(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new person."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    form = await request.form()
    form_data = dict(form)

    # Dynamic form parsing
    field_defs = get_field_definitions("person", active_only=True)
    field_defs = enrich_field_definitions(field_defs)
    person_data = parse_form_data("person", form, field_defs)

    # Entity-specific extraction (org autocomplete, multi-select)
    primary_org_id = (form_data.get("primary_organization_id") or "").strip()
    job_title_at_org = (form_data.get("primary_job_title_at_org") or "").strip() or None
    if "asset_classes_of_interest" not in person_data or person_data["asset_classes_of_interest"] is None:
        asset_classes = form.getlist("asset_classes_of_interest") if hasattr(form, "getlist") else []
        person_data["asset_classes_of_interest"] = list(asset_classes) if asset_classes else None

    # Dynamic validation
    errors = validate_form_data("person", person_data, field_defs)

    # Entity-specific validation
    if not person_data.get("first_name"):
        if "First Name is required." not in errors:
            errors.append("First Name is required.")
    if not person_data.get("last_name"):
        if "Last Name is required." not in errors:
            errors.append("Last Name is required.")
    if not primary_org_id:
        errors.append("Primary Organization is required.")

    if errors:
        sb = get_supabase()
        users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
        users_list = users_resp.data or []
        form_ctx = build_form_context("person", record=None, extra_context={"users": users_list})
        context = {
            "request": request,
            "user": current_user,
            "person": person_data,
            "person_org_links": [],
            "pre_org": None,
            "errors": errors,
            "asset_classes": get_reference_data("asset_class"),
            "users": users_list,
            "sections": form_ctx["sections"],
            "field_defs": form_ctx["field_defs"],
        }
        return templates.TemplateResponse("people/form.html", context)

    # Check for duplicates (unless user confirmed)
    if form_data.get("confirm_duplicate") != "yes":
        dupes = _check_duplicates(
            person_data["first_name"], person_data["last_name"],
            person_data.get("email"),
        )
        if dupes:
            sb = get_supabase()
            users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
            users_list = users_resp.data or []
            pre_org = None
            if primary_org_id:
                org_resp = sb.table("organizations").select("id, company_name").eq("id", primary_org_id).maybe_single().execute()
                pre_org = org_resp.data
            form_ctx = build_form_context("person", record=None, extra_context={"users": users_list})
            context = {
                "request": request,
                "user": current_user,
                "person": person_data,
                "person_org_links": [],
                "pre_org": pre_org,
                "duplicates": dupes,
                "asset_classes": get_reference_data("asset_class"),
                "users": users_list,
                "sections": form_ctx["sections"],
                "field_defs": form_ctx["field_defs"],
            }
            return templates.TemplateResponse("people/form.html", context)

    # Set default coverage owner to creator
    if not person_data.get("coverage_owner"):
        person_data["coverage_owner"] = str(current_user.id)

    # Insert
    person_data["created_by"] = str(current_user.id)
    sb = get_supabase()
    resp = sb.table("people").insert(person_data).execute()

    if resp.data:
        new_person = resp.data[0]
        person_id = new_person["id"]

        # Create primary org link
        _sync_org_links(str(person_id), form_data, current_user.id)

        # Audit log
        log_field_change("person", str(person_id), "_created", None, "record created", current_user.id)

        # DNC enforcement
        if new_person.get("do_not_contact"):
            _enforce_do_not_contact(str(person_id), current_user.id)

        return RedirectResponse(url=f"/people/{person_id}", status_code=303)

    raise HTTPException(status_code=500, detail="Failed to create person")


# ---------------------------------------------------------------------------
# EDIT FORM — GET /people/{person_id}/edit
# ---------------------------------------------------------------------------

@router.get("/{person_id}/edit", response_class=HTMLResponse)
async def edit_person_form(
    request: Request,
    person_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the edit person form."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()
    resp = (
        sb.table("people")
        .select("*")
        .eq("id", str(person_id))
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    person = resp.data
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    # Org links
    org_links_resp = (
        sb.table("person_organization_links")
        .select("id, link_type, job_title_at_org, organization_id, organization:organizations(id, company_name)")
        .eq("person_id", str(person_id))
        .execute()
    )
    org_links = org_links_resp.data or []

    # Pre-fill primary org
    pre_org = None
    for link in org_links:
        if link["link_type"] == "primary" and link.get("organization"):
            pre_org = link["organization"]
            break

    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
    users_list = users_resp.data or []

    form_ctx = build_form_context("person", record=person, extra_context={"users": users_list})

    context = {
        "request": request,
        "user": current_user,
        "person": person,
        "person_org_links": org_links,
        "pre_org": pre_org,
        "asset_classes": get_reference_data("asset_class"),
        "users": users_list,
        "sections": form_ctx["sections"],
        "field_defs": form_ctx["field_defs"],
    }
    return templates.TemplateResponse("people/form.html", context)


# ---------------------------------------------------------------------------
# UPDATE — POST /people/{person_id}
# ---------------------------------------------------------------------------

@router.post("/{person_id}", response_class=HTMLResponse)
async def update_person(
    request: Request,
    person_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an existing person."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()

    old_resp = (
        sb.table("people")
        .select("*")
        .eq("id", str(person_id))
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    old_person = old_resp.data
    if not old_person:
        raise HTTPException(status_code=404, detail="Person not found")

    form = await request.form()
    form_data = dict(form)

    # Dynamic form parsing
    field_defs = get_field_definitions("person", active_only=True)
    field_defs = enrich_field_definitions(field_defs)
    person_data = parse_form_data("person", form, field_defs)

    # Entity-specific extraction (multi-select fallback)
    if "asset_classes_of_interest" not in person_data or person_data["asset_classes_of_interest"] is None:
        asset_classes = form.getlist("asset_classes_of_interest") if hasattr(form, "getlist") else []
        person_data["asset_classes_of_interest"] = list(asset_classes) if asset_classes else None

    # Dynamic validation
    errors = validate_form_data("person", person_data, field_defs)

    # Entity-specific validation
    if not person_data.get("first_name"):
        if "First Name is required." not in errors:
            errors.append("First Name is required.")
    if not person_data.get("last_name"):
        if "Last Name is required." not in errors:
            errors.append("Last Name is required.")

    if errors:
        users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
        users_list = users_resp.data or []
        org_links_resp = (
            sb.table("person_organization_links")
            .select("id, link_type, job_title_at_org, organization_id, organization:organizations(id, company_name)")
            .eq("person_id", str(person_id))
            .execute()
        )
        form_ctx = build_form_context("person", record={**old_person, **person_data}, extra_context={"users": users_list})
        context = {
            "request": request,
            "user": current_user,
            "person": {**old_person, **person_data},
            "person_org_links": org_links_resp.data or [],
            "pre_org": None,
            "errors": errors,
            "asset_classes": get_reference_data("asset_class"),
            "users": users_list,
            "sections": form_ctx["sections"],
            "field_defs": form_ctx["field_defs"],
        }
        return templates.TemplateResponse("people/form.html", context)

    # Audit log every changed field
    audit_changes("person", str(person_id), old_person, person_data, current_user.id)

    # Update
    sb.table("people").update(person_data).eq("id", str(person_id)).execute()

    # Sync org links
    _sync_org_links(str(person_id), form_data, current_user.id)

    # DNC enforcement: if DNC was just toggled ON
    was_dnc = old_person.get("do_not_contact", False)
    is_dnc = person_data.get("do_not_contact", False)
    if is_dnc and not was_dnc:
        _enforce_do_not_contact(str(person_id), current_user.id)

    return RedirectResponse(url=f"/people/{person_id}", status_code=303)


# ---------------------------------------------------------------------------
# ARCHIVE (soft delete) — POST /people/{person_id}/archive
# ---------------------------------------------------------------------------

@router.post("/{person_id}/archive", response_class=HTMLResponse)
async def archive_person(
    request: Request,
    person_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-delete a person."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    sb.table("people").update({"is_deleted": True}).eq("id", str(person_id)).execute()
    log_field_change("person", str(person_id), "is_deleted", False, True, current_user.id)

    if request.headers.get("HX-Request"):
        return HTMLResponse('<p class="text-sm text-green-600">Person archived.</p>')
    return RedirectResponse(url="/people", status_code=303)

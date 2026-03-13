"""Organizations router — full CRUD, search, duplicate detection, audit logging."""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from dependencies import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/organizations", tags=["organizations"])
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_reference_data(category: str) -> list[dict]:
    """Fetch active reference data for a dropdown category, ordered by display_order."""
    sb = get_supabase()
    resp = (
        sb.table("reference_data")
        .select("value, label")
        .eq("category", category)
        .eq("is_active", True)
        .order("display_order")
        .execute()
    )
    return resp.data or []


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
        # Normalise for comparison
        if str(old_val) != str(new_val) and not (old_val is None and new_val is None):
            _log_field_change("organization", record_id, field, old_val, new_val, changed_by)


def _check_duplicates(company_name: str, website: Optional[str] = None, exclude_id: Optional[str] = None) -> list[dict]:
    """Return potential duplicate organisations based on name similarity or website match."""
    sb = get_supabase()
    duplicates = []

    # Fuzzy name match using pg_trgm (similarity > 0.4 via trigram index)
    name_resp = sb.rpc("check_org_name_similarity", {
        "search_name": company_name,
        "similarity_threshold": 0.4,
    }).execute()
    if name_resp.data:
        duplicates.extend(name_resp.data)

    # Website domain match (if provided)
    if website:
        domain = website.lower().replace("https://", "").replace("http://", "").rstrip("/")
        web_resp = (
            sb.table("organizations")
            .select("id, company_name, website, organization_type, relationship_type")
            .eq("is_archived", False)
            .ilike("website", f"%{domain}%")
            .execute()
        )
        if web_resp.data:
            existing_ids = {d["id"] for d in duplicates}
            for row in web_resp.data:
                if row["id"] not in existing_ids:
                    duplicates.append(row)

    # Exclude self when editing
    if exclude_id:
        duplicates = [d for d in duplicates if str(d["id"]) != exclude_id]

    return duplicates


def _build_org_data_from_form(form: dict) -> dict:
    """Extract organization fields from form data dict, handling type conversion."""
    data = {}

    # Text fields
    text_fields = [
        "company_name", "short_name", "relationship_type", "organization_type",
        "team_distribution_email", "website", "country", "city",
        "state_province", "street_address", "postal_code",
        "aum_source", "target_allocation_source",
        "backstop_company_id", "ostrako_id",
    ]
    for f in text_fields:
        val = form.get(f, "").strip()
        data[f] = val if val else None

    # Required text fields (keep empty string as None but they'll be validated)
    data["company_name"] = form.get("company_name", "").strip()
    data["relationship_type"] = form.get("relationship_type", "").strip()
    data["organization_type"] = form.get("organization_type", "").strip()

    # Numeric fields
    numeric_fields = [
        "aum_mn", "overall_aum_mn",
        "hf_target_allocation_pct", "pe_target_allocation_pct",
        "pc_target_allocation_pct", "re_target_allocation_pct",
        "ra_target_allocation_pct",
    ]
    for f in numeric_fields:
        val = form.get(f, "").strip()
        data[f] = float(val) if val else None

    # Boolean fields (checkboxes send value only when checked)
    data["rfp_hold"] = form.get("rfp_hold") == "on"
    data["client_discloses_info"] = form.get("client_discloses_info") == "on"

    # Date fields
    date_fields = ["questionnaire_date", "aum_as_of_date"]
    for f in date_fields:
        val = form.get(f, "").strip()
        data[f] = val if val else None

    return data


# ---------------------------------------------------------------------------
# LIST — GET /organizations
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def list_organizations(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=10, le=100),
    search: str = Query("", alias="q"),
    relationship_type: str = Query("", alias="relationship"),
    organization_type: str = Query("", alias="type"),
    country: str = Query("", alias="country"),
    sort_by: str = Query("company_name"),
    sort_dir: str = Query("asc"),
):
    """List organizations with filtering, search, sorting, and pagination."""
    sb = get_supabase()
    query = (
        sb.table("organizations")
        .select("id, company_name, short_name, relationship_type, organization_type, country, city, aum_mn, rfp_hold, website, created_at", count="exact")
        .eq("is_archived", False)
    )

    # Filters
    if search:
        query = query.ilike("company_name", f"%{search}%")
    if relationship_type:
        query = query.eq("relationship_type", relationship_type)
    if organization_type:
        query = query.eq("organization_type", organization_type)
    if country:
        query = query.eq("country", country)

    # Sorting
    valid_sort_cols = ["company_name", "relationship_type", "organization_type", "country", "aum_mn", "created_at"]
    if sort_by not in valid_sort_cols:
        sort_by = "company_name"
    desc = sort_dir.lower() == "desc"
    query = query.order(sort_by, desc=desc)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    resp = query.execute()
    organizations = resp.data or []
    total_count = resp.count or 0
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    # Reference data for filter dropdowns
    relationship_types = _get_reference_data("relationship_type")
    organization_types = _get_reference_data("organization_type")
    countries = _get_reference_data("country")

    context = {
        "request": request,
        "user": current_user,
        "organizations": organizations,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "search": search,
        "relationship_type": relationship_type,
        "organization_type": organization_type,
        "country": country,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "relationship_types": relationship_types,
        "organization_types": organization_types,
        "countries": countries,
        "view_mode": "all_organizations",
    }

    # HTMX partial vs full page (hx-boost navigations get the full page)
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("organizations/_list_table.html", context)
    return templates.TemplateResponse("organizations/list.html", context)


# ---------------------------------------------------------------------------
# MY ORGANIZATIONS — GET /organizations/my-organizations
# ---------------------------------------------------------------------------

@router.get("/my-organizations", response_class=HTMLResponse)
async def my_organizations(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=10, le=100),
    search: str = Query("", alias="q"),
    relationship_type: str = Query("", alias="relationship"),
    organization_type: str = Query("", alias="type"),
    country: str = Query("", alias="country"),
    sort_by: str = Query("company_name"),
    sort_dir: str = Query("asc"),
):
    """List organizations where the current user is a coverage owner (via people or leads)."""
    sb = get_supabase()

    # Find orgs where user is coverage_owner on linked people
    covered_people = (
        sb.table("people")
        .select("id")
        .eq("coverage_owner", str(current_user.id))
        .eq("is_archived", False)
        .execute()
    )
    person_ids = [str(p["id"]) for p in (covered_people.data or [])]
    my_org_ids = set()
    if person_ids:
        pol_resp = (
            sb.table("person_organization_links")
            .select("organization_id")
            .in_("person_id", person_ids)
            .execute()
        )
        my_org_ids |= {str(r["organization_id"]) for r in (pol_resp.data or [])}

    # Find orgs where user is aksia_owner on leads
    owned_leads = (
        sb.table("leads")
        .select("organization_id")
        .eq("aksia_owner_id", str(current_user.id))
        .eq("is_archived", False)
        .execute()
    )
    my_org_ids |= {str(l["organization_id"]) for l in (owned_leads.data or []) if l.get("organization_id")}

    # If no matching orgs, return empty results
    organizations = []
    total_count = 0
    total_pages = 1

    if my_org_ids:
        query = (
            sb.table("organizations")
            .select("id, company_name, short_name, relationship_type, organization_type, country, city, aum_mn, rfp_hold, website, created_at", count="exact")
            .eq("is_archived", False)
            .in_("id", list(my_org_ids))
        )

        # Filters
        if search:
            query = query.ilike("company_name", f"%{search}%")
        if relationship_type:
            query = query.eq("relationship_type", relationship_type)
        if organization_type:
            query = query.eq("organization_type", organization_type)
        if country:
            query = query.eq("country", country)

        # Sorting
        valid_sort_cols = ["company_name", "relationship_type", "organization_type", "country", "aum_mn", "created_at"]
        if sort_by not in valid_sort_cols:
            sort_by = "company_name"
        desc = sort_dir.lower() == "desc"
        query = query.order(sort_by, desc=desc)

        # Pagination
        offset = (page - 1) * page_size
        query = query.range(offset, offset + page_size - 1)

        resp = query.execute()
        organizations = resp.data or []
        total_count = resp.count or 0
        total_pages = max(1, (total_count + page_size - 1) // page_size)

    # Reference data for filter dropdowns
    relationship_types = _get_reference_data("relationship_type")
    organization_types = _get_reference_data("organization_type")
    countries = _get_reference_data("country")

    context = {
        "request": request,
        "user": current_user,
        "organizations": organizations,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "search": search,
        "relationship_type": relationship_type,
        "organization_type": organization_type,
        "country": country,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "relationship_types": relationship_types,
        "organization_types": organization_types,
        "countries": countries,
        "view_mode": "my_organizations",
    }

    # HTMX partial vs full page
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("organizations/_list_table.html", context)
    return templates.TemplateResponse("organizations/list.html", context)


# ---------------------------------------------------------------------------
# CREATE FORM — GET /organizations/new  (must be before /{org_id})
# ---------------------------------------------------------------------------

@router.get("/new", response_class=HTMLResponse)
async def new_organization_form(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the new organization form."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    context = {
        "request": request,
        "user": current_user,
        "org": None,
        "relationship_types": _get_reference_data("relationship_type"),
        "organization_types": _get_reference_data("organization_type"),
        "countries": _get_reference_data("country"),
    }
    return templates.TemplateResponse("organizations/form.html", context)


# ---------------------------------------------------------------------------
# DUPLICATE CHECK (HTMX) — GET /organizations/check-duplicates  (must be before /{org_id})
# ---------------------------------------------------------------------------

@router.get("/check-duplicates", response_class=HTMLResponse)
async def check_duplicates(
    request: Request,
    name: str = Query(""),
    website: str = Query(""),
    exclude_id: str = Query(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX endpoint: return duplicate warning HTML fragment."""
    if not name or len(name) < 3:
        return HTMLResponse("")

    dupes = _check_duplicates(name, website or None, exclude_id or None)
    if not dupes:
        return HTMLResponse("")

    context = {
        "request": request,
        "duplicates": dupes,
    }
    return templates.TemplateResponse("organizations/_duplicate_warning.html", context)


# ---------------------------------------------------------------------------
# DETAIL — GET /organizations/{org_id}
# ---------------------------------------------------------------------------

@router.get("/{org_id}", response_class=HTMLResponse)
async def get_organization(
    request: Request,
    org_id: UUID,
    tab: str = Query("people"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Organization detail page with tabbed linked records."""
    sb = get_supabase()

    # Fetch the organization
    resp = (
        sb.table("organizations")
        .select("*")
        .eq("id", str(org_id))
        .eq("is_archived", False)
        .maybe_single()
        .execute()
    )
    org = resp.data
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Linked people
    people_resp = (
        sb.table("person_organization_links")
        .select("link_type, job_title_at_org, person:people(id, first_name, last_name, email, job_title, coverage_owner, do_not_contact)")
        .eq("organization_id", str(org_id))
        .execute()
    )
    people = people_resp.data or []

    # Linked activities (most recent first, limit 50)
    activities_resp = (
        sb.table("activity_organization_links")
        .select("activity:activities(id, title, effective_date, activity_type, subtype, author_id, details, created_at)")
        .eq("organization_id", str(org_id))
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    activities = activities_resp.data or []

    # Linked leads
    leads_resp = (
        sb.table("leads")
        .select("id, start_date, end_date, rating, service_type, asset_classes, relationship, aksia_owner_id, expected_revenue, expected_yr1_flar")
        .eq("organization_id", str(org_id))
        .eq("is_archived", False)
        .order("created_at", desc=True)
        .execute()
    )
    leads = leads_resp.data or []

    # Linked contracts
    contracts_resp = (
        sb.table("contracts")
        .select("id, start_date, service_type, asset_classes, actual_revenue, client_coverage")
        .eq("organization_id", str(org_id))
        .eq("is_archived", False)
        .execute()
    )
    contracts = contracts_resp.data or []

    # Linked fund prospects
    fp_resp = (
        sb.table("fund_prospects")
        .select("id, fund_id, share_class, stage, aksia_owner_id, target_allocation_mn, probability_pct")
        .eq("organization_id", str(org_id))
        .eq("is_archived", False)
        .execute()
    )
    fund_prospects = fp_resp.data or []

    # Enrich fund prospects with ticker
    if fund_prospects:
        funds_resp = sb.table("funds").select("id, ticker").execute()
        funds_map = {f["id"]: f["ticker"] for f in (funds_resp.data or [])}
        for fp in fund_prospects:
            fp["fund_ticker"] = funds_map.get(fp.get("fund_id"), "?")

    # Fee arrangements
    fee_resp = (
        sb.table("fee_arrangements")
        .select("id, arrangement_name, annual_value, frequency, status, start_date, end_date")
        .eq("organization_id", str(org_id))
        .eq("is_archived", False)
        .execute()
    )
    fee_arrangements = fee_resp.data or []

    # Coverage rollup — collect unique coverage owners from people and leads
    coverage_owners = set()
    for p in people:
        person_data = p.get("person") or p
        if person_data.get("coverage_owner"):
            coverage_owners.add(person_data["coverage_owner"])
    for lead in leads:
        if lead.get("aksia_owner_id"):
            coverage_owners.add(lead["aksia_owner_id"])

    # Resolve coverage owner names
    coverage_names = []
    if coverage_owners:
        users_resp = (
            sb.table("users")
            .select("id, display_name")
            .in_("id", [str(uid) for uid in coverage_owners])
            .execute()
        )
        coverage_names = users_resp.data or []

    # Last contact date — most recent activity
    last_contact_date = None
    if activities:
        activity_data = activities[0].get("activity") or activities[0]
        last_contact_date = activity_data.get("effective_date")

    # Relationship type history from audit log
    history_resp = (
        sb.table("audit_log")
        .select("old_value, new_value, changed_by, changed_at")
        .eq("record_type", "organization")
        .eq("record_id", str(org_id))
        .eq("field_name", "relationship_type")
        .order("changed_at", desc=True)
        .execute()
    )
    relationship_history = history_resp.data or []

    # Separate former employees from current people
    former_employees = [p for p in people if p.get("link_type") == "former"]
    current_people = [p for p in people if p.get("link_type") != "former"]

    context = {
        "request": request,
        "user": current_user,
        "org": org,
        "people": current_people,
        "former_employees": former_employees,
        "activities": activities,
        "leads": leads,
        "contracts": contracts,
        "fund_prospects": fund_prospects,
        "fee_arrangements": fee_arrangements,
        "coverage_names": coverage_names,
        "last_contact_date": last_contact_date,
        "relationship_history": relationship_history,
        "active_tab": tab,
    }

    # Only return tab partial for explicit HTMX tab clicks, not hx-boost page navigations
    if request.headers.get("HX-Request") and tab:
        return templates.TemplateResponse(f"organizations/_tab_{tab}.html", context)
    return templates.TemplateResponse("organizations/detail.html", context)


# ---------------------------------------------------------------------------
# CREATE — POST /organizations
# ---------------------------------------------------------------------------

@router.post("/", response_class=HTMLResponse)
async def create_organization(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new organization."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    form = await request.form()
    form_data = dict(form)
    org_data = _build_org_data_from_form(form_data)

    # Validation
    errors = []
    if not org_data.get("company_name"):
        errors.append("Company Name is required.")
    if not org_data.get("relationship_type"):
        errors.append("Relationship Type is required.")
    if not org_data.get("organization_type"):
        errors.append("Organization Type is required.")

    # RFP Hold — only rfp_team and admin can set it
    if org_data.get("rfp_hold") and current_user.role not in ("admin", "rfp_team"):
        org_data["rfp_hold"] = False

    if errors:
        context = {
            "request": request,
            "user": current_user,
            "org": org_data,
            "errors": errors,
            "relationship_types": _get_reference_data("relationship_type"),
            "organization_types": _get_reference_data("organization_type"),
            "countries": _get_reference_data("country"),
        }
        return templates.TemplateResponse("organizations/form.html", context)

    # Check for duplicates (unless user confirmed)
    if form_data.get("confirm_duplicate") != "yes":
        dupes = _check_duplicates(org_data["company_name"], org_data.get("website"))
        if dupes:
            context = {
                "request": request,
                "user": current_user,
                "org": org_data,
                "duplicates": dupes,
                "relationship_types": _get_reference_data("relationship_type"),
                "organization_types": _get_reference_data("organization_type"),
                "countries": _get_reference_data("country"),
            }
            return templates.TemplateResponse("organizations/form.html", context)

    # Insert
    org_data["created_by"] = str(current_user.id)
    sb = get_supabase()
    resp = sb.table("organizations").insert(org_data).execute()

    if resp.data:
        new_org = resp.data[0]
        # Audit log — record creation
        _log_field_change("organization", new_org["id"], "_created", None, "record created", current_user.id)
        return RedirectResponse(url=f"/organizations/{new_org['id']}", status_code=303)

    raise HTTPException(status_code=500, detail="Failed to create organization")


# ---------------------------------------------------------------------------
# EDIT FORM — GET /organizations/{org_id}/edit
# ---------------------------------------------------------------------------

@router.get("/{org_id}/edit", response_class=HTMLResponse)
async def edit_organization_form(
    request: Request,
    org_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the edit organization form."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()
    resp = (
        sb.table("organizations")
        .select("*")
        .eq("id", str(org_id))
        .eq("is_archived", False)
        .maybe_single()
        .execute()
    )
    org = resp.data
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    context = {
        "request": request,
        "user": current_user,
        "org": org,
        "relationship_types": _get_reference_data("relationship_type"),
        "organization_types": _get_reference_data("organization_type"),
        "countries": _get_reference_data("country"),
    }
    return templates.TemplateResponse("organizations/form.html", context)


# ---------------------------------------------------------------------------
# UPDATE — POST /organizations/{org_id}
# ---------------------------------------------------------------------------

@router.post("/{org_id}", response_class=HTMLResponse)
async def update_organization(
    request: Request,
    org_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an existing organization."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()

    # Fetch current record for audit comparison
    old_resp = (
        sb.table("organizations")
        .select("*")
        .eq("id", str(org_id))
        .eq("is_archived", False)
        .maybe_single()
        .execute()
    )
    old_org = old_resp.data
    if not old_org:
        raise HTTPException(status_code=404, detail="Organization not found")

    form = await request.form()
    form_data = dict(form)
    org_data = _build_org_data_from_form(form_data)

    # RFP Hold — only rfp_team and admin can change it
    if current_user.role not in ("admin", "rfp_team"):
        org_data["rfp_hold"] = old_org["rfp_hold"]

    # Validation
    errors = []
    if not org_data.get("company_name"):
        errors.append("Company Name is required.")
    if not org_data.get("relationship_type"):
        errors.append("Relationship Type is required.")
    if not org_data.get("organization_type"):
        errors.append("Organization Type is required.")

    if errors:
        context = {
            "request": request,
            "user": current_user,
            "org": {**old_org, **org_data},
            "errors": errors,
            "relationship_types": _get_reference_data("relationship_type"),
            "organization_types": _get_reference_data("organization_type"),
            "countries": _get_reference_data("country"),
        }
        return templates.TemplateResponse("organizations/form.html", context)

    # Audit log every changed field
    _audit_changes(str(org_id), old_org, org_data, current_user.id)

    # Update
    sb.table("organizations").update(org_data).eq("id", str(org_id)).execute()

    return RedirectResponse(url=f"/organizations/{org_id}", status_code=303)


# ---------------------------------------------------------------------------
# ARCHIVE (soft delete) — POST /organizations/{org_id}/archive
# ---------------------------------------------------------------------------

@router.post("/{org_id}/archive", response_class=HTMLResponse)
async def archive_organization(
    request: Request,
    org_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-delete an organization."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    sb.table("organizations").update({"is_archived": True}).eq("id", str(org_id)).execute()
    _log_field_change("organization", str(org_id), "is_archived", False, True, current_user.id)

    if request.headers.get("HX-Request"):
        return HTMLResponse('<p class="text-sm text-green-600">Organization archived.</p>')
    return RedirectResponse(url="/organizations", status_code=303)



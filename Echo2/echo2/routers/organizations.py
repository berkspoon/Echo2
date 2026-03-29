"""Organizations router — full CRUD, search, duplicate detection, audit logging."""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from db.helpers import get_reference_data, log_field_change, audit_changes, batch_resolve_users
from db.field_service import get_field_definitions, enrich_field_definitions, save_custom_values
from services.form_service import build_form_context, parse_form_data, validate_form_data, get_users_for_lookup, split_core_eav
from dependencies import CurrentUser, get_current_user, require_role
from services.grid_service import build_grid_context

router = APIRouter(prefix="/organizations", tags=["organizations"])
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_duplicates(company_name: str, website: Optional[str] = None, exclude_id: Optional[str] = None, source_id: Optional[str] = None) -> list[dict]:
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
            .eq("is_deleted", False)
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

    # Filter out suppressed pairs
    if source_id:
        supp_resp = sb.table("duplicate_suppressions").select("record_id_a, record_id_b").eq("entity_type", "organization").or_(f"record_id_a.eq.{source_id},record_id_b.eq.{source_id}").execute()
        if supp_resp.data:
            suppressed_ids = set()
            for s in supp_resp.data:
                suppressed_ids.add(s["record_id_a"])
                suppressed_ids.add(s["record_id_b"])
            suppressed_ids.discard(source_id)
            duplicates = [d for d in duplicates if str(d["id"]) not in suppressed_ids]

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
):
    """List organizations with filtering, search, sorting, and pagination."""
    ctx = build_grid_context("organization", request, current_user, base_url="/organizations")

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("components/_grid.html", {"request": request, **ctx})

    # Extra context for the filter bar on list.html
    ctx.update({
        "user": current_user,
        "view_mode": "all_organizations",
        "total_count": ctx["pagination"]["total"],
        "search": ctx["filters"].get("q", ""),
        "relationship_type": ctx["filters"].get("relationship", ""),
        "organization_type": ctx["filters"].get("type", ""),
        "country": ctx["filters"].get("country", ""),
        "relationship_types": get_reference_data("relationship_type"),
        "organization_types": get_reference_data("organization_type"),
        "countries": get_reference_data("country"),
    })
    return templates.TemplateResponse("organizations/list.html", {"request": request, **ctx})


# ---------------------------------------------------------------------------
# MY ORGANIZATIONS — GET /organizations/my-organizations
# ---------------------------------------------------------------------------

@router.get("/my-organizations", response_class=HTMLResponse)
async def my_organizations(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List organizations where the current user is a coverage owner (via people or leads)."""
    sb = get_supabase()

    # Find orgs where user is coverage_owner on linked people
    covered_people = (
        sb.table("people")
        .select("id")
        .eq("coverage_owner", str(current_user.id))
        .eq("is_deleted", False)
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
        .eq("is_deleted", False)
        .execute()
    )
    my_org_ids |= {str(l["organization_id"]) for l in (owned_leads.data or []) if l.get("organization_id")}

    extra_filters = {"_org_ids": list(my_org_ids)} if my_org_ids else {"_org_ids": ["00000000-0000-0000-0000-000000000000"]}
    ctx = build_grid_context("organization", request, current_user, base_url="/organizations/my-organizations", extra_filters=extra_filters)

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("components/_grid.html", {"request": request, **ctx})

    ctx.update({
        "user": current_user,
        "view_mode": "my_organizations",
        "total_count": ctx["pagination"]["total"],
        "search": ctx["filters"].get("q", ""),
        "relationship_type": ctx["filters"].get("relationship", ""),
        "organization_type": ctx["filters"].get("type", ""),
        "country": ctx["filters"].get("country", ""),
        "relationship_types": get_reference_data("relationship_type"),
        "organization_types": get_reference_data("organization_type"),
        "countries": get_reference_data("country"),
    })
    return templates.TemplateResponse("organizations/list.html", {"request": request, **ctx})


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

    form_ctx = build_form_context("organization", record=None)

    context = {
        "request": request,
        "user": current_user,
        "org": None,
        "relationship_types": get_reference_data("relationship_type"),
        "organization_types": get_reference_data("organization_type"),
        "countries": get_reference_data("country"),
        "org_asset_classes": get_reference_data("org_asset_class"),
        "org_product_funds": get_reference_data("org_product_fund"),
        "record": form_ctx["record"],
        "sections": form_ctx["sections"],
        "field_defs": form_ctx["field_defs"],
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

    dupes = _check_duplicates(name, website or None, exclude_id or None, source_id=exclude_id or None)
    if not dupes:
        return HTMLResponse("")

    context = {
        "request": request,
        "duplicates": dupes,
        "source_id": exclude_id or None,
        "entity_type": "organization",
    }
    return templates.TemplateResponse("organizations/_duplicate_warning.html", context)


# ---------------------------------------------------------------------------
# SUPPRESS DUPLICATE — POST /organizations/{org_id}/suppress-duplicate
# ---------------------------------------------------------------------------

@router.post("/{org_id}/suppress-duplicate", response_class=HTMLResponse)
async def suppress_duplicate(
    request: Request,
    org_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Suppress a duplicate pair so it no longer shows as a warning."""
    form = await request.form()
    other_id = form.get("other_id", "")
    if not other_id:
        raise HTTPException(status_code=400, detail="Missing other_id")

    # Normalize: smaller UUID as record_id_a
    id_a, id_b = (min(org_id, other_id), max(org_id, other_id))

    sb = get_supabase()
    sb.table("duplicate_suppressions").upsert({
        "entity_type": "organization",
        "record_id_a": id_a,
        "record_id_b": id_b,
        "suppressed_by": str(current_user.id),
    }).execute()

    log_field_change("organization", org_id, "duplicate_suppressed", other_id, "suppressed", current_user.id)

    # Re-run duplicate check and return updated list
    org_resp = sb.table("organizations").select("company_name, website").eq("id", org_id).maybe_single().execute()
    if org_resp.data:
        dupes = _check_duplicates(org_resp.data["company_name"], org_resp.data.get("website"), exclude_id=org_id, source_id=org_id)
    else:
        dupes = []

    context = {
        "request": request,
        "duplicates": dupes,
        "source_id": org_id,
        "entity_type": "organization",
    }
    return templates.TemplateResponse("organizations/_duplicate_warning.html", context)


# ---------------------------------------------------------------------------
# LEADS PANEL (HTMX) — GET /organizations/{org_id}/leads-panel
# ---------------------------------------------------------------------------

# Inactive lead stages — same as grid_service._enrich_organizations
_INACTIVE_LEAD_STAGES = (
    "won", "lost_dropped_out", "lost_selected_other",
    "lost_nobody_hired", "closed", "declined",
)

@router.get("/{org_id}/leads-panel", response_class=HTMLResponse)
async def org_leads_panel(
    request: Request,
    org_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX partial: inline mini-table of active leads for an organization."""
    sb = get_supabase()

    leads_resp = (
        sb.table("leads")
        .select("id, summary, rating, service_type, aksia_owner_id, expected_revenue, lead_type")
        .eq("organization_id", str(org_id))
        .eq("is_deleted", False)
        .execute()
    )
    all_leads = leads_resp.data or []

    # Filter out inactive stages in Python
    active_leads = [
        l for l in all_leads
        if l.get("rating") not in _INACTIVE_LEAD_STAGES
    ]

    # Batch resolve owner names
    owner_ids = list({str(l["aksia_owner_id"]) for l in active_leads if l.get("aksia_owner_id")})
    user_map = batch_resolve_users(owner_ids) if owner_ids else {}

    # Batch resolve stage labels from reference_data
    stage_labels = {}
    for rd in get_reference_data("lead_stage"):
        stage_labels[rd["value"]] = rd["label"]

    # Attach resolved names to each lead
    for lead in active_leads:
        lead["owner_name"] = user_map.get(str(lead.get("aksia_owner_id", "")), "")
        lead["stage_label"] = stage_labels.get(lead.get("rating", ""), (lead.get("rating") or "").replace("_", " ").title())

    context = {
        "request": request,
        "org_id": str(org_id),
        "leads": active_leads,
    }
    return templates.TemplateResponse("organizations/_org_leads_panel.html", context)


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
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    org = resp.data
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Linked people
    people_resp = (
        sb.table("person_organization_links")
        .select("link_type, job_title_at_org, start_date, end_date, person:people(id, first_name, last_name, email, job_title, coverage_owner, do_not_contact)")
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

    # Enrich activities with linked leads (batch)
    act_ids = []
    for item in activities:
        act = item.get("activity") or item
        if act.get("id"):
            act_ids.append(str(act["id"]))
    if act_ids:
        from db.helpers import get_reference_data as _get_ref
        all_lead_links = (
            sb.table("activity_lead_links")
            .select("activity_id, lead_id")
            .in_("activity_id", act_ids)
            .execute()
        ).data or []
        lead_ids_set = list({r["lead_id"] for r in all_lead_links})
        leads_map = {}
        if lead_ids_set:
            leads_detail = (
                sb.table("leads")
                .select("id, rating, lead_type")
                .in_("id", lead_ids_set)
                .eq("is_deleted", False)
                .execute()
            )
            stage_labels = {r["value"]: r["label"] for r in _get_ref("lead_stage")}
            leads_map = {str(l["id"]): {**l, "stage_label": stage_labels.get(l.get("rating"), (l.get("rating") or "").replace("_", " ").title())} for l in (leads_detail.data or [])}
        act_lead_map = {}
        for r in all_lead_links:
            act_lead_map.setdefault(str(r["activity_id"]), []).append(leads_map.get(str(r["lead_id"])))
        for item in activities:
            act = item.get("activity") or item
            act["_linked_leads"] = [l for l in act_lead_map.get(str(act.get("id")), []) if l]

    # Linked leads
    leads_resp = (
        sb.table("leads")
        .select("id, title, start_date, end_date, rating, service_type, asset_classes, relationship, aksia_owner_id, expected_revenue, expected_yr1_flar")
        .eq("organization_id", str(org_id))
        .eq("is_deleted", False)
        .order("start_date", desc=True, nullsfirst=False)
        .execute()
    )
    leads = leads_resp.data or []

    # Resolve lead owner names from lead_owners junction table
    if leads:
        lead_ids = [str(l["id"]) for l in leads]
        lo_resp = sb.table("lead_owners").select("lead_id, user_id, is_primary").in_("lead_id", lead_ids).execute()
        owner_user_ids = list({str(r["user_id"]) for r in (lo_resp.data or [])})
        if owner_user_ids:
            users_resp = sb.table("users").select("id, display_name").in_("id", owner_user_ids).execute()
            user_names = {str(u["id"]): u["display_name"] for u in (users_resp.data or [])}
        else:
            user_names = {}
        lead_owner_map = {}
        for r in (lo_resp.data or []):
            lid = str(r["lead_id"])
            if r.get("is_primary") or lid not in lead_owner_map:
                lead_owner_map[lid] = user_names.get(str(r["user_id"]), "")
        for lead in leads:
            lead["_owner_name"] = lead_owner_map.get(str(lead["id"]), "")

    # Linked contracts
    contracts_resp = (
        sb.table("contracts")
        .select("id, start_date, service_type, asset_classes, actual_revenue, client_coverage")
        .eq("organization_id", str(org_id))
        .eq("is_deleted", False)
        .execute()
    )
    contracts = contracts_resp.data or []

    # Linked fundraise/product leads (replaces fund_prospects)
    fundraise_resp = (
        sb.table("leads")
        .select("id, fund_id, share_class, rating, aksia_owner_id, target_allocation_mn, probability_pct, lead_type")
        .eq("organization_id", str(org_id))
        .eq("is_deleted", False)
        .in_("lead_type", ["fundraise", "product"])
        .execute()
    )
    fundraise_leads = fundraise_resp.data or []

    # Enrich fundraise leads with fund ticker
    if fundraise_leads:
        funds_resp = sb.table("funds").select("id, ticker").execute()
        funds_map = {f["id"]: f["ticker"] for f in (funds_resp.data or [])}
        for fl in fundraise_leads:
            fl["fund_ticker"] = funds_map.get(fl.get("fund_id"), "?")
            fl["stage"] = fl.get("rating", "target_identified")

    # Fee arrangements
    fee_resp = (
        sb.table("fee_arrangements")
        .select("id, arrangement_name, annual_value, frequency, status, start_date, end_date")
        .eq("organization_id", str(org_id))
        .eq("is_deleted", False)
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
        "fundraise_leads": fundraise_leads,
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

    # Dynamic form parsing via field_defs
    field_defs = get_field_definitions("organization", active_only=True)
    field_defs = enrich_field_definitions(field_defs)
    org_data = parse_form_data("organization", form, field_defs)

    # Dynamic validation from field_defs
    errors = validate_form_data("organization", org_data, field_defs)

    # Entity-specific validation (keep existing logic)
    if not org_data.get("company_name") and "Company Name is required." not in errors:
        errors.append("Company Name is required.")
    if not org_data.get("relationship_type") and "Relationship Type is required." not in errors:
        errors.append("Relationship Type is required.")
    if not org_data.get("organization_type") and "Organization Type is required." not in errors:
        errors.append("Organization Type is required.")

    # Parse asset_class and product_funds (multi-select checkboxes)
    asset_class_vals = form.getlist("asset_class")
    org_data["asset_class"] = asset_class_vals if asset_class_vals else None
    product_fund_vals = form.getlist("product_funds")
    org_data["product_funds"] = product_fund_vals if product_fund_vals else None

    # Client-specific validation
    if org_data.get("relationship_type") == "client":
        if not asset_class_vals:
            errors.append("Asset Class is required for client organizations.")
        if asset_class_vals and "product" in asset_class_vals and not product_fund_vals:
            errors.append("Product Funds is required when 'Product' is selected as an asset class.")

    # RFP Hold — only rfp_team and admin can set it
    if org_data.get("rfp_hold") and current_user.role not in ("admin", "rfp_team"):
        org_data["rfp_hold"] = False

    if errors:
        form_ctx = build_form_context("organization", record=None)
        context = {
            "request": request,
            "user": current_user,
            "org": org_data,
            "errors": errors,
            "relationship_types": get_reference_data("relationship_type"),
            "organization_types": get_reference_data("organization_type"),
            "countries": get_reference_data("country"),
            "org_asset_classes": get_reference_data("org_asset_class"),
            "org_product_funds": get_reference_data("org_product_fund"),
            "record": form_ctx["record"],
            "sections": form_ctx["sections"],
            "field_defs": form_ctx["field_defs"],
        }
        return templates.TemplateResponse("organizations/form.html", context)

    # Check for duplicates (unless user confirmed)
    if form_data.get("confirm_duplicate") != "yes":
        dupes = _check_duplicates(org_data["company_name"], org_data.get("website"))
        if dupes:
            form_ctx = build_form_context("organization", record=None)
            context = {
                "request": request,
                "user": current_user,
                "org": org_data,
                "duplicates": dupes,
                "relationship_types": get_reference_data("relationship_type"),
                "organization_types": get_reference_data("organization_type"),
                "countries": get_reference_data("country"),
                "org_asset_classes": get_reference_data("org_asset_class"),
                "org_product_funds": get_reference_data("org_product_fund"),
                "record": form_ctx["record"],
                "sections": form_ctx["sections"],
                "field_defs": form_ctx["field_defs"],
            }
            return templates.TemplateResponse("organizations/form.html", context)

    # Insert
    org_data["created_by"] = str(current_user.id)
    sb = get_supabase()
    core_data, eav_data = split_core_eav(org_data, field_defs)
    resp = sb.table("organizations").insert(core_data).execute()

    if resp.data:
        new_org = resp.data[0]
        # Save EAV custom field values
        if eav_data:
            save_custom_values("organization", str(new_org["id"]), eav_data, field_defs)
        # Audit log — record creation
        log_field_change("organization", new_org["id"], "_created", None, "record created", current_user.id)
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
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    org = resp.data
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    form_ctx = build_form_context("organization", record=org)

    context = {
        "request": request,
        "user": current_user,
        "org": org,
        "record": form_ctx["record"],
        "relationship_types": get_reference_data("relationship_type"),
        "organization_types": get_reference_data("organization_type"),
        "countries": get_reference_data("country"),
        "org_asset_classes": get_reference_data("org_asset_class"),
        "org_product_funds": get_reference_data("org_product_fund"),
        "sections": form_ctx["sections"],
        "field_defs": form_ctx["field_defs"],
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
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    old_org = old_resp.data
    if not old_org:
        raise HTTPException(status_code=404, detail="Organization not found")

    form = await request.form()
    form_data = dict(form)

    # Dynamic form parsing via field_defs
    field_defs = get_field_definitions("organization", active_only=True)
    field_defs = enrich_field_definitions(field_defs)
    org_data = parse_form_data("organization", form, field_defs)

    # RFP Hold — only rfp_team and admin can change it
    if current_user.role not in ("admin", "rfp_team"):
        org_data["rfp_hold"] = old_org["rfp_hold"]

    # Dynamic validation from field_defs
    errors = validate_form_data("organization", org_data, field_defs)

    # Entity-specific validation (keep existing logic)
    if not org_data.get("company_name") and "Company Name is required." not in errors:
        errors.append("Company Name is required.")
    if not org_data.get("relationship_type") and "Relationship Type is required." not in errors:
        errors.append("Relationship Type is required.")
    if not org_data.get("organization_type") and "Organization Type is required." not in errors:
        errors.append("Organization Type is required.")

    # Parse asset_class and product_funds (multi-select checkboxes)
    asset_class_vals = form.getlist("asset_class")
    org_data["asset_class"] = asset_class_vals if asset_class_vals else None
    product_fund_vals = form.getlist("product_funds")
    org_data["product_funds"] = product_fund_vals if product_fund_vals else None

    # Client-specific validation
    if org_data.get("relationship_type") == "client":
        if not asset_class_vals:
            errors.append("Asset Class is required for client organizations.")
        if asset_class_vals and "product" in asset_class_vals and not product_fund_vals:
            errors.append("Product Funds is required when 'Product' is selected as an asset class.")

    if errors:
        form_ctx = build_form_context("organization", record=old_org)
        context = {
            "request": request,
            "user": current_user,
            "org": {**old_org, **org_data},
            "errors": errors,
            "relationship_types": get_reference_data("relationship_type"),
            "organization_types": get_reference_data("organization_type"),
            "countries": get_reference_data("country"),
            "org_asset_classes": get_reference_data("org_asset_class"),
            "org_product_funds": get_reference_data("org_product_fund"),
            "record": form_ctx["record"],
            "sections": form_ctx["sections"],
            "field_defs": form_ctx["field_defs"],
        }
        return templates.TemplateResponse("organizations/form.html", context)

    # Audit log every changed field
    audit_changes("organization", str(org_id), old_org, org_data, current_user.id)

    # Update
    core_data, eav_data = split_core_eav(org_data, field_defs)
    sb.table("organizations").update(core_data).eq("id", str(org_id)).execute()
    if eav_data:
        save_custom_values("organization", str(org_id), eav_data, field_defs)

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
    sb.table("organizations").update({"is_deleted": True}).eq("id", str(org_id)).execute()
    log_field_change("organization", str(org_id), "is_deleted", False, True, current_user.id)

    if request.headers.get("HX-Request"):
        return HTMLResponse('<p class="text-sm text-green-600">Organization archived.</p>')
    return RedirectResponse(url="/organizations", status_code=303)


# ---------------------------------------------------------------------------
# MARK FORMER — POST /organizations/{org_id}/mark-former
# ---------------------------------------------------------------------------

@router.post("/{org_id}/mark-former", response_class=HTMLResponse)
async def mark_person_former(
    request: Request,
    org_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Mark a person as 'former' at this organization."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])
    sb = get_supabase()
    form = await request.form()
    person_id = (form.get("person_id") or "").strip()

    if not person_id:
        raise HTTPException(status_code=400, detail="No person specified.")

    effective_date = (form.get("effective_date") or "").strip()
    end_date = effective_date if effective_date else date.today().isoformat()

    # Update link_type to 'former' and set end_date
    sb.table("person_organization_links") \
        .update({"link_type": "former", "end_date": end_date}) \
        .eq("person_id", person_id) \
        .eq("organization_id", str(org_id)) \
        .execute()

    # Audit log
    log_field_change("person_organization_links", person_id, "link_type", "primary", "former", current_user.id)

    # Redirect to refresh the people tab
    return HTMLResponse(
        content="",
        headers={"HX-Redirect": f"/organizations/{org_id}?tab=people"}
    )



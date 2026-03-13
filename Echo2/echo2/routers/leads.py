"""Leads router — full CRUD, search, filters, pagination, audit logging,
stage-gated validation, Lead→Contract promotion, next-steps task generation."""

from datetime import date as date_type
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from dependencies import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/leads", tags=["leads"])
templates = Jinja2Templates(directory="templates")

# Stage hierarchy for gated field requirements
STAGE_ORDER = {
    "exploratory": 1,
    "radar": 2,
    "focus": 3,
    "verbal_mandate": 4,
    "won": 5,
    "lost_dropped_out": 5,
    "lost_selected_other": 5,
    "lost_nobody_hired": 5,
}
INACTIVE_STAGES = {"won", "lost_dropped_out", "lost_selected_other", "lost_nobody_hired"}
LOST_STAGES = {"lost_dropped_out", "lost_selected_other", "lost_nobody_hired"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_reference_data(category: str) -> list[dict]:
    """Fetch active reference data for a dropdown category."""
    sb = get_supabase()
    return (
        sb.table("reference_data")
        .select("value, label")
        .eq("category", category)
        .eq("is_active", True)
        .order("display_order")
        .execute()
        .data or []
    )


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
            _log_field_change("lead", record_id, field, old_val, new_val, changed_by)


def _build_lead_data_from_form(form: dict) -> dict:
    """Extract lead fields from form data."""
    data = {}

    # Organization (single FK)
    org_id = (form.get("organization_id") or "").strip()
    data["organization_id"] = org_id if org_id else None

    # Rating / stage
    data["rating"] = (form.get("rating") or "exploratory").strip()

    # Dates
    for date_field in ("start_date", "end_date", "expected_decision_date",
                       "rfp_expected_date", "next_steps_date"):
        val = (form.get(date_field) or "").strip()
        data[date_field] = val if val else None

    # Text fields
    for text_field in ("relationship", "source", "summary", "service_type",
                       "pricing_proposal", "pricing_proposal_details",
                       "expected_revenue_notes", "rfp_status", "risk_weight",
                       "next_steps", "potential_coverage",
                       "legacy_onboarding_holdings"):
        val = (form.get(text_field) or "").strip()
        data[text_field] = val if val else None

    # Aksia Owner (user lookup)
    owner = (form.get("aksia_owner_id") or "").strip()
    data["aksia_owner_id"] = owner if owner else None

    # Decimal fields
    for dec_field in ("expected_revenue", "expected_yr1_flar",
                      "expected_longterm_flar", "previous_flar"):
        val = (form.get(dec_field) or "").strip()
        if val:
            try:
                data[dec_field] = float(val)
            except ValueError:
                data[dec_field] = None
        else:
            data[dec_field] = None

    # Asset classes (multi-select)
    asset_classes = form.getlist("asset_classes") if hasattr(form, "getlist") else []
    data["asset_classes"] = list(asset_classes) if asset_classes else None

    # Boolean: legacy onboarding
    data["legacy_onboarding"] = form.get("legacy_onboarding") == "on"

    return data


def _validate_lead_fields(data: dict, rating: str) -> list[str]:
    """Validate fields based on current stage. Returns list of error strings."""
    errors = []
    stage = STAGE_ORDER.get(rating, 1)

    # Always required
    if not data.get("organization_id"):
        errors.append("Organization is required.")

    # Exploratory+ (stage >= 1)
    if stage >= 1:
        if not data.get("relationship"):
            errors.append("Relationship type is required.")
        if not data.get("aksia_owner_id"):
            errors.append("Aksia Owner is required.")

    # Radar+ (stage >= 2)
    if stage >= 2:
        if not data.get("service_type"):
            errors.append("Service Type is required at Radar stage and above.")
        if not data.get("asset_classes"):
            errors.append("At least one Asset Class is required at Radar stage and above.")
        if not data.get("source"):
            errors.append("Source is required at Radar stage and above.")

    # Focus+ (stage >= 3)
    if stage >= 3:
        if not data.get("pricing_proposal"):
            errors.append("Pricing Proposal is required at Focus stage and above.")
        if data.get("pricing_proposal") and data["pricing_proposal"] != "no_proposal":
            if not data.get("pricing_proposal_details"):
                errors.append("Pricing Proposal Details required when a proposal has been made.")
        if not data.get("expected_decision_date"):
            errors.append("Expected Decision Date is required at Focus stage and above.")
        if data.get("expected_revenue") is None:
            errors.append("Expected Revenue is required at Focus stage and above.")
        if data.get("expected_yr1_flar") is None:
            errors.append("Expected Yr 1 FLAR is required at Focus stage and above.")
        if data.get("expected_longterm_flar") is None:
            errors.append("Expected Long-term FLAR is required at Focus stage and above.")
        if not data.get("rfp_status"):
            errors.append("RFP Status is required at Focus stage and above.")
        if data.get("rfp_status") and data["rfp_status"] != "not_applicable":
            if not data.get("rfp_expected_date"):
                errors.append("RFP Expected Date is required when RFP Status is not N/A.")
        if not data.get("risk_weight"):
            errors.append("Risk Weight is required at Focus stage and above.")
        # Previous FLAR for extension/re-up
        if data.get("relationship") in ("contract_extension", "re_up"):
            if data.get("previous_flar") is None:
                errors.append("Previous FLAR is required for Extension/Re-Up relationships.")

    # Verbal Mandate+ (stage >= 4)
    if stage >= 4:
        if data.get("legacy_onboarding") is None:
            errors.append("Legacy Onboarding is required at Verbal Mandate stage.")
        if data.get("legacy_onboarding") and not data.get("legacy_onboarding_holdings"):
            errors.append("Legacy Onboarding Holdings required when Legacy Onboarding is Yes.")

    # Lost stages require end_date
    if rating in LOST_STAGES:
        if not data.get("end_date"):
            errors.append("End Date is required for inactive/lost leads.")

    return errors


def _promote_lead_to_contract(lead: dict, current_user_id: UUID) -> str:
    """Create a Contract record from a won lead. Returns the new contract ID."""
    sb = get_supabase()
    today = str(date_type.today())

    # Auto-set end_date on the lead
    sb.table("leads").update({"end_date": today}).eq("id", str(lead["id"])).execute()
    _log_field_change("lead", str(lead["id"]), "end_date", lead.get("end_date"), today, current_user_id)

    # Build contract data
    contract_data = {
        "organization_id": str(lead["organization_id"]),
        "originating_lead_id": str(lead["id"]),
        "start_date": today,
        "service_type": lead.get("service_type") or "",
        "asset_classes": lead.get("asset_classes") or [],
        "client_coverage": lead.get("potential_coverage"),
        "actual_revenue": lead.get("expected_revenue") or 0,
        "created_by": str(current_user_id),
    }

    resp = sb.table("contracts").insert(contract_data).execute()
    contract_id = resp.data[0]["id"] if resp.data else None

    # Audit log the promotion
    _log_field_change("lead", str(lead["id"]), "_promoted_to_contract", None, str(contract_id), current_user_id)
    if contract_id:
        _log_field_change("contract", str(contract_id), "_created", None, "auto-created from lead promotion", current_user_id)

    return str(contract_id) if contract_id else ""


def _create_next_steps_task(lead: dict, org_name: str, changed_by: UUID) -> None:
    """Auto-generate a Task when next_steps_date is set."""
    sb = get_supabase()
    sb.table("tasks").insert({
        "title": f"Lead next steps: {org_name}",
        "due_date": lead.get("next_steps_date"),
        "assigned_to": str(lead["aksia_owner_id"]) if lead.get("aksia_owner_id") else str(changed_by),
        "status": "open",
        "notes": lead.get("next_steps") or "",
        "source": "lead_next_steps",
        "linked_record_type": "lead",
        "linked_record_id": str(lead["id"]),
        "created_by": str(changed_by),
    }).execute()


def _get_org_name(org_id: str) -> str:
    """Look up an org name by ID."""
    sb = get_supabase()
    resp = sb.table("organizations").select("company_name").eq("id", org_id).single().execute()
    return resp.data["company_name"] if resp.data else "Unknown"


def _get_user_name(user_id: str) -> str:
    """Look up a user display_name by ID."""
    sb = get_supabase()
    resp = sb.table("users").select("display_name").eq("id", user_id).single().execute()
    return resp.data["display_name"] if resp.data else "Unknown"


def _load_form_context(sb, current_user, lead=None, pre_org=None, errors=None):
    """Load all reference data and users needed for the lead form."""
    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
    return {
        "lead_stages": _get_reference_data("lead_stage"),
        "relationship_types": _get_reference_data("lead_relationship_type"),
        "service_types": _get_reference_data("service_type"),
        "asset_classes": _get_reference_data("asset_class"),
        "pricing_proposals": _get_reference_data("pricing_proposal"),
        "rfp_statuses": _get_reference_data("rfp_status"),
        "risk_weights": _get_reference_data("risk_weight"),
        "users": users_resp.data or [],
        "lead": lead,
        "pre_org": pre_org,
        "errors": errors or [],
        "user": current_user,
    }


# ---------------------------------------------------------------------------
# ORG SEARCH (HTMX autocomplete) — GET /leads/search-orgs
# ---------------------------------------------------------------------------

@router.get("/search-orgs", response_class=HTMLResponse)
async def search_orgs(
    request: Request,
    q: str = Query(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX endpoint: return org search results for single-select autocomplete."""
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
            f"onclick=\"selectOrg('{org['id']}', '{safe_name}')\">"
            f'<div class="font-medium text-gray-900">{org["company_name"]}</div>'
            f'<div class="text-xs text-gray-400">{(org.get("organization_type") or "").replace("_", " ").title()}'
            f'{" — " + location if location else ""}</div>'
            f'</button>'
        )
    return HTMLResponse("\n".join(html_parts))


# ---------------------------------------------------------------------------
# LIST — GET /leads
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def list_leads(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=10, le=100),
    search: str = Query("", alias="q"),
    rating: str = Query("", alias="stage"),
    owner_id: str = Query("", alias="owner"),
    service_type: str = Query("", alias="service"),
    relationship: str = Query("", alias="rel"),
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    sort_by: str = Query("start_date"),
    sort_dir: str = Query("desc"),
):
    """List leads with filtering, search, sorting, and pagination."""
    sb = get_supabase()

    # If searching by org name, get matching org IDs first
    org_id_filter = None
    if search:
        org_search_resp = (
            sb.table("organizations")
            .select("id")
            .eq("is_archived", False)
            .ilike("company_name", f"%{search}%")
            .limit(100)
            .execute()
        )
        org_id_filter = [o["id"] for o in (org_search_resp.data or [])]

    query = (
        sb.table("leads")
        .select("id, organization_id, start_date, end_date, rating, service_type, "
                "relationship, aksia_owner_id, summary, expected_revenue, "
                "expected_yr1_flar, created_at", count="exact")
        .eq("is_archived", False)
    )

    # Search: match org name (via IDs) or summary
    if search:
        if org_id_filter:
            query = query.or_(
                f"summary.ilike.%{search}%,organization_id.in.({','.join(org_id_filter)})"
            )
        else:
            query = query.ilike("summary", f"%{search}%")

    # Filters
    if rating:
        query = query.eq("rating", rating)
    if owner_id:
        query = query.eq("aksia_owner_id", owner_id)
    if service_type:
        query = query.eq("service_type", service_type)
    if relationship:
        query = query.eq("relationship", relationship)
    if date_from:
        query = query.gte("start_date", date_from)
    if date_to:
        query = query.lte("start_date", date_to)

    # Sorting
    valid_sort_cols = ["start_date", "rating", "service_type", "expected_revenue",
                       "expected_yr1_flar", "created_at"]
    if sort_by not in valid_sort_cols:
        sort_by = "start_date"
    desc = sort_dir.lower() == "desc"
    query = query.order(sort_by, desc=desc)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    resp = query.execute()
    leads = resp.data or []
    total_count = resp.count or 0
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    # Enrich with org name and owner name
    for lead in leads:
        if lead.get("organization_id"):
            lead["org_name"] = _get_org_name(str(lead["organization_id"]))
        else:
            lead["org_name"] = "—"

        if lead.get("aksia_owner_id"):
            lead["owner_name"] = _get_user_name(str(lead["aksia_owner_id"]))
        else:
            lead["owner_name"] = "—"

    # Reference data for filter dropdowns
    lead_stages = _get_reference_data("lead_stage")
    relationship_types = _get_reference_data("lead_relationship_type")
    service_types = _get_reference_data("service_type")
    users_resp = (
        sb.table("users")
        .select("id, display_name")
        .eq("is_active", True)
        .order("display_name")
        .execute()
    )

    context = {
        "request": request,
        "user": current_user,
        "leads": leads,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "search": search,
        "rating": rating,
        "owner_id": owner_id,
        "service_type": service_type,
        "relationship": relationship,
        "date_from": date_from,
        "date_to": date_to,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "lead_stages": lead_stages,
        "relationship_types": relationship_types,
        "service_types": service_types,
        "users": users_resp.data or [],
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("leads/_list_table.html", context)
    return templates.TemplateResponse("leads/list.html", context)


# ---------------------------------------------------------------------------
# CREATE FORM — GET /leads/new  (must be before /{lead_id})
# ---------------------------------------------------------------------------

@router.get("/new", response_class=HTMLResponse)
async def new_lead_form(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    org_id: str = Query("", alias="org"),
):
    """Render the new lead form. Optionally pre-fill org from query param."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()

    # Pre-fill org if provided
    pre_org = None
    if org_id:
        org_resp = (
            sb.table("organizations")
            .select("id, company_name")
            .eq("id", org_id)
            .eq("is_archived", False)
            .single()
            .execute()
        )
        if org_resp.data:
            pre_org = org_resp.data

    context = _load_form_context(sb, current_user, lead=None, pre_org=pre_org)
    context["request"] = request
    return templates.TemplateResponse("leads/form.html", context)


# ---------------------------------------------------------------------------
# DETAIL — GET /leads/{lead_id}
# ---------------------------------------------------------------------------

@router.get("/{lead_id}", response_class=HTMLResponse)
async def get_lead(
    request: Request,
    lead_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Lead detail page."""
    sb = get_supabase()

    resp = (
        sb.table("leads")
        .select("*")
        .eq("id", str(lead_id))
        .eq("is_archived", False)
        .single()
        .execute()
    )
    lead = resp.data
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Enrich: org name
    org_name = _get_org_name(str(lead["organization_id"])) if lead.get("organization_id") else "—"

    # Enrich: owner name
    owner_name = _get_user_name(str(lead["aksia_owner_id"])) if lead.get("aksia_owner_id") else "—"

    # Related contract (if promoted)
    contract = None
    contract_resp = (
        sb.table("contracts")
        .select("id, start_date, service_type, actual_revenue")
        .eq("originating_lead_id", str(lead_id))
        .eq("is_archived", False)
        .limit(1)
        .execute()
    )
    if contract_resp.data:
        contract = contract_resp.data[0]

    # Related tasks
    tasks_resp = (
        sb.table("tasks")
        .select("id, title, due_date, status, assigned_to")
        .eq("linked_record_type", "lead")
        .eq("linked_record_id", str(lead_id))
        .eq("is_archived", False)
        .order("created_at", desc=True)
        .execute()
    )
    related_tasks = tasks_resp.data or []

    # Reference data for labels
    lead_stages = _get_reference_data("lead_stage")
    stage_labels = {s["value"]: s["label"] for s in lead_stages}

    # Asset class labels
    asset_class_data = _get_reference_data("asset_class")
    ac_labels = {a["value"]: a["label"] for a in asset_class_data}

    context = {
        "request": request,
        "user": current_user,
        "lead": lead,
        "org_name": org_name,
        "owner_name": owner_name,
        "contract": contract,
        "related_tasks": related_tasks,
        "stage_labels": stage_labels,
        "ac_labels": ac_labels,
        "stage_order": STAGE_ORDER,
    }
    return templates.TemplateResponse("leads/detail.html", context)


# ---------------------------------------------------------------------------
# CREATE — POST /leads
# ---------------------------------------------------------------------------

@router.post("/", response_class=HTMLResponse)
async def create_lead(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new lead."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    form = await request.form()
    lead_data = _build_lead_data_from_form(form)
    rating = lead_data.get("rating") or "exploratory"

    # Validate
    errors = _validate_lead_fields(lead_data, rating)

    if errors:
        sb = get_supabase()
        pre_org = None
        if lead_data.get("organization_id"):
            org_resp = (
                sb.table("organizations")
                .select("id, company_name")
                .eq("id", lead_data["organization_id"])
                .single()
                .execute()
            )
            if org_resp.data:
                pre_org = org_resp.data

        context = _load_form_context(
            sb, current_user, lead=lead_data, pre_org=pre_org, errors=errors
        )
        context["request"] = request
        return templates.TemplateResponse("leads/form.html", context)

    # Set system fields
    lead_data["created_by"] = str(current_user.id)
    if not lead_data.get("start_date"):
        lead_data["start_date"] = str(date_type.today())

    # Auto-set end_date for won
    if rating == "won" and not lead_data.get("end_date"):
        lead_data["end_date"] = str(date_type.today())

    sb = get_supabase()
    resp = sb.table("leads").insert(lead_data).execute()

    if resp.data:
        new_lead = resp.data[0]
        lead_id = new_lead["id"]

        # Audit log
        _log_field_change("lead", str(lead_id), "_created", None, "record created", current_user.id)

        # Lead → Contract promotion
        if rating == "won":
            _promote_lead_to_contract(new_lead, current_user.id)

        # Next steps task auto-generation
        if new_lead.get("next_steps_date"):
            org_name = _get_org_name(str(new_lead["organization_id"])) if new_lead.get("organization_id") else "Lead"
            _create_next_steps_task(new_lead, org_name, current_user.id)

        return RedirectResponse(url=f"/leads/{lead_id}", status_code=303)

    raise HTTPException(status_code=500, detail="Failed to create lead")


# ---------------------------------------------------------------------------
# EDIT FORM — GET /leads/{lead_id}/edit
# ---------------------------------------------------------------------------

@router.get("/{lead_id}/edit", response_class=HTMLResponse)
async def edit_lead_form(
    request: Request,
    lead_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the edit lead form."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()
    resp = (
        sb.table("leads")
        .select("*")
        .eq("id", str(lead_id))
        .eq("is_archived", False)
        .single()
        .execute()
    )
    lead = resp.data
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Load linked org for pre-fill
    pre_org = None
    if lead.get("organization_id"):
        org_resp = (
            sb.table("organizations")
            .select("id, company_name")
            .eq("id", str(lead["organization_id"]))
            .single()
            .execute()
        )
        if org_resp.data:
            pre_org = org_resp.data

    context = _load_form_context(sb, current_user, lead=lead, pre_org=pre_org)
    context["request"] = request
    return templates.TemplateResponse("leads/form.html", context)


# ---------------------------------------------------------------------------
# UPDATE — POST /leads/{lead_id}
# ---------------------------------------------------------------------------

@router.post("/{lead_id}", response_class=HTMLResponse)
async def update_lead(
    request: Request,
    lead_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an existing lead."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()

    old_resp = (
        sb.table("leads")
        .select("*")
        .eq("id", str(lead_id))
        .eq("is_archived", False)
        .single()
        .execute()
    )
    old_lead = old_resp.data
    if not old_lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    form = await request.form()
    lead_data = _build_lead_data_from_form(form)
    rating = lead_data.get("rating") or "exploratory"

    # Validate
    errors = _validate_lead_fields(lead_data, rating)

    if errors:
        pre_org = None
        if lead_data.get("organization_id"):
            org_resp = (
                sb.table("organizations")
                .select("id, company_name")
                .eq("id", lead_data["organization_id"])
                .single()
                .execute()
            )
            if org_resp.data:
                pre_org = org_resp.data

        merged_lead = {**old_lead, **lead_data}
        context = _load_form_context(
            sb, current_user, lead=merged_lead, pre_org=pre_org, errors=errors
        )
        context["request"] = request
        return templates.TemplateResponse("leads/form.html", context)

    # Auto-set end_date for won
    if rating == "won" and not lead_data.get("end_date"):
        lead_data["end_date"] = str(date_type.today())

    # Audit log every changed field
    _audit_changes(str(lead_id), old_lead, lead_data, current_user.id)

    # Update
    sb.table("leads").update(lead_data).eq("id", str(lead_id)).execute()

    # Lead → Contract promotion: if rating changed to "won"
    old_rating = old_lead.get("rating")
    if old_rating != "won" and rating == "won":
        updated_lead = {**old_lead, **lead_data, "id": str(lead_id)}
        _promote_lead_to_contract(updated_lead, current_user.id)

    # Next steps task: if next_steps_date changed and is now set
    old_nsd = old_lead.get("next_steps_date")
    new_nsd = lead_data.get("next_steps_date")
    if new_nsd and str(old_nsd) != str(new_nsd):
        updated_lead = {**old_lead, **lead_data, "id": str(lead_id)}
        org_name = _get_org_name(str(updated_lead["organization_id"])) if updated_lead.get("organization_id") else "Lead"
        _create_next_steps_task(updated_lead, org_name, current_user.id)

    return RedirectResponse(url=f"/leads/{lead_id}", status_code=303)


# ---------------------------------------------------------------------------
# ARCHIVE (soft delete) — POST /leads/{lead_id}/archive
# ---------------------------------------------------------------------------

@router.post("/{lead_id}/archive", response_class=HTMLResponse)
async def archive_lead(
    request: Request,
    lead_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-delete a lead."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    sb.table("leads").update({"is_archived": True}).eq("id", str(lead_id)).execute()
    _log_field_change("lead", str(lead_id), "is_archived", False, True, current_user.id)

    if request.headers.get("HX-Request"):
        return HTMLResponse('<p class="text-sm text-green-600">Lead archived.</p>')
    return RedirectResponse(url="/leads", status_code=303)

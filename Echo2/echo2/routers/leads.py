"""Leads router — full CRUD, search, filters, pagination, audit logging,
stage-gated validation, next-steps task generation."""

from datetime import date as date_type
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from db.helpers import get_reference_data, log_field_change, audit_changes, get_org_name, get_user_name
from db.field_service import get_field_definitions, enrich_field_definitions, save_custom_values
from services.form_service import build_form_context, parse_form_data, validate_form_data, get_users_for_lookup, split_core_eav
from services.grid_service import build_grid_context
from dependencies import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/leads", tags=["leads"])
templates = Jinja2Templates(directory="templates")

# Stage hierarchy for gated field requirements — SERVICE leads
STAGE_ORDER = {
    "exploratory": 1,
    "radar": 2,
    "focus": 3,
    "verbal_mandate": 4,
    "won": 5,
    "did_not_win": 5,
}
INACTIVE_STAGES = {"won", "did_not_win"}
LOST_STAGES = {"did_not_win"}

# Stage hierarchy for PRODUCT leads
PRODUCT_STAGE_ORDER = {
    "target_identified": 1,
    "intro_scheduled": 2,
    "initial_meeting_complete": 3,
    "ddq_materials_sent": 4,
    "due_diligence": 5,
    "ic_review": 6,
    "soft_circle": 7,
    "legal_docs": 8,
    "closed": 9,
    "declined": 10,
}
PRODUCT_TERMINAL_STAGES = {"closed", "declined"}

# Engagement status → auto-date mapping
_ENGAGEMENT_DATE_FIELDS = {
    "prospect_contacted": "prospect_contacted_date",
    "prospect_responded": "prospect_responded_date",
    "initial_meeting": "initial_meeting_date",
    "ongoing_dialogue": "initial_meeting_complete_date",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sync_lead_owners(lead_id: str, owner_ids: list[str], primary_owner_id: str | None = None) -> None:
    """Sync the lead_owners junction table for a lead.

    Replaces all existing owners with the provided list.
    The first owner (or primary_owner_id) is marked as is_primary=True.
    """
    sb = get_supabase()
    # Delete existing owners
    sb.table("lead_owners").delete().eq("lead_id", lead_id).execute()
    # Insert new owners
    if not primary_owner_id and owner_ids:
        primary_owner_id = owner_ids[0]
    for uid in owner_ids:
        sb.table("lead_owners").insert({
            "lead_id": lead_id,
            "user_id": uid,
            "is_primary": uid == primary_owner_id,
        }).execute()


def _get_lead_owners(lead_id: str) -> list[dict]:
    """Get all owners for a lead from the junction table."""
    sb = get_supabase()
    resp = (
        sb.table("lead_owners")
        .select("user_id, is_primary")
        .eq("lead_id", lead_id)
        .order("is_primary", desc=True)
        .execute()
    )
    return resp.data or []


def _batch_get_lead_owners(lead_ids: list[str]) -> dict[str, list[dict]]:
    """Batch get owners for multiple leads. Returns {lead_id: [owner_dicts]}."""
    if not lead_ids:
        return {}
    sb = get_supabase()
    resp = (
        sb.table("lead_owners")
        .select("lead_id, user_id, is_primary")
        .in_("lead_id", lead_ids)
        .execute()
    )
    result: dict[str, list[dict]] = {}
    for row in (resp.data or []):
        result.setdefault(str(row["lead_id"]), []).append(row)
    return result


def _build_lead_data_from_form(form: dict) -> dict:
    """Extract lead fields from form data. Handles all lead types (service/product)."""
    data = {}

    # Lead type (V17: service or product)
    lead_type = (form.get("lead_type") or "service").strip()
    data["lead_type"] = lead_type

    # Title
    title = (form.get("title") or "").strip()
    data["title"] = title if title else None

    # Organization (single FK)
    org_id = (form.get("organization_id") or "").strip()
    data["organization_id"] = org_id if org_id else None

    # Rating / stage
    if lead_type == "product":
        data["rating"] = (form.get("rating") or "target_identified").strip()
    else:
        data["rating"] = (form.get("rating") or "exploratory").strip()

    # Dates (common)
    for date_field in ("start_date", "end_date", "next_steps_date",
                       "expected_contract_start_date"):
        val = (form.get(date_field) or "").strip()
        data[date_field] = val if val else None

    # Aksia Owner(s) — supports both single select (legacy) and multi-select
    owner_ids = form.getlist("owner_ids[]") if hasattr(form, "getlist") else []
    owner_ids = [o.strip() for o in owner_ids if o.strip()]
    if not owner_ids:
        owner = (form.get("aksia_owner_id") or "").strip()
        if owner:
            owner_ids = [owner]
    data["_owner_ids"] = owner_ids
    data["aksia_owner_id"] = owner_ids[0] if owner_ids else None

    # Text fields (common)
    for text_field in ("summary", "next_steps", "expected_revenue_notes",
                       "expected_size"):
        val = (form.get(text_field) or "").strip()
        data[text_field] = val if val else None

    # Common dropdown fields (V17)
    for dd_field in ("engagement_status", "coverage_office", "service_type",
                     "service_subtype", "risk_weight", "revenue_currency",
                     "commitment_status", "waystone_approved", "gp_commitment",
                     "deployment_period", "expected_fund_close"):
        val = (form.get(dd_field) or "").strip()
        data[dd_field] = val if val else None

    # Asset classes (multi-select)
    asset_classes = form.getlist("asset_classes") if hasattr(form, "getlist") else []
    data["asset_classes"] = list(asset_classes) if asset_classes else None

    # Common decimal fields (V17)
    for dec_field in ("expected_yr1_flar", "expected_longterm_flar", "previous_flar",
                      "expected_fee", "indicative_size_low", "indicative_size_high",
                      "expected_management_fee", "expected_incentive_fee",
                      "expected_preferred_return", "expected_catchup_pct"):
        val = (form.get(dec_field) or "").strip()
        if val:
            try:
                data[dec_field] = float(val)
            except ValueError:
                data[dec_field] = None
        else:
            data[dec_field] = None

    # Common date fields (V17 timeline — auto-populated but editable)
    for date_field in ("prospect_contacted_date", "prospect_responded_date",
                       "initial_meeting_date", "initial_meeting_complete_date",
                       "rfp_due_date", "rfp_submitted_date"):
        val = (form.get(date_field) or "").strip()
        data[date_field] = val if val else None

    # Booleans (V17)
    data["includes_product_allocation"] = form.get("includes_product_allocation") == "on"
    data["includes_max_access"] = form.get("includes_max_access") == "on"

    if lead_type == "product":
        # --- Product-specific fields ---
        fund_id = (form.get("fund_id") or "").strip()
        data["fund_id"] = fund_id if fund_id else None

        share_class = (form.get("share_class") or "").strip()
        data["share_class"] = share_class if share_class else None

        # Decline reason (only when stage=declined)
        if data["rating"] == "declined":
            dr = (form.get("decline_reason") or "").strip()
            data["decline_reason"] = dr if dr else None
        else:
            data["decline_reason"] = None

        # Decimal fields (allocation)
        for dec_field in ("target_allocation_mn", "soft_circle_mn", "hard_circle_mn"):
            val = (form.get(dec_field) or "").strip()
            if val:
                try:
                    data[dec_field] = float(val)
                except ValueError:
                    data[dec_field] = None
            else:
                data[dec_field] = None

        # Probability (integer 0-100)
        prob = (form.get("probability_pct") or "").strip()
        if prob:
            try:
                data["probability_pct"] = int(prob)
            except ValueError:
                data["probability_pct"] = None
        else:
            data["probability_pct"] = None

        # Linked lead (optional FK)
        linked = (form.get("linked_lead_id") or "").strip()
        data["_linked_lead_id"] = linked if linked else None

        # Clear service-only fields
        for f in ("relationship", "potential_coverage", "legacy_onboarding_holdings"):
            data[f] = None
        data["legacy_onboarding"] = None
        data["decline_reason_code"] = None
        data["decline_rationale"] = None

    else:
        # --- Service-specific fields ---
        for text_field in ("relationship", "source",
                          "potential_coverage", "legacy_onboarding_holdings"):
            val = (form.get(text_field) or "").strip()
            data[text_field] = val if val else None

        # Boolean: legacy onboarding
        data["legacy_onboarding"] = form.get("legacy_onboarding") == "on"

        # Decline fields (V17: did_not_win)
        if data["rating"] == "did_not_win":
            for f in ("decline_reason_code", "decline_rationale"):
                val = (form.get(f) or "").strip()
                data[f] = val if val else None
        else:
            data["decline_reason_code"] = None
            data["decline_rationale"] = None

        # Clear product-only fields
        for f in ("fund_id", "share_class", "decline_reason",
                  "target_allocation_mn", "soft_circle_mn", "hard_circle_mn",
                  "probability_pct", "stage_entry_date"):
            data[f] = None

    return data


def _validate_lead_fields(data: dict, rating: str) -> list[str]:
    """Validate fields based on current stage and lead type. Returns list of error strings."""
    errors = []
    lead_type = data.get("lead_type", "service")

    # Always required
    if not data.get("title"):
        errors.append("Title is required.")
    if not data.get("organization_id"):
        errors.append("Organization is required.")
    if not data.get("aksia_owner_id"):
        errors.append("Aksia Owner is required.")

    if lead_type == "product":
        # --- Product validation ---
        if not data.get("fund_id"):
            errors.append("Fund is required.")
        if not data.get("share_class"):
            errors.append("Share Class is required.")

        # Decline reason required when stage=declined
        if rating == "declined" and not data.get("decline_reason"):
            errors.append("Decline Reason is required when stage is Declined.")

        # Probability range check
        if data.get("probability_pct") is not None:
            if data["probability_pct"] < 0 or data["probability_pct"] > 100:
                errors.append("Probability must be between 0 and 100.")

        # Allocation non-negative checks
        for field, label in [
            ("target_allocation_mn", "Target Allocation"),
            ("soft_circle_mn", "Soft Circle"),
            ("hard_circle_mn", "Hard Circle"),
        ]:
            if data.get(field) is not None and data[field] < 0:
                errors.append(f"{label} cannot be negative.")

    else:
        # --- Service validation (stage-gated, V17) ---
        stage = STAGE_ORDER.get(rating, 1)

        # Exploratory+ (stage >= 1)
        if stage >= 1:
            if not data.get("relationship"):
                errors.append("Relationship type is required.")

        # Radar+ (stage >= 2)
        if stage >= 2:
            if not data.get("service_type"):
                errors.append("Service Type is required at Radar stage and above.")
            if not data.get("asset_classes"):
                errors.append("At least one Asset Class is required at Radar stage and above.")
            # Source is now suggested, not required (V17)

        # Focus+ (stage >= 3) — V17: removed pricing_proposal, expected_decision_date, expected_revenue
        if stage >= 3:
            if not data.get("risk_weight"):
                errors.append("Probability of Close is required at Focus stage and above.")
            # Previous FLAR for contract extension
            if data.get("relationship") == "existing_client_contract_extension":
                if data.get("previous_flar") is None:
                    errors.append("Previous FLAR is required for Contract Extension relationships.")

        # Verbal Mandate+ (stage >= 4)
        if stage >= 4:
            if data.get("legacy_onboarding") is None:
                errors.append("Legacy Onboarding is required at Verbal Mandate stage.")
            if data.get("legacy_onboarding") and not data.get("legacy_onboarding_holdings"):
                errors.append("Legacy Onboarding Holdings required when Legacy Onboarding is Yes.")

        # Did Not Win requires end_date and decline_reason_code
        if rating == "did_not_win":
            if not data.get("end_date"):
                errors.append("End Date is required for Did Not Win leads.")
            if not data.get("decline_reason_code"):
                errors.append("Decline Reason is required for Did Not Win leads.")

    return errors


def _create_next_steps_task(lead: dict, org_name: str, changed_by: UUID) -> None:
    """Auto-generate a Task when next_steps_date (follow-up date) is set."""
    sb = get_supabase()
    lead_type = lead.get("lead_type", "service")

    # Title includes fund ticker for product leads
    if lead_type == "product" and lead.get("fund_id"):
        fund_ticker = _get_fund_ticker(str(lead["fund_id"]))
        title = f"Lead follow-up: {org_name} ({fund_ticker})"
        source = "lead_next_steps"
    else:
        title = f"Lead follow-up: {org_name}"
        source = "lead_next_steps"

    sb.table("tasks").insert({
        "title": title,
        "due_date": lead.get("next_steps_date"),
        "assigned_to": str(lead["aksia_owner_id"]) if lead.get("aksia_owner_id") else str(changed_by),
        "status": "open",
        "notes": lead.get("next_steps") or "",
        "source": source,
        "linked_record_type": "lead",
        "linked_record_id": str(lead["id"]),
        "created_by": str(changed_by),
    }).execute()


def _get_fund_ticker(fund_id: str) -> str:
    """Get fund ticker by ID. Returns ticker or '?' if not found."""
    sb = get_supabase()
    resp = sb.table("funds").select("ticker").eq("id", fund_id).maybe_single().execute()
    return resp.data["ticker"] if resp.data else "?"


def _get_fund_info(fund_id: str) -> dict | None:
    """Get full fund info by ID."""
    sb = get_supabase()
    resp = sb.table("funds").select("*").eq("id", fund_id).maybe_single().execute()
    return resp.data



def _load_form_context(sb, current_user, lead=None, pre_org=None, errors=None):
    """Load all reference data and users needed for the lead form."""
    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()

    # Load existing owners if editing
    selected_owner_ids = []
    if lead and lead.get("id"):
        owners = _get_lead_owners(str(lead["id"]))
        selected_owner_ids = [str(o["user_id"]) for o in owners]
    elif lead and lead.get("_owner_ids"):
        selected_owner_ids = lead["_owner_ids"]
    elif lead and lead.get("aksia_owner_id"):
        selected_owner_ids = [str(lead["aksia_owner_id"])]

    lead_type = (lead.get("lead_type") if lead else None) or "service"

    # Stages scoped by lead_type via parent_value
    all_stages = get_reference_data("lead_stage")
    all_service_stages = [s for s in all_stages if s.get("parent_value") == "service"]
    all_product_stages = [s for s in all_stages if s.get("parent_value") == "product"]
    if lead_type == "product":
        lead_stages = all_product_stages
    else:
        lead_stages = all_service_stages

    # Funds for product lead types
    funds_resp = sb.table("funds").select("id, fund_name, ticker, brand").eq("is_active", True).order("ticker").execute()
    funds = funds_resp.data or []

    # Decline reasons for product leads
    decline_reasons = get_reference_data("decline_reason")

    # Lead type options
    lead_types = get_reference_data("lead_type")

    return {
        "lead_stages": lead_stages,
        "all_service_stages": all_service_stages,
        "all_product_stages": all_product_stages,
        "relationship_types": get_reference_data("lead_relationship_type"),
        "service_types": get_reference_data("service_type"),
        "asset_classes": get_reference_data("asset_class"),
        "engagement_statuses": get_reference_data("engagement_status"),
        "risk_weights": get_reference_data("risk_weight"),
        "coverage_offices": get_reference_data("coverage_office"),
        "commitment_statuses": get_reference_data("commitment_status"),
        "waystone_options": get_reference_data("waystone_approved"),
        "decline_reason_codes": get_reference_data("decline_reason_code"),
        "revenue_currencies": get_reference_data("revenue_currency"),
        "gp_commitment_options": get_reference_data("gp_commitment"),
        "deployment_periods": get_reference_data("deployment_period"),
        "fund_close_options": get_reference_data("expected_fund_close"),
        "users": users_resp.data or [],
        "selected_owner_ids": selected_owner_ids,
        "funds": funds,
        "decline_reasons": decline_reasons,
        "lead_types": lead_types,
        "lead_type": lead_type,
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
# LIST — GET /leads
# ---------------------------------------------------------------------------

@router.get("/my-leads", response_class=HTMLResponse)
async def my_leads(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    lead_type: str = Query("", alias="lead_type"),
):
    """Redirect to /leads with owner and optional lead_type filter."""
    params = f"?owner={current_user.id}&view=my"
    if lead_type:
        params += f"&lead_type={lead_type}"
    return RedirectResponse(url=f"/leads{params}", status_code=303)


@router.get("/", response_class=HTMLResponse)
async def list_leads(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List leads with filtering, search, sorting, and pagination."""
    params = dict(request.query_params)
    lead_type_filter = params.get("lead_type", "")
    view = params.get("view", "")

    extra_filters = {}
    if lead_type_filter:
        extra_filters["lead_type"] = lead_type_filter
    if view == "my":
        extra_filters["view"] = "my"
        extra_filters["_user_id"] = str(current_user.id)

    ctx = build_grid_context("lead", request, current_user, base_url="/leads", extra_filters=extra_filters)

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("components/_grid.html", {"request": request, **ctx})

    # Load reference data for filter bar
    sb = get_supabase()
    lead_types = get_reference_data("lead_type")
    lead_stages = get_reference_data("lead_stage")
    service_types = get_reference_data("service_type")
    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
    funds_resp = sb.table("funds").select("id, ticker, fund_name").execute()

    ctx.update({
        "user": current_user,
        "view_mode": "my_leads" if view == "my" else "all_leads",
        "total_count": ctx["pagination"]["total"],
        "search": ctx["filters"].get("q", ""),
        "rating": ctx["filters"].get("stage", ""),
        "owner_id": ctx["filters"].get("owner", ""),
        "service_type": ctx["filters"].get("service", ""),
        "relationship": ctx["filters"].get("rel", ""),
        "lead_type_filter": lead_type_filter,
        "fund_filter": ctx["filters"].get("fund", ""),
        "date_from": ctx["filters"].get("from", ""),
        "date_to": ctx["filters"].get("to", ""),
        "view": view,
        "lead_types": lead_types,
        "lead_stages": lead_stages,
        "service_types": service_types,
        "users": users_resp.data or [],
        "funds_list": funds_resp.data or [],
    })
    return templates.TemplateResponse("leads/list.html", {"request": request, **ctx})


# ---------------------------------------------------------------------------
# CREATE FORM — GET /leads/new  (must be before /{lead_id})
# ---------------------------------------------------------------------------

@router.get("/leads-for-org", response_class=HTMLResponse)
async def leads_for_org(
    request: Request,
    org_id: str = Query(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX endpoint: return service leads for an org as <option> elements
    (used by product lead form to link to a service lead)."""
    if not org_id:
        return HTMLResponse('<option value="">— None —</option>')

    sb = get_supabase()
    resp = (
        sb.table("leads")
        .select("id, rating, summary, service_type")
        .eq("organization_id", org_id)
        .eq("lead_type", "service")
        .eq("is_deleted", False)
        .order("start_date", desc=True)
        .limit(50)
        .execute()
    )
    leads = resp.data or []

    options = ['<option value="">— None —</option>']
    for lead in leads:
        label = f"{(lead.get('rating') or '').replace('_', ' ').title()}"
        if lead.get("service_type"):
            label += f" — {lead['service_type'].replace('_', ' ').title()}"
        if lead.get("summary"):
            label += f" ({lead['summary'][:40]})"
        options.append(f'<option value="{lead["id"]}">{label}</option>')

    return HTMLResponse("\n".join(options))


@router.get("/new", response_class=HTMLResponse)
async def new_lead_form(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    org_id: str = Query("", alias="org"),
    lead_type_param: str = Query("service", alias="type"),
):
    """Render the new lead form. Optionally pre-fill org and lead_type from query params."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()

    # Pre-fill org if provided
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
        if org_resp.data:
            pre_org = org_resp.data

    # Pre-set lead_type
    lead_stub = {"lead_type": lead_type_param}

    # Load users for form_service lookup fields
    users_list = get_users_for_lookup()
    form_ctx = build_form_context("lead", record=lead_stub, extra_context={"users": users_list})

    context = _load_form_context(sb, current_user, lead=lead_stub, pre_org=pre_org)
    context["request"] = request
    context["record"] = form_ctx["record"]
    context["sections"] = form_ctx["sections"]
    context["field_defs"] = form_ctx["field_defs"]
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
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    lead = resp.data
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead_type = lead.get("lead_type", "service")

    # Enrich: org name
    org_name = get_org_name(str(lead["organization_id"])) if lead.get("organization_id") else "—"

    # Enrich: owner name
    # Resolve owners from junction table (with fallback to aksia_owner_id)
    lead_owners = _get_lead_owners(str(lead_id))
    if lead_owners:
        from db.helpers import batch_resolve_users
        owner_user_ids = [o["user_id"] for o in lead_owners]
        owner_names_map = batch_resolve_users(owner_user_ids)
        owner_names = []
        for o in lead_owners:
            name = owner_names_map.get(str(o["user_id"]), "Unknown")
            if o.get("is_primary"):
                name += " (primary)"
            owner_names.append(name)
        owner_name = ", ".join(owner_names)
    else:
        owner_name = get_user_name(str(lead["aksia_owner_id"])) if lead.get("aksia_owner_id") else "—"

    # Fund info for product leads
    fund_info = None
    if lead_type == "product" and lead.get("fund_id"):
        fund_info = _get_fund_info(str(lead["fund_id"]))

    # Related contract (if one exists for this lead)
    contract = None
    contract_resp = (
        sb.table("contracts")
        .select("id, start_date, service_type, actual_revenue")
        .eq("originating_lead_id", str(lead_id))
        .eq("is_deleted", False)
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
        .eq("is_deleted", False)
        .order("created_at", desc=True)
        .execute()
    )
    related_tasks = tasks_resp.data or []

    # Linked activities (via activity_lead_links)
    activity_links_resp = (
        sb.table("activity_lead_links")
        .select("activity_id")
        .eq("lead_id", str(lead_id))
        .execute()
    )
    linked_activities = []
    act_ids = [r["activity_id"] for r in (activity_links_resp.data or [])]
    if act_ids:
        acts_resp = (
            sb.table("activities")
            .select("id, title, effective_date, activity_type, subtype, details")
            .in_("id", act_ids)
            .eq("is_deleted", False)
            .order("effective_date", desc=True)
            .execute()
        )
        linked_activities = acts_resp.data or []

    # Reference data for labels — scoped stages
    all_stages = get_reference_data("lead_stage")
    if lead_type == "product":
        lead_stages = [s for s in all_stages if s.get("parent_value") == "product"]
        stage_order = PRODUCT_STAGE_ORDER
    else:
        lead_stages = [s for s in all_stages if s.get("parent_value") == "service"]
        stage_order = STAGE_ORDER
    stage_labels = {s["value"]: s["label"] for s in lead_stages}

    # Decline reason labels (product leads)
    decline_reasons = get_reference_data("decline_reason")
    decline_labels = {d["value"]: d["label"] for d in decline_reasons}

    # Decline reason code labels (service leads — did_not_win)
    decline_reason_codes = get_reference_data("decline_reason_code")
    decline_code_labels = {d["value"]: d["label"] for d in decline_reason_codes}

    # Asset class labels
    asset_class_data = get_reference_data("asset_class")
    ac_labels = {a["value"]: a["label"] for a in asset_class_data}

    # Engagement status labels
    engagement_statuses = get_reference_data("engagement_status")
    engagement_labels = {e["value"]: e["label"] for e in engagement_statuses}

    # Coverage office labels
    coverage_offices = get_reference_data("coverage_office")
    coverage_office_labels = {c["value"]: c["label"] for c in coverage_offices}

    # Risk weight labels
    risk_weights = get_reference_data("risk_weight")
    risk_weight_labels = {r["value"]: r["label"] for r in risk_weights}

    # RFP auto-boolean (computed from engagement_status)
    rfp_active = lead.get("engagement_status") in ("rfp_expected", "rfp_in_progress", "rfp_submitted")

    context = {
        "request": request,
        "user": current_user,
        "lead": lead,
        "lead_type": lead_type,
        "org_name": org_name,
        "owner_name": owner_name,
        "fund_info": fund_info,
        "contract": contract,
        "related_tasks": related_tasks,
        "linked_activities": linked_activities,
        "stage_labels": stage_labels,
        "decline_labels": decline_labels,
        "decline_code_labels": decline_code_labels,
        "ac_labels": ac_labels,
        "engagement_labels": engagement_labels,
        "coverage_office_labels": coverage_office_labels,
        "risk_weight_labels": risk_weight_labels,
        "stage_order": stage_order,
        "rfp_active": rfp_active,
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

    # --- Dynamic form service: parse ---
    field_defs = get_field_definitions("lead", active_only=True)
    field_defs = enrich_field_definitions(field_defs)
    lead_data = parse_form_data("lead", form, field_defs)

    # --- Entity-specific field extraction (owner_ids[], lead_type, linked records) ---
    owner_ids = form.getlist("owner_ids[]") if hasattr(form, "getlist") else []
    owner_ids = [o.strip() for o in owner_ids if o.strip()]
    if not owner_ids:
        owner = (form.get("aksia_owner_id") or "").strip()
        if owner:
            owner_ids = [owner]
    lead_data["_owner_ids"] = owner_ids
    lead_data["aksia_owner_id"] = owner_ids[0] if owner_ids else lead_data.get("aksia_owner_id")

    # Ensure lead_type is captured
    if not lead_data.get("lead_type"):
        lead_data["lead_type"] = (form.get("lead_type") or "service").strip()

    # Linked lead (product → service FK)
    linked = (form.get("linked_lead_id") or "").strip()
    lead_data["_linked_lead_id"] = linked if linked else None

    rating = lead_data.get("rating") or "exploratory"

    # --- Dynamic form service: validate ---
    errors = validate_form_data("lead", lead_data, field_defs)

    # --- Entity-specific validation (product requires fund_id + share_class, lead_owners, etc.) ---
    lead_type = lead_data.get("lead_type", "service")
    if not lead_data.get("organization_id"):
        errors.append("Organization is required.")
    if not lead_data.get("aksia_owner_id"):
        errors.append("Aksia Owner is required.")
    if lead_type == "product":
        if not lead_data.get("fund_id"):
            errors.append("Fund is required.")
        if not lead_data.get("share_class"):
            errors.append("Share Class is required.")
        if rating == "declined" and not lead_data.get("decline_reason"):
            errors.append("Decline Reason is required when stage is Declined.")
    if lead_type == "service" and rating in LOST_STAGES:
        if not lead_data.get("end_date"):
            errors.append("End Date is required for Did Not Win leads.")

    if errors:
        sb = get_supabase()
        pre_org = None
        if lead_data.get("organization_id"):
            org_resp = (
                sb.table("organizations")
                .select("id, company_name")
                .eq("id", lead_data["organization_id"])
                .maybe_single()
                .execute()
            )
            if org_resp.data:
                pre_org = org_resp.data

        users_list = get_users_for_lookup()
        form_ctx = build_form_context("lead", record=lead_data, extra_context={"users": users_list})

        context = _load_form_context(
            sb, current_user, lead=lead_data, pre_org=pre_org, errors=errors
        )
        context["request"] = request
        context["record"] = form_ctx["record"]
        context["sections"] = form_ctx["sections"]
        context["field_defs"] = form_ctx["field_defs"]
        return templates.TemplateResponse("leads/form.html", context)

    # Set system fields
    lead_data["created_by"] = str(current_user.id)
    if not lead_data.get("start_date"):
        lead_data["start_date"] = str(date_type.today())

    lead_type = lead_data.get("lead_type", "service")

    # Auto-set end_date for won/did_not_win
    if rating in ("won", "did_not_win") and not lead_data.get("end_date"):
        lead_data["end_date"] = str(date_type.today())

    # Set stage_entry_date for product leads
    if lead_type == "product":
        lead_data["stage_entry_date"] = str(date_type.today())

    # Auto-set engagement status timeline dates (V17)
    eng_status = lead_data.get("engagement_status")
    if eng_status and eng_status in _ENGAGEMENT_DATE_FIELDS:
        date_field = _ENGAGEMENT_DATE_FIELDS[eng_status]
        if not lead_data.get(date_field):
            lead_data[date_field] = str(date_type.today())

    # Extract non-DB fields before inserting
    owner_ids = lead_data.pop("_owner_ids", [])
    lead_data.pop("_linked_lead_id", None)

    sb = get_supabase()
    core_data, eav_data = split_core_eav(lead_data, field_defs)
    resp = sb.table("leads").insert(core_data).execute()

    if resp.data:
        new_lead = resp.data[0]
        lead_id = new_lead["id"]

        # Save EAV custom field values
        if eav_data:
            save_custom_values("lead", str(lead_id), eav_data, field_defs)

        # Sync lead owners
        if owner_ids:
            _sync_lead_owners(str(lead_id), owner_ids)

        # Audit log
        log_field_change("lead", str(lead_id), "_created", None, "record created", current_user.id)

        # Next steps task auto-generation
        if new_lead.get("next_steps_date"):
            org_name = get_org_name(str(new_lead["organization_id"])) if new_lead.get("organization_id") else "Lead"
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
        .eq("is_deleted", False)
        .maybe_single()
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
            .maybe_single()
            .execute()
        )
        if org_resp.data:
            pre_org = org_resp.data

    # Build dynamic form context for field_defs and sections
    users_list = get_users_for_lookup()
    form_ctx = build_form_context("lead", record=lead, extra_context={"users": users_list})

    context = _load_form_context(sb, current_user, lead=lead, pre_org=pre_org)
    context["request"] = request
    context["record"] = form_ctx["record"]
    context["sections"] = form_ctx["sections"]
    context["field_defs"] = form_ctx["field_defs"]
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
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    old_lead = old_resp.data
    if not old_lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    form = await request.form()

    # --- Dynamic form service: parse ---
    field_defs = get_field_definitions("lead", active_only=True)
    field_defs = enrich_field_definitions(field_defs)
    lead_data = parse_form_data("lead", form, field_defs)

    # --- Entity-specific field extraction (owner_ids[], lead_type locking, linked records) ---
    owner_ids = form.getlist("owner_ids[]") if hasattr(form, "getlist") else []
    owner_ids = [o.strip() for o in owner_ids if o.strip()]
    if not owner_ids:
        owner = (form.get("aksia_owner_id") or "").strip()
        if owner:
            owner_ids = [owner]
    lead_data["_owner_ids"] = owner_ids
    lead_data["aksia_owner_id"] = owner_ids[0] if owner_ids else lead_data.get("aksia_owner_id")

    # Lock lead_type to existing value on edit (cannot change lead_type after creation)
    lead_data["lead_type"] = old_lead.get("lead_type", "service")

    # Linked lead (product → service FK)
    linked = (form.get("linked_lead_id") or "").strip()
    lead_data["_linked_lead_id"] = linked if linked else None

    rating = lead_data.get("rating") or "exploratory"

    # --- Dynamic form service: validate ---
    errors = validate_form_data("lead", lead_data, field_defs, record=old_lead)

    # --- Entity-specific validation (product requires fund_id + share_class, lead_owners, etc.) ---
    lead_type_val = lead_data.get("lead_type", "service")
    if not lead_data.get("organization_id"):
        errors.append("Organization is required.")
    if not lead_data.get("aksia_owner_id"):
        errors.append("Aksia Owner is required.")
    if lead_type_val == "product":
        if not lead_data.get("fund_id"):
            errors.append("Fund is required.")
        if not lead_data.get("share_class"):
            errors.append("Share Class is required.")
        if rating == "declined" and not lead_data.get("decline_reason"):
            errors.append("Decline Reason is required when stage is Declined.")
    if lead_type_val == "service" and rating in LOST_STAGES:
        if not lead_data.get("end_date"):
            errors.append("End Date is required for Did Not Win leads.")

    if errors:
        pre_org = None
        if lead_data.get("organization_id"):
            org_resp = (
                sb.table("organizations")
                .select("id, company_name")
                .eq("id", lead_data["organization_id"])
                .maybe_single()
                .execute()
            )
            if org_resp.data:
                pre_org = org_resp.data

        merged_lead = {**old_lead, **lead_data}
        users_list = get_users_for_lookup()
        form_ctx = build_form_context("lead", record=merged_lead, extra_context={"users": users_list})

        context = _load_form_context(
            sb, current_user, lead=merged_lead, pre_org=pre_org, errors=errors
        )
        context["request"] = request
        context["record"] = form_ctx["record"]
        context["sections"] = form_ctx["sections"]
        context["field_defs"] = form_ctx["field_defs"]
        return templates.TemplateResponse("leads/form.html", context)

    lead_type = lead_data.get("lead_type", old_lead.get("lead_type", "service"))

    # Auto-set end_date for won/did_not_win
    if rating in ("won", "did_not_win") and not lead_data.get("end_date"):
        lead_data["end_date"] = str(date_type.today())

    # Auto-set stage_entry_date when stage changes (product leads)
    if lead_type == "product":
        old_rating = old_lead.get("rating")
        if old_rating != rating:
            lead_data["stage_entry_date"] = str(date_type.today())

    # Auto-set engagement status timeline dates (V17)
    old_eng = old_lead.get("engagement_status")
    new_eng = lead_data.get("engagement_status")
    if new_eng and new_eng != old_eng and new_eng in _ENGAGEMENT_DATE_FIELDS:
        date_field = _ENGAGEMENT_DATE_FIELDS[new_eng]
        if not lead_data.get(date_field) and not old_lead.get(date_field):
            lead_data[date_field] = str(date_type.today())

    # Extract non-DB fields before updating
    owner_ids = lead_data.pop("_owner_ids", [])
    lead_data.pop("_linked_lead_id", None)

    # Audit log every changed field
    audit_changes("lead", str(lead_id), old_lead, lead_data, current_user.id)

    # Update
    core_data, eav_data = split_core_eav(lead_data, field_defs)
    sb.table("leads").update(core_data).eq("id", str(lead_id)).execute()
    if eav_data:
        save_custom_values("lead", str(lead_id), eav_data, field_defs)

    # Sync lead owners
    if owner_ids:
        _sync_lead_owners(str(lead_id), owner_ids)

    # Next steps task: if next_steps_date changed and is now set
    old_nsd = old_lead.get("next_steps_date")
    new_nsd = lead_data.get("next_steps_date")
    if new_nsd and str(old_nsd) != str(new_nsd):
        updated_lead = {**old_lead, **lead_data, "id": str(lead_id)}
        org_name = get_org_name(str(updated_lead["organization_id"])) if updated_lead.get("organization_id") else "Lead"
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
    sb.table("leads").update({"is_deleted": True}).eq("id", str(lead_id)).execute()
    log_field_change("lead", str(lead_id), "is_deleted", False, True, current_user.id)

    if request.headers.get("HX-Request"):
        return HTMLResponse('<p class="text-sm text-green-600">Lead archived.</p>')
    return RedirectResponse(url="/leads", status_code=303)

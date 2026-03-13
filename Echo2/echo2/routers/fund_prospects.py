"""Fund prospects router — full CRUD, search, filters, pagination, audit logging,
stage validation, next-steps task generation."""

from datetime import date as date_type
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from dependencies import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/fund-prospects", tags=["fund_prospects"])
templates = Jinja2Templates(directory="templates")

# Stage ordering for progress bar and validation
STAGE_ORDER = {
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
            _log_field_change("fund_prospect", record_id, field, old_val, new_val, changed_by)


def _build_prospect_data_from_form(form: dict) -> dict:
    """Extract fund prospect fields from form data."""
    data = {}

    # Organization (single FK)
    org_id = (form.get("organization_id") or "").strip()
    data["organization_id"] = org_id if org_id else None

    # Fund (single FK)
    fund_id = (form.get("fund_id") or "").strip()
    data["fund_id"] = fund_id if fund_id else None

    # Share class
    share_class = (form.get("share_class") or "").strip()
    data["share_class"] = share_class if share_class else None

    # Stage
    data["stage"] = (form.get("stage") or "target_identified").strip()

    # Decline reason (only meaningful when stage=declined)
    if data["stage"] == "declined":
        dr = (form.get("decline_reason") or "").strip()
        data["decline_reason"] = dr if dr else None
    else:
        data["decline_reason"] = None

    # Aksia Owner (user lookup)
    owner = (form.get("aksia_owner_id") or "").strip()
    data["aksia_owner_id"] = owner if owner else None

    # Decimal fields ($mn)
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
    data["linked_lead_id"] = linked if linked else None

    # Text fields
    for text_field in ("next_steps", "notes"):
        val = (form.get(text_field) or "").strip()
        data[text_field] = val if val else None

    # Next steps date
    nsd = (form.get("next_steps_date") or "").strip()
    data["next_steps_date"] = nsd if nsd else None

    return data


def _validate_prospect_fields(data: dict) -> list[str]:
    """Validate fund prospect fields. Returns list of error strings."""
    errors = []

    if not data.get("organization_id"):
        errors.append("Organization is required.")
    if not data.get("fund_id"):
        errors.append("Fund is required.")
    if not data.get("share_class"):
        errors.append("Share Class is required.")
    if not data.get("aksia_owner_id"):
        errors.append("Aksia Owner is required.")

    # Decline reason required when stage=declined
    if data.get("stage") == "declined" and not data.get("decline_reason"):
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

    return errors


def _create_next_steps_task(
    prospect_id: str, org_name: str, fund_ticker: str,
    owner_id: str, next_steps: str, next_steps_date: str,
    created_by: UUID,
) -> None:
    """Auto-generate a Task when next_steps_date is set."""
    sb = get_supabase()
    sb.table("tasks").insert({
        "title": f"Fund prospect next steps: {org_name} ({fund_ticker})",
        "due_date": next_steps_date,
        "assigned_to": owner_id,
        "status": "open",
        "notes": next_steps or "",
        "source": "fund_prospect_next_steps",
        "linked_record_type": "fund_prospect",
        "linked_record_id": prospect_id,
        "created_by": str(created_by),
    }).execute()


def _get_org_name(org_id: str) -> str:
    """Look up an org name by ID."""
    sb = get_supabase()
    resp = sb.table("organizations").select("company_name").eq("id", org_id).maybe_single().execute()
    return resp.data["company_name"] if resp.data else "Unknown"


def _get_user_name(user_id: str) -> str:
    """Look up a user display_name by ID."""
    sb = get_supabase()
    resp = sb.table("users").select("display_name").eq("id", user_id).maybe_single().execute()
    return resp.data["display_name"] if resp.data else "Unknown"


def _get_fund_info(fund_id: str) -> dict:
    """Look up fund details by ID."""
    sb = get_supabase()
    resp = (
        sb.table("funds")
        .select("id, fund_name, ticker, brand, asset_class")
        .eq("id", fund_id)
        .maybe_single()
        .execute()
    )
    return resp.data if resp.data else {"fund_name": "Unknown", "ticker": "?", "brand": "", "asset_class": ""}


def _load_form_context(sb, current_user, prospect=None, pre_org=None, errors=None):
    """Load all reference data and users needed for the fund prospect form."""
    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
    funds_resp = sb.table("funds").select("id, fund_name, ticker, brand").eq("is_active", True).order("ticker").execute()

    # Load leads for linked lead dropdown (scoped to org if available)
    leads_for_org = []
    org_id = None
    if prospect and isinstance(prospect, dict):
        org_id = prospect.get("organization_id")
    if not org_id and pre_org:
        org_id = pre_org.get("id") if isinstance(pre_org, dict) else None
    if org_id:
        leads_resp = (
            sb.table("leads")
            .select("id, summary, rating")
            .eq("organization_id", str(org_id))
            .eq("is_archived", False)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        leads_for_org = leads_resp.data or []

    return {
        "stages": _get_reference_data("fund_prospect_stage"),
        "decline_reasons": _get_reference_data("decline_reason"),
        "funds": funds_resp.data or [],
        "users": users_resp.data or [],
        "leads_for_org": leads_for_org,
        "prospect": prospect,
        "pre_org": pre_org,
        "errors": errors or [],
        "user": current_user,
    }


# ---------------------------------------------------------------------------
# ORG SEARCH (HTMX autocomplete) — GET /fund-prospects/search-orgs
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
# LEADS FOR ORG (HTMX dropdown refresh) — GET /fund-prospects/leads-for-org
# ---------------------------------------------------------------------------

@router.get("/leads-for-org", response_class=HTMLResponse)
async def leads_for_org(
    request: Request,
    org: str = Query(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX endpoint: return lead <option> elements for a given org."""
    html = '<option value="">— None —</option>'
    if not org:
        return HTMLResponse(html)

    sb = get_supabase()
    resp = (
        sb.table("leads")
        .select("id, summary, rating")
        .eq("organization_id", org)
        .eq("is_archived", False)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    leads = resp.data or []

    for lead in leads:
        summary = lead.get("summary") or "Untitled Lead"
        stage = (lead.get("rating") or "").replace("_", " ").title()
        html += f'<option value="{lead["id"]}">{summary} ({stage})</option>'

    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# LIST — GET /fund-prospects
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def list_fund_prospects(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=10, le=100),
    search: str = Query("", alias="q"),
    fund_id: str = Query("", alias="fund"),
    stage: str = Query("", alias="stage"),
    share_class: str = Query("", alias="share_class"),
    owner_id: str = Query("", alias="owner"),
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
):
    """List fund prospects with filtering, search, sorting, and pagination."""
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
        sb.table("fund_prospects")
        .select("id, organization_id, fund_id, share_class, stage, "
                "aksia_owner_id, target_allocation_mn, probability_pct, "
                "created_at", count="exact")
        .eq("is_archived", False)
    )

    # Search: match org name via IDs
    if search:
        if org_id_filter:
            query = query.in_("organization_id", org_id_filter)
        else:
            # No matching orgs — return empty
            query = query.eq("organization_id", "00000000-0000-0000-0000-000000000000")

    # Filters
    if fund_id:
        query = query.eq("fund_id", fund_id)
    if stage:
        query = query.eq("stage", stage)
    if share_class:
        query = query.eq("share_class", share_class)
    if owner_id:
        query = query.eq("aksia_owner_id", owner_id)
    if date_from:
        query = query.gte("created_at", date_from)
    if date_to:
        query = query.lte("created_at", date_to)

    # Sorting
    valid_sort_cols = ["created_at", "stage", "share_class", "target_allocation_mn", "probability_pct"]
    if sort_by not in valid_sort_cols:
        sort_by = "created_at"
    desc = sort_dir.lower() == "desc"
    query = query.order(sort_by, desc=desc)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    resp = query.execute()
    prospects = resp.data or []
    total_count = resp.count or 0
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    # Load all funds into a dict for O(1) enrichment
    funds_resp = sb.table("funds").select("id, fund_name, ticker, brand").execute()
    funds_dict = {f["id"]: f for f in (funds_resp.data or [])}

    # Enrich each prospect
    for fp in prospects:
        if fp.get("organization_id"):
            fp["org_name"] = _get_org_name(str(fp["organization_id"]))
        else:
            fp["org_name"] = "—"

        if fp.get("aksia_owner_id"):
            fp["owner_name"] = _get_user_name(str(fp["aksia_owner_id"]))
        else:
            fp["owner_name"] = "—"

        fund = funds_dict.get(fp.get("fund_id"), {})
        fp["fund_ticker"] = fund.get("ticker", "?")
        fp["fund_name"] = fund.get("fund_name", "Unknown")

    # Reference data for filter dropdowns and stage labels
    stages = _get_reference_data("fund_prospect_stage")
    stage_labels = {s["value"]: s["label"] for s in stages}
    funds_list = [{"id": f["id"], "fund_name": f["fund_name"], "ticker": f["ticker"], "brand": f["brand"]}
                  for f in (funds_resp.data or [])]
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
        "prospects": prospects,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "search": search,
        "fund_id": fund_id,
        "stage": stage,
        "share_class": share_class,
        "owner_id": owner_id,
        "date_from": date_from,
        "date_to": date_to,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "stages": stages,
        "stage_labels": stage_labels,
        "funds": funds_list,
        "users": users_resp.data or [],
        "view_mode": "all_fund_prospects",
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("fund_prospects/_list_table.html", context)
    return templates.TemplateResponse("fund_prospects/list.html", context)


# ---------------------------------------------------------------------------
# MY FUND PROSPECTS — GET /fund-prospects/my-fund-prospects
# ---------------------------------------------------------------------------

@router.get("/my-fund-prospects", response_class=HTMLResponse)
async def my_fund_prospects(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=10, le=100),
    search: str = Query("", alias="q"),
    fund_id: str = Query("", alias="fund"),
    stage: str = Query("", alias="stage"),
    share_class: str = Query("", alias="share_class"),
    owner_id: str = Query("", alias="owner"),
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
):
    """List fund prospects where the current user is the Aksia owner."""
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
        sb.table("fund_prospects")
        .select("id, organization_id, fund_id, share_class, stage, "
                "aksia_owner_id, target_allocation_mn, probability_pct, "
                "created_at", count="exact")
        .eq("is_archived", False)
        .eq("aksia_owner_id", str(current_user.id))
    )

    # Search: match org name via IDs
    if search:
        if org_id_filter:
            query = query.in_("organization_id", org_id_filter)
        else:
            # No matching orgs — return empty
            query = query.eq("organization_id", "00000000-0000-0000-0000-000000000000")

    # Filters
    if fund_id:
        query = query.eq("fund_id", fund_id)
    if stage:
        query = query.eq("stage", stage)
    if share_class:
        query = query.eq("share_class", share_class)
    if owner_id:
        query = query.eq("aksia_owner_id", owner_id)
    if date_from:
        query = query.gte("created_at", date_from)
    if date_to:
        query = query.lte("created_at", date_to)

    # Sorting
    valid_sort_cols = ["created_at", "stage", "share_class", "target_allocation_mn", "probability_pct"]
    if sort_by not in valid_sort_cols:
        sort_by = "created_at"
    desc = sort_dir.lower() == "desc"
    query = query.order(sort_by, desc=desc)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    resp = query.execute()
    prospects = resp.data or []
    total_count = resp.count or 0
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    # Load all funds into a dict for O(1) enrichment
    funds_resp = sb.table("funds").select("id, fund_name, ticker, brand").execute()
    funds_dict = {f["id"]: f for f in (funds_resp.data or [])}

    # Enrich each prospect
    for fp in prospects:
        if fp.get("organization_id"):
            fp["org_name"] = _get_org_name(str(fp["organization_id"]))
        else:
            fp["org_name"] = "—"

        if fp.get("aksia_owner_id"):
            fp["owner_name"] = _get_user_name(str(fp["aksia_owner_id"]))
        else:
            fp["owner_name"] = "—"

        fund = funds_dict.get(fp.get("fund_id"), {})
        fp["fund_ticker"] = fund.get("ticker", "?")
        fp["fund_name"] = fund.get("fund_name", "Unknown")

    # Reference data for filter dropdowns and stage labels
    stages = _get_reference_data("fund_prospect_stage")
    stage_labels = {s["value"]: s["label"] for s in stages}
    funds_list = [{"id": f["id"], "fund_name": f["fund_name"], "ticker": f["ticker"], "brand": f["brand"]}
                  for f in (funds_resp.data or [])]
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
        "prospects": prospects,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "search": search,
        "fund_id": fund_id,
        "stage": stage,
        "share_class": share_class,
        "owner_id": owner_id,
        "date_from": date_from,
        "date_to": date_to,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "stages": stages,
        "stage_labels": stage_labels,
        "funds": funds_list,
        "users": users_resp.data or [],
        "view_mode": "my_fund_prospects",
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("fund_prospects/_list_table.html", context)
    return templates.TemplateResponse("fund_prospects/list.html", context)


# ---------------------------------------------------------------------------
# CREATE FORM — GET /fund-prospects/new  (must be before /{prospect_id})
# ---------------------------------------------------------------------------

@router.get("/new", response_class=HTMLResponse)
async def new_prospect_form(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    org_id: str = Query("", alias="org"),
    fund_id_param: str = Query("", alias="fund"),
):
    """Render the new fund prospect form. Optionally pre-fill org/fund."""
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
            .maybe_single()
            .execute()
        )
        if org_resp.data:
            pre_org = org_resp.data

    # Pre-fill fund if provided
    pre_prospect = None
    if fund_id_param:
        pre_prospect = {"fund_id": fund_id_param}

    context = _load_form_context(sb, current_user, prospect=pre_prospect, pre_org=pre_org)
    context["request"] = request
    return templates.TemplateResponse("fund_prospects/form.html", context)


# ---------------------------------------------------------------------------
# DETAIL — GET /fund-prospects/{prospect_id}
# ---------------------------------------------------------------------------

@router.get("/{prospect_id}", response_class=HTMLResponse)
async def get_prospect(
    request: Request,
    prospect_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Fund prospect detail page."""
    sb = get_supabase()

    resp = (
        sb.table("fund_prospects")
        .select("*")
        .eq("id", str(prospect_id))
        .eq("is_archived", False)
        .maybe_single()
        .execute()
    )
    prospect = resp.data
    if not prospect:
        raise HTTPException(status_code=404, detail="Fund prospect not found")

    # Enrich: org name
    org_name = _get_org_name(str(prospect["organization_id"])) if prospect.get("organization_id") else "—"

    # Enrich: owner name
    owner_name = _get_user_name(str(prospect["aksia_owner_id"])) if prospect.get("aksia_owner_id") else "—"

    # Enrich: fund info
    fund_info = _get_fund_info(str(prospect["fund_id"])) if prospect.get("fund_id") else {}

    # Linked lead (if any)
    linked_lead = None
    if prospect.get("linked_lead_id"):
        lead_resp = (
            sb.table("leads")
            .select("id, summary, rating, organization_id")
            .eq("id", str(prospect["linked_lead_id"]))
            .eq("is_archived", False)
            .limit(1)
            .execute()
        )
        if lead_resp.data:
            linked_lead = lead_resp.data[0]

    # Related tasks
    tasks_resp = (
        sb.table("tasks")
        .select("id, title, due_date, status, assigned_to")
        .eq("linked_record_type", "fund_prospect")
        .eq("linked_record_id", str(prospect_id))
        .eq("is_archived", False)
        .order("created_at", desc=True)
        .execute()
    )
    related_tasks = tasks_resp.data or []

    # Reference data for labels
    stages = _get_reference_data("fund_prospect_stage")
    stage_labels = {s["value"]: s["label"] for s in stages}

    decline_reasons = _get_reference_data("decline_reason")
    decline_labels = {d["value"]: d["label"] for d in decline_reasons}

    context = {
        "request": request,
        "user": current_user,
        "prospect": prospect,
        "org_name": org_name,
        "owner_name": owner_name,
        "fund_info": fund_info,
        "linked_lead": linked_lead,
        "related_tasks": related_tasks,
        "stage_labels": stage_labels,
        "decline_labels": decline_labels,
        "stage_order": STAGE_ORDER,
    }
    return templates.TemplateResponse("fund_prospects/detail.html", context)


# ---------------------------------------------------------------------------
# CREATE — POST /fund-prospects
# ---------------------------------------------------------------------------

@router.post("/", response_class=HTMLResponse)
async def create_prospect(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new fund prospect."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    form = await request.form()
    prospect_data = _build_prospect_data_from_form(form)

    # Validate
    errors = _validate_prospect_fields(prospect_data)

    if errors:
        sb = get_supabase()
        pre_org = None
        if prospect_data.get("organization_id"):
            org_resp = (
                sb.table("organizations")
                .select("id, company_name")
                .eq("id", prospect_data["organization_id"])
                .maybe_single()
                .execute()
            )
            if org_resp.data:
                pre_org = org_resp.data

        context = _load_form_context(
            sb, current_user, prospect=prospect_data, pre_org=pre_org, errors=errors
        )
        context["request"] = request
        return templates.TemplateResponse("fund_prospects/form.html", context)

    # Set system fields
    prospect_data["created_by"] = str(current_user.id)
    prospect_data["stage_entry_date"] = str(date_type.today())

    sb = get_supabase()
    resp = sb.table("fund_prospects").insert(prospect_data).execute()

    if resp.data:
        new_prospect = resp.data[0]
        prospect_id = new_prospect["id"]

        # Audit log
        _log_field_change("fund_prospect", str(prospect_id), "_created", None, "record created", current_user.id)

        # Next steps task auto-generation
        if new_prospect.get("next_steps_date"):
            org_name = _get_org_name(str(new_prospect["organization_id"])) if new_prospect.get("organization_id") else "Prospect"
            fund_info = _get_fund_info(str(new_prospect["fund_id"])) if new_prospect.get("fund_id") else {}
            _create_next_steps_task(
                str(prospect_id), org_name, fund_info.get("ticker", "?"),
                str(new_prospect["aksia_owner_id"]),
                new_prospect.get("next_steps"), new_prospect["next_steps_date"],
                current_user.id,
            )

        return RedirectResponse(url=f"/fund-prospects/{prospect_id}", status_code=303)

    raise HTTPException(status_code=500, detail="Failed to create fund prospect")


# ---------------------------------------------------------------------------
# EDIT FORM — GET /fund-prospects/{prospect_id}/edit
# ---------------------------------------------------------------------------

@router.get("/{prospect_id}/edit", response_class=HTMLResponse)
async def edit_prospect_form(
    request: Request,
    prospect_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the edit fund prospect form."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()
    resp = (
        sb.table("fund_prospects")
        .select("*")
        .eq("id", str(prospect_id))
        .eq("is_archived", False)
        .maybe_single()
        .execute()
    )
    prospect = resp.data
    if not prospect:
        raise HTTPException(status_code=404, detail="Fund prospect not found")

    # Load linked org for pre-fill
    pre_org = None
    if prospect.get("organization_id"):
        org_resp = (
            sb.table("organizations")
            .select("id, company_name")
            .eq("id", str(prospect["organization_id"]))
            .maybe_single()
            .execute()
        )
        if org_resp.data:
            pre_org = org_resp.data

    context = _load_form_context(sb, current_user, prospect=prospect, pre_org=pre_org)
    context["request"] = request
    return templates.TemplateResponse("fund_prospects/form.html", context)


# ---------------------------------------------------------------------------
# UPDATE — POST /fund-prospects/{prospect_id}
# ---------------------------------------------------------------------------

@router.post("/{prospect_id}", response_class=HTMLResponse)
async def update_prospect(
    request: Request,
    prospect_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an existing fund prospect."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()

    old_resp = (
        sb.table("fund_prospects")
        .select("*")
        .eq("id", str(prospect_id))
        .eq("is_archived", False)
        .maybe_single()
        .execute()
    )
    old_prospect = old_resp.data
    if not old_prospect:
        raise HTTPException(status_code=404, detail="Fund prospect not found")

    form = await request.form()
    prospect_data = _build_prospect_data_from_form(form)

    # Validate
    errors = _validate_prospect_fields(prospect_data)

    if errors:
        pre_org = None
        if prospect_data.get("organization_id"):
            org_resp = (
                sb.table("organizations")
                .select("id, company_name")
                .eq("id", prospect_data["organization_id"])
                .maybe_single()
                .execute()
            )
            if org_resp.data:
                pre_org = org_resp.data

        merged = {**old_prospect, **prospect_data}
        context = _load_form_context(
            sb, current_user, prospect=merged, pre_org=pre_org, errors=errors
        )
        context["request"] = request
        return templates.TemplateResponse("fund_prospects/form.html", context)

    # Stage change detection — auto-set stage_entry_date
    old_stage = old_prospect.get("stage")
    new_stage = prospect_data.get("stage")
    if old_stage != new_stage:
        prospect_data["stage_entry_date"] = str(date_type.today())

    # Audit log every changed field
    _audit_changes(str(prospect_id), old_prospect, prospect_data, current_user.id)

    # Update
    sb.table("fund_prospects").update(prospect_data).eq("id", str(prospect_id)).execute()

    # Next steps task: if next_steps_date changed and is now set
    old_nsd = old_prospect.get("next_steps_date")
    new_nsd = prospect_data.get("next_steps_date")
    if new_nsd and str(old_nsd) != str(new_nsd):
        updated = {**old_prospect, **prospect_data, "id": str(prospect_id)}
        org_name = _get_org_name(str(updated["organization_id"])) if updated.get("organization_id") else "Prospect"
        fund_info = _get_fund_info(str(updated["fund_id"])) if updated.get("fund_id") else {}
        _create_next_steps_task(
            str(prospect_id), org_name, fund_info.get("ticker", "?"),
            str(updated["aksia_owner_id"]),
            updated.get("next_steps"), new_nsd,
            current_user.id,
        )

    return RedirectResponse(url=f"/fund-prospects/{prospect_id}", status_code=303)


# ---------------------------------------------------------------------------
# ARCHIVE (soft delete) — POST /fund-prospects/{prospect_id}/archive
# ---------------------------------------------------------------------------

@router.post("/{prospect_id}/archive", response_class=HTMLResponse)
async def archive_prospect(
    request: Request,
    prospect_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-delete a fund prospect."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    sb.table("fund_prospects").update({"is_archived": True}).eq("id", str(prospect_id)).execute()
    _log_field_change("fund_prospect", str(prospect_id), "is_archived", False, True, current_user.id)

    if request.headers.get("HX-Request"):
        return HTMLResponse('<p class="text-sm text-green-600">Fund prospect archived.</p>')
    return RedirectResponse(url="/fund-prospects", status_code=303)

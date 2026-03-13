"""Contracts router — full CRUD for Contracts (Legal-only edit) and
Fee Arrangements (standard-user accessible, org-level)."""

from datetime import date as date_type
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from dependencies import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/contracts", tags=["contracts"])
templates = Jinja2Templates(directory="templates")


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
    record_type: str,
    record_id: str,
    old_record: dict,
    new_data: dict,
    changed_by: UUID,
) -> None:
    """Compare old record with new data and log every changed field."""
    for field, new_val in new_data.items():
        old_val = old_record.get(field)
        if str(old_val) != str(new_val) and not (old_val is None and new_val is None):
            _log_field_change(record_type, record_id, field, old_val, new_val, changed_by)


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


# ===========================================================================
#  FEE ARRANGEMENTS — defined BEFORE /{contract_id} routes to avoid
#  FastAPI parsing "fee-arrangements" as a UUID.
# ===========================================================================

# ---------------------------------------------------------------------------
# FEE ARRANGEMENT — NEW FORM (HTMX partial) — GET /contracts/fee-arrangements/new
# ---------------------------------------------------------------------------

@router.get("/fee-arrangements/new", response_class=HTMLResponse)
async def new_fee_arrangement_form(
    request: Request,
    org: str = Query(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the new fee arrangement form (HTMX partial for org detail page)."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    if not org:
        raise HTTPException(status_code=400, detail="Organization ID required")

    context = {
        "request": request,
        "user": current_user,
        "fa": None,
        "org_id": org,
        "frequencies": _get_reference_data("fee_frequency"),
        "fee_statuses": _get_reference_data("fee_status"),
        "errors": [],
    }
    return templates.TemplateResponse("organizations/_fee_arrangement_form.html", context)


# ---------------------------------------------------------------------------
# FEE ARRANGEMENT — CREATE — POST /contracts/fee-arrangements/
# ---------------------------------------------------------------------------

@router.post("/fee-arrangements/", response_class=HTMLResponse)
async def create_fee_arrangement(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new fee arrangement."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    form = await request.form()
    org_id = (form.get("organization_id") or "").strip()

    if not org_id:
        raise HTTPException(status_code=400, detail="Organization ID required")

    # Extract form data
    fa_data = {
        "organization_id": org_id,
        "arrangement_name": (form.get("arrangement_name") or "").strip(),
        "annual_value": form.get("annual_value") or 0,
        "frequency": (form.get("frequency") or "").strip(),
        "status": (form.get("status") or "active").strip(),
        "start_date": (form.get("start_date") or "").strip() or None,
        "end_date": (form.get("end_date") or "").strip() or None,
        "notes": (form.get("notes") or "").strip() or None,
        "created_by": str(current_user.id),
    }

    # Validate required fields
    errors = []
    if not fa_data["arrangement_name"]:
        errors.append("Arrangement Name is required.")
    if not fa_data["frequency"]:
        errors.append("Frequency is required.")
    if not fa_data["start_date"]:
        errors.append("Start Date is required.")
    if fa_data["status"] == "inactive" and not fa_data["end_date"]:
        errors.append("End Date is required when status is Inactive.")

    if errors:
        context = {
            "request": request,
            "user": current_user,
            "fa": fa_data,
            "org_id": org_id,
            "frequencies": _get_reference_data("fee_frequency"),
            "fee_statuses": _get_reference_data("fee_status"),
            "errors": errors,
        }
        return templates.TemplateResponse("organizations/_fee_arrangement_form.html", context)

    sb = get_supabase()
    resp = sb.table("fee_arrangements").insert(fa_data).execute()

    if resp.data:
        fa_id = resp.data[0]["id"]
        _log_field_change("fee_arrangement", str(fa_id), "_created", None, "record created", current_user.id)

    response = HTMLResponse("")
    response.headers["HX-Redirect"] = f"/organizations/{org_id}?tab=fee_arrangements"
    return response


# ---------------------------------------------------------------------------
# FEE ARRANGEMENT — EDIT FORM (HTMX partial) — GET /contracts/fee-arrangements/{fa_id}/edit
# ---------------------------------------------------------------------------

@router.get("/fee-arrangements/{fa_id}/edit", response_class=HTMLResponse)
async def edit_fee_arrangement_form(
    request: Request,
    fa_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the edit fee arrangement form (HTMX partial)."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()
    resp = (
        sb.table("fee_arrangements")
        .select("*")
        .eq("id", str(fa_id))
        .eq("is_archived", False)
        .single()
        .execute()
    )
    fa = resp.data
    if not fa:
        raise HTTPException(status_code=404, detail="Fee arrangement not found")

    context = {
        "request": request,
        "user": current_user,
        "fa": fa,
        "org_id": str(fa["organization_id"]),
        "frequencies": _get_reference_data("fee_frequency"),
        "fee_statuses": _get_reference_data("fee_status"),
        "errors": [],
    }
    return templates.TemplateResponse("organizations/_fee_arrangement_form.html", context)


# ---------------------------------------------------------------------------
# FEE ARRANGEMENT — UPDATE — POST /contracts/fee-arrangements/{fa_id}
# ---------------------------------------------------------------------------

@router.post("/fee-arrangements/{fa_id}", response_class=HTMLResponse)
async def update_fee_arrangement(
    request: Request,
    fa_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an existing fee arrangement."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()
    old_resp = (
        sb.table("fee_arrangements")
        .select("*")
        .eq("id", str(fa_id))
        .eq("is_archived", False)
        .single()
        .execute()
    )
    old_fa = old_resp.data
    if not old_fa:
        raise HTTPException(status_code=404, detail="Fee arrangement not found")

    form = await request.form()
    org_id = str(old_fa["organization_id"])

    update_data = {
        "arrangement_name": (form.get("arrangement_name") or "").strip(),
        "annual_value": form.get("annual_value") or 0,
        "frequency": (form.get("frequency") or "").strip(),
        "status": (form.get("status") or "active").strip(),
        "start_date": (form.get("start_date") or "").strip() or None,
        "end_date": (form.get("end_date") or "").strip() or None,
        "notes": (form.get("notes") or "").strip() or None,
    }

    # Validate
    errors = []
    if not update_data["arrangement_name"]:
        errors.append("Arrangement Name is required.")
    if not update_data["frequency"]:
        errors.append("Frequency is required.")
    if not update_data["start_date"]:
        errors.append("Start Date is required.")
    if update_data["status"] == "inactive" and not update_data["end_date"]:
        errors.append("End Date is required when status is Inactive.")

    if errors:
        context = {
            "request": request,
            "user": current_user,
            "fa": {**old_fa, **update_data},
            "org_id": org_id,
            "frequencies": _get_reference_data("fee_frequency"),
            "fee_statuses": _get_reference_data("fee_status"),
            "errors": errors,
        }
        return templates.TemplateResponse("organizations/_fee_arrangement_form.html", context)

    # Audit log changes
    _audit_changes("fee_arrangement", str(fa_id), old_fa, update_data, current_user.id)

    # Update
    sb.table("fee_arrangements").update(update_data).eq("id", str(fa_id)).execute()

    response = HTMLResponse("")
    response.headers["HX-Redirect"] = f"/organizations/{org_id}?tab=fee_arrangements"
    return response


# ---------------------------------------------------------------------------
# FEE ARRANGEMENT — ARCHIVE — POST /contracts/fee-arrangements/{fa_id}/archive
# ---------------------------------------------------------------------------

@router.post("/fee-arrangements/{fa_id}/archive", response_class=HTMLResponse)
async def archive_fee_arrangement(
    request: Request,
    fa_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-delete a fee arrangement."""
    require_role(current_user, ["admin"])

    sb = get_supabase()

    # Get org_id for redirect
    fa_resp = (
        sb.table("fee_arrangements")
        .select("organization_id")
        .eq("id", str(fa_id))
        .single()
        .execute()
    )
    org_id = fa_resp.data["organization_id"] if fa_resp.data else ""

    sb.table("fee_arrangements").update({"is_archived": True}).eq("id", str(fa_id)).execute()
    _log_field_change("fee_arrangement", str(fa_id), "is_archived", False, True, current_user.id)

    response = HTMLResponse("")
    response.headers["HX-Redirect"] = f"/organizations/{org_id}?tab=fee_arrangements"
    return response


# ===========================================================================
#  CONTRACTS
# ===========================================================================

# ---------------------------------------------------------------------------
# LIST — GET /contracts
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def list_contracts(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=10, le=100),
    search: str = Query("", alias="q"),
    service_type: str = Query("", alias="service"),
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    sort_by: str = Query("start_date"),
    sort_dir: str = Query("desc"),
):
    """List contracts with filtering, search, sorting, and pagination."""
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
        sb.table("contracts")
        .select("id, organization_id, originating_lead_id, start_date, service_type, "
                "asset_classes, client_coverage, actual_revenue, created_at", count="exact")
        .eq("is_archived", False)
    )

    # Search: match org name (via IDs)
    if search:
        if org_id_filter:
            query = query.in_("organization_id", org_id_filter)
        else:
            # No matching orgs — return empty
            query = query.eq("id", "00000000-0000-0000-0000-000000000000")

    # Filters
    if service_type:
        query = query.eq("service_type", service_type)
    if date_from:
        query = query.gte("start_date", date_from)
    if date_to:
        query = query.lte("start_date", date_to)

    # Sorting
    valid_sort_cols = ["start_date", "actual_revenue", "service_type", "created_at"]
    if sort_by not in valid_sort_cols:
        sort_by = "start_date"
    desc = sort_dir.lower() == "desc"
    query = query.order(sort_by, desc=desc)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    resp = query.execute()
    contracts = resp.data or []
    total_count = resp.count or 0
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    # Enrich with org name
    for c in contracts:
        if c.get("organization_id"):
            c["org_name"] = _get_org_name(str(c["organization_id"]))
        else:
            c["org_name"] = "—"

    # Reference data for filter dropdowns
    service_types = _get_reference_data("service_type")

    context = {
        "request": request,
        "user": current_user,
        "contracts": contracts,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "search": search,
        "service_type": service_type,
        "date_from": date_from,
        "date_to": date_to,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "service_types": service_types,
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("contracts/_list_table.html", context)
    return templates.TemplateResponse("contracts/list.html", context)


# ---------------------------------------------------------------------------
# DETAIL — GET /contracts/{contract_id}
# ---------------------------------------------------------------------------

@router.get("/{contract_id}", response_class=HTMLResponse)
async def get_contract(
    request: Request,
    contract_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Contract detail page."""
    sb = get_supabase()

    resp = (
        sb.table("contracts")
        .select("*")
        .eq("id", str(contract_id))
        .eq("is_archived", False)
        .single()
        .execute()
    )
    contract = resp.data
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Org name
    org_name = _get_org_name(str(contract["organization_id"])) if contract.get("organization_id") else "—"

    # Originating lead info
    lead_info = None
    if contract.get("originating_lead_id"):
        lead_resp = (
            sb.table("leads")
            .select("id, rating, summary, relationship")
            .eq("id", str(contract["originating_lead_id"]))
            .single()
            .execute()
        )
        lead_info = lead_resp.data

    # Lead stage labels
    lead_stages = _get_reference_data("lead_stage")
    stage_labels = {s["value"]: s["label"] for s in lead_stages}

    # Asset class labels
    asset_class_data = _get_reference_data("asset_class")
    ac_labels = {a["value"]: a["label"] for a in asset_class_data}

    # Service type labels
    service_type_data = _get_reference_data("service_type")
    st_labels = {s["value"]: s["label"] for s in service_type_data}

    # Audit history
    audit_resp = (
        sb.table("audit_log")
        .select("field_name, old_value, new_value, changed_by, changed_at")
        .eq("record_type", "contract")
        .eq("record_id", str(contract_id))
        .order("changed_at", desc=True)
        .limit(50)
        .execute()
    )
    audit_entries = audit_resp.data or []

    # Enrich audit entries with user names
    for entry in audit_entries:
        if entry.get("changed_by"):
            entry["changed_by_name"] = _get_user_name(str(entry["changed_by"]))
        else:
            entry["changed_by_name"] = "System"

    context = {
        "request": request,
        "user": current_user,
        "contract": contract,
        "org_name": org_name,
        "lead_info": lead_info,
        "stage_labels": stage_labels,
        "ac_labels": ac_labels,
        "st_labels": st_labels,
        "audit_entries": audit_entries,
    }
    return templates.TemplateResponse("contracts/detail.html", context)


# ---------------------------------------------------------------------------
# EDIT FORM — GET /contracts/{contract_id}/edit
# ---------------------------------------------------------------------------

@router.get("/{contract_id}/edit", response_class=HTMLResponse)
async def edit_contract_form(
    request: Request,
    contract_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the contract edit form (Legal / Admin only)."""
    require_role(current_user, ["admin", "legal"])

    sb = get_supabase()
    resp = (
        sb.table("contracts")
        .select("*")
        .eq("id", str(contract_id))
        .eq("is_archived", False)
        .single()
        .execute()
    )
    contract = resp.data
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Org name for read-only display
    org_name = _get_org_name(str(contract["organization_id"])) if contract.get("organization_id") else "—"

    # Originating lead summary for read-only display
    lead_summary = None
    if contract.get("originating_lead_id"):
        lead_resp = (
            sb.table("leads")
            .select("id, summary, rating")
            .eq("id", str(contract["originating_lead_id"]))
            .single()
            .execute()
        )
        lead_summary = lead_resp.data

    context = {
        "request": request,
        "user": current_user,
        "contract": contract,
        "org_name": org_name,
        "lead_summary": lead_summary,
        "service_types": _get_reference_data("service_type"),
        "asset_classes": _get_reference_data("asset_class"),
        "errors": [],
    }
    return templates.TemplateResponse("contracts/form.html", context)


# ---------------------------------------------------------------------------
# UPDATE — POST /contracts/{contract_id}
# ---------------------------------------------------------------------------

@router.post("/{contract_id}", response_class=HTMLResponse)
async def update_contract(
    request: Request,
    contract_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a contract (Legal / Admin only)."""
    require_role(current_user, ["admin", "legal"])

    sb = get_supabase()

    old_resp = (
        sb.table("contracts")
        .select("*")
        .eq("id", str(contract_id))
        .eq("is_archived", False)
        .single()
        .execute()
    )
    old_contract = old_resp.data
    if not old_contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    form = await request.form()

    # Only extract editable fields — organization_id and originating_lead_id are read-only
    update_data = {
        "start_date": (form.get("start_date") or "").strip() or None,
        "service_type": (form.get("service_type") or "").strip(),
        "asset_classes": form.getlist("asset_classes"),
        "client_coverage": (form.get("client_coverage") or "").strip() or None,
        "summary": (form.get("summary") or "").strip() or None,
        "actual_revenue": form.get("actual_revenue") or 0,
        "inflation_provision": (form.get("inflation_provision") or "").strip() or None,
        "escalator_clause": (form.get("escalator_clause") or "").strip() or None,
    }

    # Validate required fields
    errors = []
    if not update_data["start_date"]:
        errors.append("Start Date is required.")
    if not update_data["service_type"]:
        errors.append("Service Type is required.")
    if not update_data["asset_classes"]:
        errors.append("At least one Asset Class is required.")
    try:
        float(update_data["actual_revenue"])
    except (TypeError, ValueError):
        errors.append("Actual Revenue must be a valid number.")

    if errors:
        org_name = _get_org_name(str(old_contract["organization_id"]))
        lead_summary = None
        if old_contract.get("originating_lead_id"):
            lead_resp = (
                sb.table("leads")
                .select("id, summary, rating")
                .eq("id", str(old_contract["originating_lead_id"]))
                .single()
                .execute()
            )
            lead_summary = lead_resp.data

        context = {
            "request": request,
            "user": current_user,
            "contract": {**old_contract, **update_data},
            "org_name": org_name,
            "lead_summary": lead_summary,
            "service_types": _get_reference_data("service_type"),
            "asset_classes": _get_reference_data("asset_class"),
            "errors": errors,
        }
        return templates.TemplateResponse("contracts/form.html", context)

    # Audit log changes
    _audit_changes("contract", str(contract_id), old_contract, update_data, current_user.id)

    # Update
    sb.table("contracts").update(update_data).eq("id", str(contract_id)).execute()

    return RedirectResponse(url=f"/contracts/{contract_id}", status_code=303)


# ---------------------------------------------------------------------------
# ARCHIVE (soft delete) — POST /contracts/{contract_id}/archive
# ---------------------------------------------------------------------------

@router.post("/{contract_id}/archive", response_class=HTMLResponse)
async def archive_contract(
    request: Request,
    contract_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-delete a contract (Admin only)."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    sb.table("contracts").update({"is_archived": True}).eq("id", str(contract_id)).execute()
    _log_field_change("contract", str(contract_id), "is_archived", False, True, current_user.id)

    if request.headers.get("HX-Request"):
        return HTMLResponse('<p class="text-sm text-green-600">Contract archived.</p>')
    return RedirectResponse(url="/contracts", status_code=303)

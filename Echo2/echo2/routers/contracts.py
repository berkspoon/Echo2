"""Contracts router — full CRUD for Contracts (Legal-only edit) and
Fee Arrangements (standard-user accessible, org-level)."""

from datetime import date as date_type
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from db.helpers import get_reference_data, log_field_change, audit_changes, get_org_name, get_user_name
from db.field_service import get_field_definitions, enrich_field_definitions
from services.form_service import build_form_context, parse_form_data, validate_form_data, get_users_for_lookup
from dependencies import CurrentUser, get_current_user, require_role
from services.grid_service import build_grid_context

router = APIRouter(prefix="/contracts", tags=["contracts"])
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        "frequencies": get_reference_data("fee_frequency"),
        "fee_statuses": get_reference_data("fee_status"),
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
            "frequencies": get_reference_data("fee_frequency"),
            "fee_statuses": get_reference_data("fee_status"),
            "errors": errors,
        }
        return templates.TemplateResponse("organizations/_fee_arrangement_form.html", context)

    sb = get_supabase()
    resp = sb.table("fee_arrangements").insert(fa_data).execute()

    if resp.data:
        fa_id = resp.data[0]["id"]
        log_field_change("fee_arrangement", str(fa_id), "_created", None, "record created", current_user.id)

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
        .eq("is_deleted", False)
        .maybe_single()
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
        "frequencies": get_reference_data("fee_frequency"),
        "fee_statuses": get_reference_data("fee_status"),
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
        .eq("is_deleted", False)
        .maybe_single()
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
            "frequencies": get_reference_data("fee_frequency"),
            "fee_statuses": get_reference_data("fee_status"),
            "errors": errors,
        }
        return templates.TemplateResponse("organizations/_fee_arrangement_form.html", context)

    # Audit log changes
    audit_changes("fee_arrangement", str(fa_id), old_fa, update_data, current_user.id)

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
        .maybe_single()
        .execute()
    )
    org_id = fa_resp.data["organization_id"] if fa_resp.data else ""

    sb.table("fee_arrangements").update({"is_deleted": True}).eq("id", str(fa_id)).execute()
    log_field_change("fee_arrangement", str(fa_id), "is_deleted", False, True, current_user.id)

    response = HTMLResponse("")
    response.headers["HX-Redirect"] = f"/organizations/{org_id}?tab=fee_arrangements"
    return response


# ===========================================================================
#  CONTRACTS
# ===========================================================================

# ---------------------------------------------------------------------------
# NEW CONTRACT FORM — GET /contracts/new
# ---------------------------------------------------------------------------

@router.get("/new", response_class=HTMLResponse)
async def new_contract_form(
    request: Request,
    lead_id: UUID = Query(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the contract creation form, pre-filled from a won lead."""
    require_role(current_user, ["admin", "legal"])

    sb = get_supabase()

    # Load the originating lead
    lead_resp = (
        sb.table("leads")
        .select("*")
        .eq("id", str(lead_id))
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    lead = lead_resp.data
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Check lead is in a Won stage
    rating = lead.get("rating", "")
    lead_type = lead.get("lead_type", "advisory")
    won_stages = {"won"} if lead_type == "advisory" else {"closed"}
    if rating not in won_stages:
        raise HTTPException(status_code=400, detail="Lead must be in a Won/Closed stage to create a contract")

    # Check no existing contract for this lead
    existing_resp = (
        sb.table("contracts")
        .select("id")
        .eq("originating_lead_id", str(lead_id))
        .eq("is_deleted", False)
        .limit(1)
        .execute()
    )
    if existing_resp.data:
        raise HTTPException(status_code=400, detail="A contract already exists for this lead")

    # Org name
    org_name = get_org_name(str(lead["organization_id"])) if lead.get("organization_id") else "—"

    # Pre-fill contract fields from the lead
    contract = {
        "id": None,
        "organization_id": lead.get("organization_id"),
        "originating_lead_id": str(lead_id),
        "start_date": str(date_type.today()),
        "service_type": lead.get("service_type") or "",
        "asset_classes": lead.get("asset_classes") or [],
        "actual_revenue": lead.get("expected_revenue"),
        "client_coverage": lead.get("potential_coverage") or "",
        "summary": lead.get("summary") or "",
        "inflation_provision": "",
        "escalator_clause": "",
    }

    lead_summary = {
        "id": str(lead_id),
        "summary": lead.get("summary"),
        "rating": lead.get("rating"),
    }

    context = {
        "request": request,
        "user": current_user,
        "contract": contract,
        "org_name": org_name,
        "lead_summary": lead_summary,
        "mode": "create",
        "lead_id": str(lead_id),
        "service_types": get_reference_data("service_type"),
        "asset_classes": get_reference_data("asset_class"),
        "errors": [],
    }
    return templates.TemplateResponse("contracts/form.html", context)


# ---------------------------------------------------------------------------
# CREATE — POST /contracts/create
# ---------------------------------------------------------------------------

@router.post("/create", response_class=HTMLResponse)
async def create_contract(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new contract from a won lead."""
    require_role(current_user, ["admin", "legal"])

    form = await request.form()
    lead_id = (form.get("lead_id") or "").strip()

    if not lead_id:
        raise HTTPException(status_code=400, detail="Lead ID is required")

    sb = get_supabase()

    # Load and validate the lead
    lead_resp = (
        sb.table("leads")
        .select("*")
        .eq("id", lead_id)
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    lead = lead_resp.data
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    rating = lead.get("rating", "")
    lead_type = lead.get("lead_type", "advisory")
    won_stages = {"won"} if lead_type == "advisory" else {"closed"}
    if rating not in won_stages:
        raise HTTPException(status_code=400, detail="Lead must be in a Won/Closed stage to create a contract")

    # Check no existing contract
    existing_resp = (
        sb.table("contracts")
        .select("id")
        .eq("originating_lead_id", lead_id)
        .eq("is_deleted", False)
        .limit(1)
        .execute()
    )
    if existing_resp.data:
        raise HTTPException(status_code=400, detail="A contract already exists for this lead")

    # Parse form data
    raw_acs = form.getlist("asset_classes")
    contract_data = {
        "organization_id": str(lead["organization_id"]),
        "originating_lead_id": lead_id,
        "start_date": (form.get("start_date") or "").strip() or str(date_type.today()),
        "service_type": (form.get("service_type") or "").strip(),
        "asset_classes": [a for a in raw_acs if a],
        "actual_revenue": float(form.get("actual_revenue") or 0),
        "client_coverage": (form.get("client_coverage") or "").strip() or None,
        "summary": (form.get("summary") or "").strip() or None,
        "inflation_provision": (form.get("inflation_provision") or "").strip() or None,
        "escalator_clause": (form.get("escalator_clause") or "").strip() or None,
        "created_by": str(current_user.id),
    }

    # Validate required fields
    errors = []
    if not contract_data["start_date"]:
        errors.append("Start Date is required.")
    if not contract_data["service_type"]:
        errors.append("Service Type is required.")
    if not contract_data["asset_classes"]:
        errors.append("At least one Asset Class is required.")

    if errors:
        org_name = get_org_name(str(lead["organization_id"])) if lead.get("organization_id") else "—"
        lead_summary = {
            "id": lead_id,
            "summary": lead.get("summary"),
            "rating": lead.get("rating"),
        }
        context = {
            "request": request,
            "user": current_user,
            "contract": {**contract_data, "id": None},
            "org_name": org_name,
            "lead_summary": lead_summary,
            "mode": "create",
            "lead_id": lead_id,
            "service_types": get_reference_data("service_type"),
            "asset_classes": get_reference_data("asset_class"),
            "errors": errors,
        }
        return templates.TemplateResponse("contracts/form.html", context)

    # Create the contract
    resp = sb.table("contracts").insert(contract_data).execute()

    if resp.data:
        contract_id = resp.data[0]["id"]

        # Audit log the creation
        log_field_change("contract", str(contract_id), "_created", None, f"manually created from lead {lead_id}", current_user.id)
        log_field_change("lead", lead_id, "_contract_created", None, str(contract_id), current_user.id)

        return RedirectResponse(url=f"/contracts/{contract_id}", status_code=303)

    raise HTTPException(status_code=500, detail="Failed to create contract")


# ---------------------------------------------------------------------------
# LIST — GET /contracts
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def list_contracts(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List contracts with filtering, search, sorting, and pagination."""
    ctx = build_grid_context("contract", request, current_user, base_url="/contracts")

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("components/_grid.html", {"request": request, **ctx})

    service_types = get_reference_data("service_type")
    ctx.update({
        "user": current_user,
        "total_count": ctx["pagination"]["total"],
        "search": ctx["filters"].get("q", ""),
        "service_type": ctx["filters"].get("service", ""),
        "date_from": ctx["filters"].get("from", ""),
        "date_to": ctx["filters"].get("to", ""),
        "service_types": service_types,
    })
    return templates.TemplateResponse("contracts/list.html", {"request": request, **ctx})


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
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    contract = resp.data
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Org name
    org_name = get_org_name(str(contract["organization_id"])) if contract.get("organization_id") else "—"

    # Originating lead info
    lead_info = None
    if contract.get("originating_lead_id"):
        lead_resp = (
            sb.table("leads")
            .select("id, rating, summary, relationship")
            .eq("id", str(contract["originating_lead_id"]))
            .maybe_single()
            .execute()
        )
        lead_info = lead_resp.data

    # Lead stage labels
    lead_stages = get_reference_data("lead_stage")
    stage_labels = {s["value"]: s["label"] for s in lead_stages}

    # Asset class labels
    asset_class_data = get_reference_data("asset_class")
    ac_labels = {a["value"]: a["label"] for a in asset_class_data}

    # Service type labels
    service_type_data = get_reference_data("service_type")
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
            entry["changed_by_name"] = get_user_name(str(entry["changed_by"]))
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
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    contract = resp.data
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Org name for read-only display
    org_name = get_org_name(str(contract["organization_id"])) if contract.get("organization_id") else "—"

    # Originating lead summary for read-only display
    lead_summary = None
    if contract.get("originating_lead_id"):
        lead_resp = (
            sb.table("leads")
            .select("id, summary, rating")
            .eq("id", str(contract["originating_lead_id"]))
            .maybe_single()
            .execute()
        )
        lead_summary = lead_resp.data

    form_ctx = build_form_context("contract", record=contract)

    context = {
        "request": request,
        "user": current_user,
        "contract": contract,
        "org_name": org_name,
        "lead_summary": lead_summary,
        "service_types": get_reference_data("service_type"),
        "asset_classes": get_reference_data("asset_class"),
        "sections": form_ctx["sections"],
        "field_defs": form_ctx["field_defs"],
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
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    old_contract = old_resp.data
    if not old_contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    form = await request.form()

    # Use dynamic form service for parsing and validation
    field_defs = get_field_definitions("contract", active_only=True)
    field_defs = enrich_field_definitions(field_defs)
    update_data = parse_form_data("contract", form, field_defs)
    errors = validate_form_data("contract", update_data, field_defs, record=old_contract)

    if errors:
        org_name = get_org_name(str(old_contract["organization_id"]))
        lead_summary = None
        if old_contract.get("originating_lead_id"):
            lead_resp = (
                sb.table("leads")
                .select("id, summary, rating")
                .eq("id", str(old_contract["originating_lead_id"]))
                .maybe_single()
                .execute()
            )
            lead_summary = lead_resp.data

        form_ctx = build_form_context("contract", record={**old_contract, **update_data})

        context = {
            "request": request,
            "user": current_user,
            "contract": {**old_contract, **update_data},
            "org_name": org_name,
            "lead_summary": lead_summary,
            "service_types": get_reference_data("service_type"),
            "asset_classes": get_reference_data("asset_class"),
            "sections": form_ctx["sections"],
            "field_defs": form_ctx["field_defs"],
            "errors": errors,
        }
        return templates.TemplateResponse("contracts/form.html", context)

    # Audit log changes
    audit_changes("contract", str(contract_id), old_contract, update_data, current_user.id)

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
    sb.table("contracts").update({"is_deleted": True}).eq("id", str(contract_id)).execute()
    log_field_change("contract", str(contract_id), "is_deleted", False, True, current_user.id)

    if request.headers.get("HX-Request"):
        return HTMLResponse('<p class="text-sm text-green-600">Contract archived.</p>')
    return RedirectResponse(url="/contracts", status_code=303)

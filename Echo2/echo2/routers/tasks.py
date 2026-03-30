"""Tasks router — full CRUD, search, filters, pagination, audit logging, status transitions."""

from datetime import date as date_type
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from db.helpers import get_reference_data, log_field_change, audit_changes, batch_resolve_users, is_overdue
from db.field_service import get_field_definitions, enrich_field_definitions
from dependencies import CurrentUser, get_current_user, require_role
from services.form_service import build_form_context, parse_form_data, validate_form_data, get_users_for_lookup
from services.grid_service import build_grid_context

router = APIRouter(prefix="/tasks", tags=["tasks"])
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_linked_record(linked_record_type: str, linked_record_id: str) -> dict:
    """Resolve a polymorphic linked record to display info (single record)."""
    sb = get_supabase()
    info = {"name": "Unknown", "url": "#", "subtitle": "", "type": linked_record_type}

    try:
        if linked_record_type == "activity":
            resp = sb.table("activities").select("id, title").eq("id", linked_record_id).maybe_single().execute()
            if resp.data:
                info["name"] = resp.data.get("title") or "Untitled Activity"
                info["url"] = f"/activities/{linked_record_id}"

        elif linked_record_type == "lead":
            resp = sb.table("leads").select("id, organization_id, summary").eq("id", linked_record_id).maybe_single().execute()
            if resp.data:
                org_name = "Unknown Org"
                if resp.data.get("organization_id"):
                    org_resp = sb.table("organizations").select("company_name").eq("id", str(resp.data["organization_id"])).maybe_single().execute()
                    if org_resp.data:
                        org_name = org_resp.data["company_name"]
                info["name"] = org_name
                info["subtitle"] = resp.data.get("summary") or ""
                info["url"] = f"/leads/{linked_record_id}"

        elif linked_record_type == "fund_prospect":
            # Legacy type — migrated records are now in leads table
            resp = sb.table("leads").select("id, organization_id, fund_id, lead_type").eq("id", linked_record_id).maybe_single().execute()
            if not resp.data:
                # Fallback to fund_prospects table for unmigrated records
                resp = sb.table("fund_prospects").select("id, organization_id, fund_id").eq("id", linked_record_id).maybe_single().execute()
            if resp.data:
                org_name = "Unknown Org"
                ticker = "?"
                if resp.data.get("organization_id"):
                    org_resp = sb.table("organizations").select("company_name").eq("id", str(resp.data["organization_id"])).maybe_single().execute()
                    if org_resp.data:
                        org_name = org_resp.data["company_name"]
                if resp.data.get("fund_id"):
                    fund_resp = sb.table("funds").select("ticker").eq("id", str(resp.data["fund_id"])).maybe_single().execute()
                    if fund_resp.data:
                        ticker = fund_resp.data["ticker"]
                info["name"] = f"{org_name} ({ticker})"
                info["url"] = f"/leads/{linked_record_id}"

        elif linked_record_type == "organization":
            resp = sb.table("organizations").select("id, company_name").eq("id", linked_record_id).maybe_single().execute()
            if resp.data:
                info["name"] = resp.data["company_name"]
                info["url"] = f"/organizations/{linked_record_id}"

        elif linked_record_type == "person":
            resp = sb.table("people").select("id, first_name, last_name").eq("id", linked_record_id).maybe_single().execute()
            if resp.data:
                info["name"] = f"{resp.data['first_name']} {resp.data['last_name']}"
                info["url"] = f"/people/{linked_record_id}"
    except Exception:
        pass

    return info


def _batch_resolve_linked_records(tasks: list[dict]) -> dict:
    """Resolve all linked records in batch. Returns dict keyed by (type, id)."""
    sb = get_supabase()
    results = {}

    # Group by type
    by_type: dict[str, set] = {}
    for t in tasks:
        rt = t.get("linked_record_type")
        ri = t.get("linked_record_id")
        if rt and ri:
            by_type.setdefault(rt, set()).add(str(ri))

    if "activity" in by_type:
        ids = list(by_type["activity"])
        resp = sb.table("activities").select("id, title").in_("id", ids).execute()
        for r in (resp.data or []):
            results[("activity", str(r["id"]))] = {
                "name": r.get("title") or "Untitled Activity",
                "url": f"/activities/{r['id']}",
                "subtitle": "",
                "type": "activity",
            }

    if "lead" in by_type:
        ids = list(by_type["lead"])
        resp = sb.table("leads").select("id, organization_id, summary").in_("id", ids).execute()
        org_ids_needed = {str(r["organization_id"]) for r in (resp.data or []) if r.get("organization_id")}
        org_names = {}
        if org_ids_needed:
            org_resp = sb.table("organizations").select("id, company_name").in_("id", list(org_ids_needed)).execute()
            org_names = {str(o["id"]): o["company_name"] for o in (org_resp.data or [])}
        for r in (resp.data or []):
            org_name = org_names.get(str(r.get("organization_id", "")), "Unknown Org")
            results[("lead", str(r["id"]))] = {
                "name": org_name,
                "url": f"/leads/{r['id']}",
                "subtitle": r.get("summary") or "",
                "type": "lead",
            }

    if "fund_prospect" in by_type:
        # Legacy type — migrated records now in leads table
        ids = list(by_type["fund_prospect"])
        resp = sb.table("leads").select("id, organization_id, fund_id, lead_type").in_("id", ids).execute()
        found_ids = {str(r["id"]) for r in (resp.data or [])}
        remaining_ids = [i for i in ids if i not in found_ids]
        fp_rows = []
        if remaining_ids:
            fp_resp = sb.table("fund_prospects").select("id, organization_id, fund_id").in_("id", remaining_ids).execute()
            fp_rows = fp_resp.data or []
        all_rows = list(resp.data or []) + fp_rows
        org_ids_needed = {str(r["organization_id"]) for r in all_rows if r.get("organization_id")}
        fund_ids_needed = {str(r["fund_id"]) for r in all_rows if r.get("fund_id")}
        org_names = {}
        fund_tickers = {}
        if org_ids_needed:
            org_resp = sb.table("organizations").select("id, company_name").in_("id", list(org_ids_needed)).execute()
            org_names = {str(o["id"]): o["company_name"] for o in (org_resp.data or [])}
        if fund_ids_needed:
            fund_resp = sb.table("funds").select("id, ticker").in_("id", list(fund_ids_needed)).execute()
            fund_tickers = {str(f["id"]): f["ticker"] for f in (fund_resp.data or [])}
        for r in all_rows:
            org_name = org_names.get(str(r.get("organization_id", "")), "Unknown Org")
            ticker = fund_tickers.get(str(r.get("fund_id", "")), "?")
            results[("fund_prospect", str(r["id"]))] = {
                "name": f"{org_name} ({ticker})",
                "url": f"/leads/{r['id']}",
                "subtitle": "",
                "type": "fund_prospect",
            }

    if "organization" in by_type:
        ids = list(by_type["organization"])
        resp = sb.table("organizations").select("id, company_name").in_("id", ids).execute()
        for r in (resp.data or []):
            results[("organization", str(r["id"]))] = {
                "name": r["company_name"],
                "url": f"/organizations/{r['id']}",
                "subtitle": "",
                "type": "organization",
            }

    if "person" in by_type:
        ids = list(by_type["person"])
        resp = sb.table("people").select("id, first_name, last_name").in_("id", ids).execute()
        for r in (resp.data or []):
            results[("person", str(r["id"]))] = {
                "name": f"{r['first_name']} {r['last_name']}",
                "url": f"/people/{r['id']}",
                "subtitle": "",
                "type": "person",
            }

    return results


def _build_task_data_from_form(form: dict) -> dict:
    """Extract task fields from form data."""
    data = {}
    data["title"] = (form.get("title") or "").strip()
    due_date = (form.get("due_date") or "").strip()
    data["due_date"] = due_date if due_date else None
    data["assigned_to"] = (form.get("assigned_to") or "").strip() or None
    data["status"] = (form.get("status") or "open").strip()
    notes = (form.get("notes") or "").strip()
    data["notes"] = notes if notes else None
    data["source"] = "manual"
    lrt = (form.get("linked_record_type") or "").strip()
    data["linked_record_type"] = lrt if lrt else None
    lri = (form.get("linked_record_id") or "").strip()
    data["linked_record_id"] = lri if lri else None
    return data


_STATUS_BADGE_CLASSES = {
    "open": "bg-yellow-100 text-yellow-800",
    "in_progress": "bg-blue-100 text-blue-800",
    "complete": "bg-green-100 text-green-800",
    "cancelled": "bg-gray-100 text-gray-500",
}

_SOURCE_LABELS = {
    "manual": "Manual",
    "activity_follow_up": "Activity Follow-Up",
    "lead_next_steps": "Lead Next Steps",
    "fund_prospect_next_steps": "Fundraise Lead Next Steps",
}


def _render_status_cell_html(task: dict) -> str:
    """Return HTML fragment for the inline status badge + quick action button."""
    task_status = task["status"]
    task_id = task["id"]
    badge_class = _STATUS_BADGE_CLASSES.get(task_status, "bg-gray-100 text-gray-800")
    label = task_status.replace("_", " ").title()

    html = f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium {badge_class}">{label}</span>'

    if task_status == "open":
        html += (
            f' <button hx-post="/tasks/{task_id}/status" '
            f'hx-vals=\'{{"status": "in_progress"}}\' '
            f'hx-target="#task-status-{task_id}" hx-swap="innerHTML" '
            f'class="ml-1 text-xs px-2 py-1 rounded bg-blue-100 text-blue-700 hover:bg-blue-200">'
            f'Start</button>'
        )
    elif task_status == "in_progress":
        html += (
            f' <button hx-post="/tasks/{task_id}/status" '
            f'hx-vals=\'{{"status": "complete"}}\' '
            f'hx-target="#task-status-{task_id}" hx-swap="innerHTML" '
            f'class="ml-1 text-xs px-2 py-1 rounded bg-green-100 text-green-700 hover:bg-green-200">'
            f'Complete</button>'
        )

    return html


def _enrich_tasks_for_list(tasks: list[dict]) -> None:
    """Add is_overdue, linked_record_info, and assigned_to_name to each task."""
    # Batch resolve linked records
    record_map = _batch_resolve_linked_records(tasks)

    # Batch resolve assigned_to names
    user_ids = list({str(t["assigned_to"]) for t in tasks if t.get("assigned_to")})
    user_map = batch_resolve_users(user_ids)

    for task in tasks:
        task["is_overdue"] = is_overdue(task)
        key = (task.get("linked_record_type"), str(task.get("linked_record_id", "")))
        task["linked_record_info"] = record_map.get(key)
        task["assigned_to_name"] = user_map.get(str(task.get("assigned_to", "")), "Unknown")
        task["source_label"] = _SOURCE_LABELS.get(task.get("source", ""), task.get("source", ""))


# ---------------------------------------------------------------------------
# SEARCH RECORDS (HTMX) — GET /tasks/search-records
# ---------------------------------------------------------------------------

@router.get("/search-records", response_class=HTMLResponse)
async def search_records(
    request: Request,
    q: str = Query(""),
    record_type: str = Query("", alias="type"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX endpoint: search for linkable records by type."""
    if not q or len(q) < 2 or not record_type:
        return HTMLResponse("")

    sb = get_supabase()
    html_parts = []

    if record_type == "organization":
        resp = (
            sb.table("organizations")
            .select("id, company_name, organization_type")
            .eq("is_deleted", False)
            .ilike("company_name", f"%{q}%")
            .order("company_name")
            .limit(10)
            .execute()
        )
        for org in (resp.data or []):
            safe_name = org["company_name"].replace("'", "&#39;").replace('"', "&quot;")
            org_type = (org.get("organization_type") or "").replace("_", " ").title()
            html_parts.append(
                f'<button type="button" '
                f'class="w-full text-left px-4 py-2 hover:bg-brand-50 text-sm" '
                f"onclick=\"selectRecord('{org['id']}', '{safe_name}')\">"
                f'<div class="font-medium text-gray-900">{org["company_name"]}</div>'
                f'<div class="text-xs text-gray-400">{org_type}</div>'
                f'</button>'
            )

    elif record_type == "person":
        resp = (
            sb.table("people")
            .select("id, first_name, last_name, email, job_title")
            .eq("is_deleted", False)
            .or_(f"first_name.ilike.%{q}%,last_name.ilike.%{q}%,email.ilike.%{q}%")
            .order("last_name")
            .limit(10)
            .execute()
        )
        for p in (resp.data or []):
            full_name = f"{p['first_name']} {p['last_name']}"
            safe_name = full_name.replace("'", "&#39;").replace('"', "&quot;")
            subtitle = p.get("job_title") or ""
            if p.get("email"):
                subtitle += f" — {p['email']}" if subtitle else p["email"]
            html_parts.append(
                f'<button type="button" '
                f'class="w-full text-left px-4 py-2 hover:bg-brand-50 text-sm" '
                f"onclick=\"selectRecord('{p['id']}', '{safe_name}')\">"
                f'<div class="font-medium text-gray-900">{full_name}</div>'
                f'<div class="text-xs text-gray-400">{subtitle}</div>'
                f'</button>'
            )

    elif record_type == "lead":
        # Search leads via their linked org name
        resp = (
            sb.table("organizations")
            .select("id, company_name")
            .eq("is_deleted", False)
            .ilike("company_name", f"%{q}%")
            .limit(20)
            .execute()
        )
        org_map = {str(o["id"]): o["company_name"] for o in (resp.data or [])}
        if org_map:
            leads_resp = (
                sb.table("leads")
                .select("id, organization_id, summary")
                .eq("is_deleted", False)
                .in_("organization_id", list(org_map.keys()))
                .limit(10)
                .execute()
            )
            for lead in (leads_resp.data or []):
                org_name = org_map.get(str(lead.get("organization_id", "")), "Unknown")
                display = f"{org_name} — {lead.get('summary') or 'No summary'}"
                safe_name = display.replace("'", "&#39;").replace('"', "&quot;")
                html_parts.append(
                    f'<button type="button" '
                    f'class="w-full text-left px-4 py-2 hover:bg-brand-50 text-sm" '
                    f"onclick=\"selectRecord('{lead['id']}', '{safe_name}')\">"
                    f'<div class="font-medium text-gray-900">{org_name}</div>'
                    f'<div class="text-xs text-gray-400">{lead.get("summary") or "No summary"}</div>'
                    f'</button>'
                )

    elif record_type == "fund_prospect":
        # Now searches fundraise/product leads in the leads table
        resp = (
            sb.table("organizations")
            .select("id, company_name")
            .eq("is_deleted", False)
            .ilike("company_name", f"%{q}%")
            .limit(20)
            .execute()
        )
        org_map = {str(o["id"]): o["company_name"] for o in (resp.data or [])}
        if org_map:
            fp_resp = (
                sb.table("leads")
                .select("id, organization_id, fund_id, lead_type")
                .eq("is_deleted", False)
                .eq("lead_type", "product")
                .in_("organization_id", list(org_map.keys()))
                .limit(10)
                .execute()
            )
            # Resolve fund tickers
            fund_ids = list({str(fp["fund_id"]) for fp in (fp_resp.data or []) if fp.get("fund_id")})
            fund_tickers = {}
            if fund_ids:
                funds_resp = sb.table("funds").select("id, ticker").in_("id", fund_ids).execute()
                fund_tickers = {str(f["id"]): f["ticker"] for f in (funds_resp.data or [])}

            for fp in (fp_resp.data or []):
                org_name = org_map.get(str(fp.get("organization_id", "")), "Unknown")
                ticker = fund_tickers.get(str(fp.get("fund_id", "")), "?")
                display = f"{org_name} ({ticker})"
                safe_name = display.replace("'", "&#39;").replace('"', "&quot;")
                html_parts.append(
                    f'<button type="button" '
                    f'class="w-full text-left px-4 py-2 hover:bg-brand-50 text-sm" '
                    f"onclick=\"selectRecord('{fp['id']}', '{safe_name}')\">"
                    f'<div class="font-medium text-gray-900">{display}</div>'
                    f'<div class="text-xs text-gray-400">Fundraise Lead</div>'
                    f'</button>'
                )

    if not html_parts:
        return HTMLResponse('<div class="px-4 py-2 text-sm text-gray-400">No records found</div>')

    return HTMLResponse("\n".join(html_parts))


# ---------------------------------------------------------------------------
# MY TASKS — GET /tasks/my-tasks
# ---------------------------------------------------------------------------

@router.get("/my-tasks", response_class=HTMLResponse)
async def my_tasks(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Personal task view: tasks assigned to the current user."""
    extra_filters = {"assignee": str(current_user.id)}
    ctx = build_grid_context("task", request, current_user, base_url="/tasks/my-tasks", extra_filters=extra_filters)

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("components/_grid.html", {"request": request, **ctx})

    statuses = get_reference_data("task_status")
    ctx.update({
        "user": current_user,
        "view_mode": "my_tasks",
        "total_count": ctx["pagination"]["total"],
        "search": ctx["filters"].get("q", ""),
        "status_filter": ctx["filters"].get("status", ""),
        "assignee_filter": ctx["filters"].get("assignee", ""),
        "source_filter": ctx["filters"].get("source", ""),
        "linked_type": ctx["filters"].get("linked_type", ""),
        "overdue_only": ctx["filters"].get("overdue", ""),
        "date_from": ctx["filters"].get("from", ""),
        "date_to": ctx["filters"].get("to", ""),
        "statuses": statuses,
        "users": ctx.get("users", []),
    })
    return templates.TemplateResponse("tasks/list.html", {"request": request, **ctx})


# ---------------------------------------------------------------------------
# CREATE FORM — GET /tasks/new  (must be before /{task_id})
# ---------------------------------------------------------------------------

@router.get("/new", response_class=HTMLResponse)
async def new_task_form(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    linked_type: str = Query("", alias="linked_type"),
    linked_id: str = Query("", alias="linked_id"),
):
    """Render the new task form. Optionally pre-fill linked record."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    sb = get_supabase()
    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
    statuses = get_reference_data("task_status")

    # Pre-fill linked record if provided
    pre_linked = None
    if linked_type and linked_id:
        pre_linked = _resolve_linked_record(linked_type, linked_id)
        pre_linked["record_type"] = linked_type
        pre_linked["record_id"] = linked_id

    # Suggest coverage owners from activity's linked orgs
    suggested_assignees = []
    if linked_type == "activity" and linked_id:
        try:
            # Get orgs linked to this activity
            aol_resp = sb.table("activity_organization_links").select("organization_id").eq("activity_id", linked_id).execute()
            org_ids = [r["organization_id"] for r in (aol_resp.data or [])]
            if org_ids:
                # Get people at those orgs
                pol_resp = sb.table("person_organization_links").select("person_id").in_("organization_id", org_ids).in_("link_type", ["primary", "secondary"]).execute()
                person_ids = list({r["person_id"] for r in (pol_resp.data or [])})
                if person_ids:
                    # Get coverage owners for those people
                    people_resp = sb.table("people").select("coverage_owner").in_("id", person_ids).eq("is_deleted", False).execute()
                    coverage_owner_ids = list({str(p["coverage_owner"]) for p in (people_resp.data or []) if p.get("coverage_owner")})
                    if coverage_owner_ids:
                        # Get user details for those coverage owners
                        owners_resp = sb.table("users").select("id, display_name").in_("id", coverage_owner_ids).eq("is_active", True).execute()
                        suggested_assignees = owners_resp.data or []
        except Exception:
            pass  # Non-critical feature, don't break the form

    # Build dynamic form context from field definitions
    form_ctx = build_form_context("task", record=None, extra_context={
        "users": users_resp.data or [],
    })

    context = {
        "request": request,
        "user": current_user,
        "task": None,
        "users": users_resp.data or [],
        "statuses": statuses,
        "pre_linked": pre_linked,
        "suggested_assignees": suggested_assignees,
        "sections": form_ctx["sections"],
        "field_defs": form_ctx["field_defs"],
    }
    return templates.TemplateResponse("tasks/form.html", context)


# ---------------------------------------------------------------------------
# LIST ALL — GET /tasks/
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def list_tasks(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all tasks with filtering, search, sorting, and pagination."""
    ctx = build_grid_context("task", request, current_user, base_url="/tasks/")

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("components/_grid.html", {"request": request, **ctx})

    statuses = get_reference_data("task_status")
    sb = get_supabase()
    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()

    ctx.update({
        "user": current_user,
        "view_mode": "all_tasks",
        "total_count": ctx["pagination"]["total"],
        "search": ctx["filters"].get("q", ""),
        "status_filter": ctx["filters"].get("status", ""),
        "assignee_filter": ctx["filters"].get("assignee", ""),
        "source_filter": ctx["filters"].get("source", ""),
        "linked_type": ctx["filters"].get("linked_type", ""),
        "overdue_only": ctx["filters"].get("overdue", ""),
        "date_from": ctx["filters"].get("from", ""),
        "date_to": ctx["filters"].get("to", ""),
        "statuses": statuses,
        "users": users_resp.data or [],
    })
    return templates.TemplateResponse("tasks/list.html", {"request": request, **ctx})


# ---------------------------------------------------------------------------
# CREATE — POST /tasks/
# ---------------------------------------------------------------------------

@router.post("/", response_class=HTMLResponse)
async def create_task(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new manual task."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    form = await request.form()
    field_defs = get_field_definitions("task", active_only=True)
    field_defs = enrich_field_definitions(field_defs)
    task_data = parse_form_data("task", form, field_defs)

    # Always set source to manual for manually created tasks
    task_data["source"] = "manual"

    # Extract entity-specific fields not in field_defs (linked record)
    lrt = (form.get("linked_record_type") or "").strip()
    task_data["linked_record_type"] = lrt if lrt else None
    lri = (form.get("linked_record_id") or "").strip()
    task_data["linked_record_id"] = lri if lri else None

    # Validate using field definitions
    errors = validate_form_data("task", task_data, field_defs)

    # Entity-specific validation
    if task_data.get("linked_record_type") and not task_data.get("linked_record_id"):
        errors.append("Linked Record ID is required when Record Type is selected.")
    if task_data.get("linked_record_id") and not task_data.get("linked_record_type"):
        errors.append("Linked Record Type is required when a record is selected.")

    if errors:
        sb = get_supabase()
        users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
        statuses = get_reference_data("task_status")

        # Rebuild pre-linked for re-rendering
        pre_linked = None
        if task_data.get("linked_record_type") and task_data.get("linked_record_id"):
            pre_linked = _resolve_linked_record(task_data["linked_record_type"], task_data["linked_record_id"])
            pre_linked["record_type"] = task_data["linked_record_type"]
            pre_linked["record_id"] = task_data["linked_record_id"]

        form_ctx = build_form_context("task", record=task_data, extra_context={"users": users_resp.data or []})

        context = {
            "request": request,
            "user": current_user,
            "task": task_data,
            "errors": errors,
            "users": users_resp.data or [],
            "statuses": statuses,
            "pre_linked": pre_linked,
            "sections": form_ctx["sections"],
            "field_defs": form_ctx["field_defs"],
        }
        return templates.TemplateResponse("tasks/form.html", context)

    task_data["created_by"] = str(current_user.id)

    sb = get_supabase()
    resp = sb.table("tasks").insert(task_data).execute()

    if resp.data:
        new_task = resp.data[0]
        log_field_change("task", str(new_task["id"]), "_created", None, "record created", current_user.id)
        return RedirectResponse(url=f"/tasks/{new_task['id']}", status_code=303)

    raise HTTPException(status_code=500, detail="Failed to create task")


# ---------------------------------------------------------------------------
# QUICK STATUS UPDATE (HTMX) — POST /tasks/{task_id}/status
# ---------------------------------------------------------------------------

@router.post("/{task_id}/status", response_class=HTMLResponse)
async def update_task_status(
    request: Request,
    task_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX quick status transition. Returns inline HTML fragment."""
    require_role(current_user, ["admin", "standard_user", "rfp_team", "legal"])

    sb = get_supabase()
    resp = (
        sb.table("tasks")
        .select("*")
        .eq("id", str(task_id))
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    task = resp.data
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Permission: assignee or admin
    if current_user.role != "admin" and str(task["assigned_to"]) != str(current_user.id):
        raise HTTPException(status_code=403, detail="You can only update tasks assigned to you.")

    form = await request.form()
    new_status = (form.get("status") or "").strip()

    allowed_statuses = {"open", "in_progress", "complete", "cancelled"}
    if new_status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")

    old_status = task["status"]
    if old_status != new_status:
        sb.table("tasks").update({"status": new_status}).eq("id", str(task_id)).execute()
        log_field_change("task", str(task_id), "status", old_status, new_status, current_user.id)

    task["status"] = new_status
    return HTMLResponse(_render_status_cell_html(task))


# ---------------------------------------------------------------------------
# ARCHIVE (soft delete) — POST /tasks/{task_id}/archive
# ---------------------------------------------------------------------------

@router.post("/{task_id}/archive", response_class=HTMLResponse)
async def archive_task(
    request: Request,
    task_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-delete a task."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    sb.table("tasks").update({"is_deleted": True}).eq("id", str(task_id)).execute()
    log_field_change("task", str(task_id), "is_deleted", False, True, current_user.id)

    if request.headers.get("HX-Request"):
        return HTMLResponse('<p class="text-sm text-green-600">Task archived.</p>')
    return RedirectResponse(url="/tasks/my-tasks", status_code=303)


# ---------------------------------------------------------------------------
# EDIT FORM — GET /tasks/{task_id}/edit
# ---------------------------------------------------------------------------

@router.get("/{task_id}/edit", response_class=HTMLResponse)
async def edit_task_form(
    request: Request,
    task_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the edit task form."""
    require_role(current_user, ["admin", "standard_user", "rfp_team", "legal"])

    sb = get_supabase()
    resp = (
        sb.table("tasks")
        .select("*")
        .eq("id", str(task_id))
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    task = resp.data
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Non-admin can only edit their own tasks
    if current_user.role != "admin" and str(task["assigned_to"]) != str(current_user.id):
        raise HTTPException(status_code=403, detail="You can only edit tasks assigned to you.")

    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
    statuses = get_reference_data("task_status")

    # Resolve linked record for pre-fill
    pre_linked = None
    if task.get("linked_record_type") and task.get("linked_record_id"):
        pre_linked = _resolve_linked_record(task["linked_record_type"], str(task["linked_record_id"]))
        pre_linked["record_type"] = task["linked_record_type"]
        pre_linked["record_id"] = str(task["linked_record_id"])

    # Build dynamic form context
    form_ctx = build_form_context("task", record=task, extra_context={"users": users_resp.data or []})

    context = {
        "request": request,
        "user": current_user,
        "task": task,
        "users": users_resp.data or [],
        "statuses": statuses,
        "pre_linked": pre_linked,
        "sections": form_ctx["sections"],
        "field_defs": form_ctx["field_defs"],
    }
    return templates.TemplateResponse("tasks/form.html", context)


# ---------------------------------------------------------------------------
# UPDATE — POST /tasks/{task_id}
# ---------------------------------------------------------------------------

@router.post("/{task_id}", response_class=HTMLResponse)
async def update_task(
    request: Request,
    task_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an existing task."""
    require_role(current_user, ["admin", "standard_user", "rfp_team", "legal"])

    sb = get_supabase()
    old_resp = (
        sb.table("tasks")
        .select("*")
        .eq("id", str(task_id))
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    old_task = old_resp.data
    if not old_task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Non-admin can only edit their own tasks
    if current_user.role != "admin" and str(old_task["assigned_to"]) != str(current_user.id):
        raise HTTPException(status_code=403, detail="You can only edit tasks assigned to you.")

    form = await request.form()
    field_defs = get_field_definitions("task", active_only=True)
    field_defs = enrich_field_definitions(field_defs)
    task_data = parse_form_data("task", form, field_defs)

    # For system-generated tasks, preserve the source
    if old_task.get("source") and old_task["source"] != "manual":
        task_data["source"] = old_task["source"]

    # Status comes from form (editable on edit)
    task_data["status"] = (form.get("status") or old_task.get("status", "open")).strip()

    # Extract entity-specific fields not in field_defs (linked record)
    lrt = (form.get("linked_record_type") or "").strip()
    task_data["linked_record_type"] = lrt if lrt else None
    lri = (form.get("linked_record_id") or "").strip()
    task_data["linked_record_id"] = lri if lri else None

    # Validate using field definitions
    errors = validate_form_data("task", task_data, field_defs, record=old_task)

    if errors:
        users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
        statuses = get_reference_data("task_status")

        pre_linked = None
        if task_data.get("linked_record_type") and task_data.get("linked_record_id"):
            pre_linked = _resolve_linked_record(task_data["linked_record_type"], task_data["linked_record_id"])
            pre_linked["record_type"] = task_data["linked_record_type"]
            pre_linked["record_id"] = task_data["linked_record_id"]

        merged = {**old_task, **task_data}
        form_ctx = build_form_context("task", record=merged, extra_context={"users": users_resp.data or []})

        context = {
            "request": request,
            "user": current_user,
            "task": merged,
            "errors": errors,
            "users": users_resp.data or [],
            "statuses": statuses,
            "pre_linked": pre_linked,
            "sections": form_ctx["sections"],
            "field_defs": form_ctx["field_defs"],
        }
        return templates.TemplateResponse("tasks/form.html", context)

    # Audit changes
    audit_changes("task", str(task_id), old_task, task_data, current_user.id)

    # Update
    sb.table("tasks").update(task_data).eq("id", str(task_id)).execute()

    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


# ---------------------------------------------------------------------------
# DETAIL — GET /tasks/{task_id}
# ---------------------------------------------------------------------------

@router.get("/{task_id}", response_class=HTMLResponse)
async def get_task(
    request: Request,
    task_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Task detail page."""
    sb = get_supabase()

    resp = (
        sb.table("tasks")
        .select("*")
        .eq("id", str(task_id))
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    task = resp.data
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Resolve assigned_to name
    assigned_to_name = "Unknown"
    if task.get("assigned_to"):
        user_resp = sb.table("users").select("display_name").eq("id", str(task["assigned_to"])).maybe_single().execute()
        if user_resp.data:
            assigned_to_name = user_resp.data["display_name"]

    # Resolve created_by name
    created_by_name = "Unknown"
    if task.get("created_by"):
        cb_resp = sb.table("users").select("display_name").eq("id", str(task["created_by"])).maybe_single().execute()
        if cb_resp.data:
            created_by_name = cb_resp.data["display_name"]

    # Resolve linked record
    linked_record_info = None
    if task.get("linked_record_type") and task.get("linked_record_id"):
        linked_record_info = _resolve_linked_record(task["linked_record_type"], str(task["linked_record_id"]))

    # Overdue check
    task["is_overdue"] = is_overdue(task)

    # Audit history
    audit_resp = (
        sb.table("audit_log")
        .select("field_name, old_value, new_value, changed_by, changed_at")
        .eq("record_type", "task")
        .eq("record_id", str(task_id))
        .order("changed_at", desc=True)
        .limit(50)
        .execute()
    )
    audit_entries = audit_resp.data or []

    # Resolve audit user names
    audit_user_ids = list({str(a["changed_by"]) for a in audit_entries if a.get("changed_by")})
    audit_user_map = batch_resolve_users(audit_user_ids)
    for entry in audit_entries:
        entry["changed_by_name"] = audit_user_map.get(str(entry.get("changed_by", "")), "Unknown")

    context = {
        "request": request,
        "user": current_user,
        "task": task,
        "assigned_to_name": assigned_to_name,
        "created_by_name": created_by_name,
        "linked_record_info": linked_record_info,
        "source_label": _SOURCE_LABELS.get(task.get("source", ""), task.get("source", "")),
        "audit_entries": audit_entries,
    }
    return templates.TemplateResponse("tasks/detail.html", context)

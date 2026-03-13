"""Tasks router — full CRUD, search, filters, pagination, audit logging, status transitions."""

from datetime import date as date_type
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from dependencies import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/tasks", tags=["tasks"])
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
    record_id: str,
    old_record: dict,
    new_data: dict,
    changed_by: UUID,
) -> None:
    """Compare old record with new data and log every changed field."""
    for field, new_val in new_data.items():
        old_val = old_record.get(field)
        if str(old_val) != str(new_val) and not (old_val is None and new_val is None):
            _log_field_change("task", record_id, field, old_val, new_val, changed_by)


def _is_overdue(task: dict) -> bool:
    """Return True if task is past due and still open/in-progress."""
    if task.get("status") not in ("open", "in_progress"):
        return False
    if not task.get("due_date"):
        return False
    try:
        due = date_type.fromisoformat(str(task["due_date"])[:10])
        return due < date_type.today()
    except (ValueError, TypeError):
        return False


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
                info["url"] = f"/fund-prospects/{linked_record_id}"

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
        ids = list(by_type["fund_prospect"])
        resp = sb.table("fund_prospects").select("id, organization_id, fund_id").in_("id", ids).execute()
        org_ids_needed = {str(r["organization_id"]) for r in (resp.data or []) if r.get("organization_id")}
        fund_ids_needed = {str(r["fund_id"]) for r in (resp.data or []) if r.get("fund_id")}
        org_names = {}
        fund_tickers = {}
        if org_ids_needed:
            org_resp = sb.table("organizations").select("id, company_name").in_("id", list(org_ids_needed)).execute()
            org_names = {str(o["id"]): o["company_name"] for o in (org_resp.data or [])}
        if fund_ids_needed:
            fund_resp = sb.table("funds").select("id, ticker").in_("id", list(fund_ids_needed)).execute()
            fund_tickers = {str(f["id"]): f["ticker"] for f in (fund_resp.data or [])}
        for r in (resp.data or []):
            org_name = org_names.get(str(r.get("organization_id", "")), "Unknown Org")
            ticker = fund_tickers.get(str(r.get("fund_id", "")), "?")
            results[("fund_prospect", str(r["id"]))] = {
                "name": f"{org_name} ({ticker})",
                "url": f"/fund-prospects/{r['id']}",
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


def _batch_resolve_users(user_ids: list[str]) -> dict:
    """Batch resolve user UUIDs to display names. Returns {id: display_name}."""
    if not user_ids:
        return {}
    sb = get_supabase()
    resp = sb.table("users").select("id, display_name").in_("id", user_ids).execute()
    return {str(u["id"]): u["display_name"] for u in (resp.data or [])}


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
    "fund_prospect_next_steps": "Fund Prospect Next Steps",
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
    user_map = _batch_resolve_users(user_ids)

    for task in tasks:
        task["is_overdue"] = _is_overdue(task)
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
            .eq("is_archived", False)
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
            .eq("is_archived", False)
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
            .eq("is_archived", False)
            .ilike("company_name", f"%{q}%")
            .limit(20)
            .execute()
        )
        org_map = {str(o["id"]): o["company_name"] for o in (resp.data or [])}
        if org_map:
            leads_resp = (
                sb.table("leads")
                .select("id, organization_id, summary")
                .eq("is_archived", False)
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
        resp = (
            sb.table("organizations")
            .select("id, company_name")
            .eq("is_archived", False)
            .ilike("company_name", f"%{q}%")
            .limit(20)
            .execute()
        )
        org_map = {str(o["id"]): o["company_name"] for o in (resp.data or [])}
        if org_map:
            fp_resp = (
                sb.table("fund_prospects")
                .select("id, organization_id, fund_id")
                .eq("is_archived", False)
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
                    f'<div class="text-xs text-gray-400">Fund Prospect</div>'
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
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=10, le=100),
    status_filter: str = Query("", alias="status"),
    overdue_only: str = Query("", alias="overdue"),
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    sort_by: str = Query("due_date"),
    sort_dir: str = Query("asc"),
):
    """Personal task view: tasks assigned to the current user."""
    sb = get_supabase()

    query = (
        sb.table("tasks")
        .select("*", count="exact")
        .eq("is_archived", False)
        .eq("assigned_to", str(current_user.id))
    )

    # Status filter
    if status_filter:
        query = query.eq("status", status_filter)

    # Overdue-only filter (DB level)
    if overdue_only == "true":
        query = query.lt("due_date", str(date_type.today())).in_("status", ["open", "in_progress"])

    # Date range
    if date_from:
        query = query.gte("due_date", date_from)
    if date_to:
        query = query.lte("due_date", date_to)

    # Sorting
    valid_sort_cols = ["due_date", "created_at", "status", "title"]
    if sort_by not in valid_sort_cols:
        sort_by = "due_date"
    desc = sort_dir.lower() == "desc"
    # For due_date ASC, we want NULLs last
    query = query.order(sort_by, desc=desc, nullsfirst=False if not desc else True)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    resp = query.execute()
    tasks_list = resp.data or []
    total_count = resp.count or 0
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    # Enrich
    _enrich_tasks_for_list(tasks_list)

    # Reference data for filters
    statuses = _get_reference_data("task_status")

    context = {
        "request": request,
        "user": current_user,
        "tasks": tasks_list,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "status_filter": status_filter,
        "overdue_only": overdue_only,
        "date_from": date_from,
        "date_to": date_to,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "statuses": statuses,
        "users": [],
        "search": "",
        "assignee_filter": "",
        "source_filter": "",
        "linked_type": "",
        "view_mode": "my_tasks",
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("tasks/_list_table.html", context)
    return templates.TemplateResponse("tasks/list.html", context)


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
    statuses = _get_reference_data("task_status")

    # Pre-fill linked record if provided
    pre_linked = None
    if linked_type and linked_id:
        pre_linked = _resolve_linked_record(linked_type, linked_id)
        pre_linked["record_type"] = linked_type
        pre_linked["record_id"] = linked_id

    context = {
        "request": request,
        "user": current_user,
        "task": None,
        "users": users_resp.data or [],
        "statuses": statuses,
        "pre_linked": pre_linked,
    }
    return templates.TemplateResponse("tasks/form.html", context)


# ---------------------------------------------------------------------------
# LIST ALL — GET /tasks/
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def list_tasks(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=10, le=100),
    search: str = Query("", alias="q"),
    status_filter: str = Query("", alias="status"),
    assignee_filter: str = Query("", alias="assignee"),
    source_filter: str = Query("", alias="source"),
    linked_type: str = Query("", alias="linked_type"),
    overdue_only: str = Query("", alias="overdue"),
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    sort_by: str = Query("due_date"),
    sort_dir: str = Query("asc"),
):
    """List all tasks with filtering, search, sorting, and pagination."""
    sb = get_supabase()

    query = (
        sb.table("tasks")
        .select("*", count="exact")
        .eq("is_archived", False)
    )

    # Search
    if search:
        query = query.or_(f"title.ilike.%{search}%,notes.ilike.%{search}%")

    # Status filter
    if status_filter:
        query = query.eq("status", status_filter)

    # Assignee filter
    if assignee_filter:
        query = query.eq("assigned_to", assignee_filter)

    # Source filter
    if source_filter:
        query = query.eq("source", source_filter)

    # Linked record type filter
    if linked_type:
        query = query.eq("linked_record_type", linked_type)

    # Overdue-only filter
    if overdue_only == "true":
        query = query.lt("due_date", str(date_type.today())).in_("status", ["open", "in_progress"])

    # Date range
    if date_from:
        query = query.gte("due_date", date_from)
    if date_to:
        query = query.lte("due_date", date_to)

    # Sorting
    valid_sort_cols = ["due_date", "created_at", "status", "title"]
    if sort_by not in valid_sort_cols:
        sort_by = "due_date"
    desc = sort_dir.lower() == "desc"
    query = query.order(sort_by, desc=desc, nullsfirst=False if not desc else True)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    resp = query.execute()
    tasks_list = resp.data or []
    total_count = resp.count or 0
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    # Enrich
    _enrich_tasks_for_list(tasks_list)

    # Reference data for filters
    statuses = _get_reference_data("task_status")
    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()

    context = {
        "request": request,
        "user": current_user,
        "tasks": tasks_list,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "search": search,
        "status_filter": status_filter,
        "assignee_filter": assignee_filter,
        "source_filter": source_filter,
        "linked_type": linked_type,
        "overdue_only": overdue_only,
        "date_from": date_from,
        "date_to": date_to,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "statuses": statuses,
        "users": users_resp.data or [],
        "view_mode": "all_tasks",
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("tasks/_list_table.html", context)
    return templates.TemplateResponse("tasks/list.html", context)


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
    task_data = _build_task_data_from_form(form)

    # Validation
    errors = []
    if not task_data.get("title"):
        errors.append("Title is required.")
    if not task_data.get("assigned_to"):
        errors.append("Assigned To is required.")
    if task_data.get("linked_record_type") and not task_data.get("linked_record_id"):
        errors.append("Linked Record ID is required when Record Type is selected.")
    if task_data.get("linked_record_id") and not task_data.get("linked_record_type"):
        errors.append("Linked Record Type is required when a record is selected.")

    if errors:
        sb = get_supabase()
        users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
        statuses = _get_reference_data("task_status")

        # Rebuild pre-linked for re-rendering
        pre_linked = None
        if task_data.get("linked_record_type") and task_data.get("linked_record_id"):
            pre_linked = _resolve_linked_record(task_data["linked_record_type"], task_data["linked_record_id"])
            pre_linked["record_type"] = task_data["linked_record_type"]
            pre_linked["record_id"] = task_data["linked_record_id"]

        context = {
            "request": request,
            "user": current_user,
            "task": task_data,
            "errors": errors,
            "users": users_resp.data or [],
            "statuses": statuses,
            "pre_linked": pre_linked,
        }
        return templates.TemplateResponse("tasks/form.html", context)

    task_data["created_by"] = str(current_user.id)

    sb = get_supabase()
    resp = sb.table("tasks").insert(task_data).execute()

    if resp.data:
        new_task = resp.data[0]
        _log_field_change("task", str(new_task["id"]), "_created", None, "record created", current_user.id)
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
        .eq("is_archived", False)
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
        _log_field_change("task", str(task_id), "status", old_status, new_status, current_user.id)

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
    sb.table("tasks").update({"is_archived": True}).eq("id", str(task_id)).execute()
    _log_field_change("task", str(task_id), "is_archived", False, True, current_user.id)

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
        .eq("is_archived", False)
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
    statuses = _get_reference_data("task_status")

    # Resolve linked record for pre-fill
    pre_linked = None
    if task.get("linked_record_type") and task.get("linked_record_id"):
        pre_linked = _resolve_linked_record(task["linked_record_type"], str(task["linked_record_id"]))
        pre_linked["record_type"] = task["linked_record_type"]
        pre_linked["record_id"] = str(task["linked_record_id"])

    context = {
        "request": request,
        "user": current_user,
        "task": task,
        "users": users_resp.data or [],
        "statuses": statuses,
        "pre_linked": pre_linked,
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
        .eq("is_archived", False)
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
    task_data = _build_task_data_from_form(form)

    # For system-generated tasks, preserve the source
    if old_task.get("source") and old_task["source"] != "manual":
        task_data["source"] = old_task["source"]

    # Status comes from form (editable on edit)
    task_data["status"] = (form.get("status") or old_task.get("status", "open")).strip()

    # Validation
    errors = []
    if not task_data.get("title"):
        errors.append("Title is required.")
    if not task_data.get("assigned_to"):
        errors.append("Assigned To is required.")

    if errors:
        users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
        statuses = _get_reference_data("task_status")

        pre_linked = None
        if task_data.get("linked_record_type") and task_data.get("linked_record_id"):
            pre_linked = _resolve_linked_record(task_data["linked_record_type"], task_data["linked_record_id"])
            pre_linked["record_type"] = task_data["linked_record_type"]
            pre_linked["record_id"] = task_data["linked_record_id"]

        context = {
            "request": request,
            "user": current_user,
            "task": {**old_task, **task_data},
            "errors": errors,
            "users": users_resp.data or [],
            "statuses": statuses,
            "pre_linked": pre_linked,
        }
        return templates.TemplateResponse("tasks/form.html", context)

    # Audit changes
    _audit_changes(str(task_id), old_task, task_data, current_user.id)

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
        .eq("is_archived", False)
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
    task["is_overdue"] = _is_overdue(task)

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
    audit_user_map = _batch_resolve_users(audit_user_ids)
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

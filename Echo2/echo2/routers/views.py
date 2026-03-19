"""Screeners router — CRUD endpoints for grid screeners (saved views).
Also provides grid inline-edit (pop-up row editor) endpoints.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from db.field_service import get_field_definitions, enrich_field_definitions, load_custom_values
from db.field_service import save_custom_values
from db.helpers import audit_changes
from dependencies import CurrentUser, get_current_user, require_role
from services.form_service import parse_form_data, validate_form_data, split_core_eav
from services.grid_service import (
    save_view, delete_view, set_default_view,
    update_view, duplicate_view, rename_view,
)

router = APIRouter(prefix="/views", tags=["views"])
templates = Jinja2Templates(directory="templates")


@router.post("/save", response_class=HTMLResponse)
async def save_current_view(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Save current grid state as a named view."""
    require_role(current_user, ["admin", "standard_user", "rfp_team", "legal"])

    form = await request.form()
    entity_type = form.get("entity_type", "").strip()
    view_name = form.get("view_name", "").strip()
    columns_str = form.get("columns", "")
    filters_str = form.get("filters", "{}")
    sort_by = form.get("sort_by", "").strip()
    sort_dir = form.get("sort_dir", "asc").strip()
    is_shared = form.get("is_shared") == "true"
    is_default = form.get("is_default") == "true"

    if not entity_type or not view_name:
        raise HTTPException(status_code=400, detail="Entity type and view name are required.")

    columns = [c.strip() for c in columns_str.split(",") if c.strip()]
    try:
        filters = json.loads(filters_str) if filters_str else {}
    except (json.JSONDecodeError, TypeError):
        filters = {}

    # Strip internal keys from filters
    filters = {k: v for k, v in filters.items() if not k.startswith("_")}

    save_view(
        user_id=str(current_user.id),
        entity_type=entity_type,
        view_name=view_name,
        columns=columns,
        filters=filters,
        sort_by=sort_by,
        sort_dir=sort_dir,
        is_shared=is_shared,
        is_default=is_default,
    )

    # Redirect back to the entity list
    url_map = {
        "organization": "/organizations",
        "person": "/people",
        "lead": "/leads",
        "activity": "/activities",
        "contract": "/contracts",
        "task": "/tasks/my-tasks",
        "distribution_list": "/distribution-lists",
    }
    redirect_url = url_map.get(entity_type, "/")
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/{view_id}/delete", response_class=HTMLResponse)
async def delete_saved_view(
    request: Request,
    view_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a saved view."""
    is_admin = current_user.role == "admin"
    success = delete_view(view_id, str(current_user.id), is_admin=is_admin)
    if not success:
        raise HTTPException(status_code=404, detail="View not found or access denied.")

    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=303)


@router.post("/{view_id}/set-default", response_class=HTMLResponse)
async def set_view_as_default(
    request: Request,
    view_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Mark a saved view as default for the current user."""
    form = await request.form()
    entity_type = form.get("entity_type", "").strip()
    if not entity_type:
        raise HTTPException(status_code=400, detail="Entity type is required.")

    set_default_view(view_id, str(current_user.id), entity_type)

    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=303)


@router.post("/{view_id}/overwrite", response_class=HTMLResponse)
async def overwrite_screener(
    request: Request,
    view_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Overwrite an existing screener with current grid state."""
    require_role(current_user, ["admin", "standard_user", "rfp_team", "legal"])

    form = await request.form()
    columns_str = form.get("columns", "")
    filters_str = form.get("filters", "{}")
    sort_by = form.get("sort_by", "").strip()
    sort_dir = form.get("sort_dir", "asc").strip()

    columns = [c.strip() for c in columns_str.split(",") if c.strip()]
    try:
        filters = json.loads(filters_str) if filters_str else {}
    except (json.JSONDecodeError, TypeError):
        filters = {}

    # Strip internal keys from filters
    filters = {k: v for k, v in filters.items() if not k.startswith("_")}

    success = update_view(
        view_id=view_id,
        user_id=str(current_user.id),
        columns=columns,
        filters=filters,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Screener not found or access denied.")

    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=303)


@router.post("/{view_id}/duplicate", response_class=HTMLResponse)
async def duplicate_screener(
    request: Request,
    view_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Duplicate a screener with a new name."""
    require_role(current_user, ["admin", "standard_user", "rfp_team", "legal"])

    form = await request.form()
    new_name = form.get("new_name", "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="New name is required.")

    result = duplicate_view(
        view_id=view_id,
        user_id=str(current_user.id),
        new_name=new_name,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Screener not found.")

    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=303)


@router.post("/{view_id}/rename", response_class=HTMLResponse)
async def rename_screener(
    request: Request,
    view_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Rename a screener."""
    require_role(current_user, ["admin", "standard_user", "rfp_team", "legal"])

    form = await request.form()
    new_name = form.get("new_name", "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="New name is required.")

    success = rename_view(
        view_id=view_id,
        user_id=str(current_user.id),
        new_name=new_name,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Screener not found or access denied.")

    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=303)


# ---------------------------------------------------------------------------
# GRID INLINE EDIT — GET/POST /views/grid-edit/{entity_type}/{record_id}
# ---------------------------------------------------------------------------

_GRID_EDIT_TABLES = {
    "organization": "organizations",
    "person": "people",
    "lead": "leads",
    "activity": "activities",
    "contract": "contracts",
    "task": "tasks",
}


@router.get("/grid-edit/{entity_type}/{record_id}", response_class=HTMLResponse)
async def grid_edit_form(
    request: Request,
    entity_type: str,
    record_id: str,
    visible_columns: str = Query(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX partial: compact edit form for a grid row (visible columns only)."""
    if entity_type not in _GRID_EDIT_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type: {entity_type}")

    table = _GRID_EDIT_TABLES[entity_type]
    sb = get_supabase()
    resp = sb.table(table).select("*").eq("id", record_id).maybe_single().execute()
    record = resp.data if resp else None
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    # Load field defs, filter to visible columns
    field_defs = get_field_definitions(entity_type, active_only=True)
    field_defs = enrich_field_definitions(field_defs)
    vis_cols = set(visible_columns.split(",")) if visible_columns else None
    if vis_cols:
        field_defs = [fd for fd in field_defs if fd["field_name"] in vis_cols]

    # Merge EAV values
    eav = load_custom_values(entity_type, record_id)
    merged = {**record, **eav}

    # Users for lookup fields
    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
    users = users_resp.data or []

    context = {
        "request": request,
        "entity_type": entity_type,
        "record_id": record_id,
        "record": merged,
        "field_defs": field_defs,
        "users": users,
        "user": current_user,
        "errors": [],
    }
    return templates.TemplateResponse("components/_grid_edit_modal.html", context)


@router.post("/grid-edit/{entity_type}/{record_id}", response_class=HTMLResponse)
async def grid_edit_save(
    request: Request,
    entity_type: str,
    record_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Save grid inline edit. Returns HX-Trigger to refresh grid."""
    if entity_type not in _GRID_EDIT_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type: {entity_type}")

    table = _GRID_EDIT_TABLES[entity_type]
    sb = get_supabase()

    # Fetch old record
    old_resp = sb.table(table).select("*").eq("id", record_id).maybe_single().execute()
    old_record = old_resp.data if old_resp else None
    if not old_record:
        raise HTTPException(status_code=404, detail="Record not found")

    # Parse form
    field_defs = get_field_definitions(entity_type, active_only=True)
    field_defs = enrich_field_definitions(field_defs)
    form = await request.form()

    # Only parse fields that were submitted (visible columns)
    submitted_fields = set(form.keys())
    visible_defs = [fd for fd in field_defs if fd["field_name"] in submitted_fields or fd["field_type"] == "boolean"]

    data = parse_form_data(entity_type, form, visible_defs)
    errors = validate_form_data(entity_type, data, visible_defs, record=old_record)

    if errors:
        eav = load_custom_values(entity_type, record_id)
        merged = {**old_record, **data}
        users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()
        context = {
            "request": request,
            "entity_type": entity_type,
            "record_id": record_id,
            "record": merged,
            "field_defs": visible_defs,
            "users": users_resp.data or [],
            "user": current_user,
            "errors": errors,
        }
        return templates.TemplateResponse("components/_grid_edit_modal.html", context)

    # Split core vs EAV
    core_data, eav_data = split_core_eav(data, visible_defs)

    # Audit + update
    audit_changes(entity_type, record_id, old_record, core_data, current_user.id)
    if core_data:
        sb.table(table).update(core_data).eq("id", record_id).execute()
    if eav_data:
        save_custom_values(entity_type, record_id, eav_data, visible_defs)

    # Return empty response with trigger to refresh grid
    response = HTMLResponse("")
    response.headers["HX-Trigger"] = "gridRefresh"
    return response

"""Screeners router — CRUD endpoints for grid screeners (saved views)."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dependencies import CurrentUser, get_current_user, require_role
from services.grid_service import (
    save_view, delete_view, set_default_view,
    update_view, duplicate_view, rename_view,
)

router = APIRouter(prefix="/views", tags=["views"])


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

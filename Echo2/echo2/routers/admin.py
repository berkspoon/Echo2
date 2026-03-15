"""Admin router — field management, page layouts, role management, user management, reference data."""

import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from db.helpers import get_reference_data, log_field_change, audit_changes, batch_resolve_users
from db.field_service import get_field_definitions, get_field_definitions_grouped, enrich_field_definitions
from dependencies import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

# Entity types that support field definitions
ENTITY_TYPES = ["organization", "person", "lead", "activity", "contract", "task"]

# Reference data category metadata
_CATEGORY_META = {
    "organization_type": {"label": "Organization Type", "parent_category": None},
    "relationship_type": {"label": "Relationship Type", "parent_category": None},
    "country": {"label": "Country", "parent_category": None},
    "activity_type": {"label": "Activity Type", "parent_category": None},
    "activity_subtype": {"label": "Activity Subtype", "parent_category": "activity_type"},
    "lead_stage": {"label": "Lead Stage", "parent_category": "lead_type"},
    "lead_relationship_type": {"label": "Lead Relationship Type", "parent_category": None},
    "service_type": {"label": "Service Type", "parent_category": None},
    "asset_class": {"label": "Asset Class", "parent_category": None},
    "pricing_proposal": {"label": "Pricing Proposal", "parent_category": None},
    "rfp_status": {"label": "RFP Status", "parent_category": None},
    "risk_weight": {"label": "Risk Weight", "parent_category": None},
    "lead_type": {"label": "Lead Type", "parent_category": None},
    "decline_reason": {"label": "Decline Reason", "parent_category": None},
    "document_type": {"label": "Document Type", "parent_category": None},
    "publication_list": {"label": "Publication List", "parent_category": None},
}

FIELD_TYPES = [
    {"value": "text", "label": "Text"},
    {"value": "textarea", "label": "Text Area"},
    {"value": "number", "label": "Number"},
    {"value": "currency", "label": "Currency"},
    {"value": "date", "label": "Date"},
    {"value": "boolean", "label": "Yes/No"},
    {"value": "dropdown", "label": "Dropdown"},
    {"value": "multi_select", "label": "Multi-Select"},
    {"value": "email", "label": "Email"},
    {"value": "url", "label": "URL"},
    {"value": "phone", "label": "Phone"},
    {"value": "lookup", "label": "Lookup"},
]


# ---------------------------------------------------------------------------
# Field Management [Change 10.1]
# ---------------------------------------------------------------------------

@router.get("/fields")
async def list_fields(
    request: Request,
    entity_type: str = Query(default="organization"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Field management — list fields grouped by section for an entity type."""
    require_role(current_user, ["admin"])

    fields = get_field_definitions(entity_type, active_only=False)
    fields = enrich_field_definitions(fields)

    # Group by section
    grouped: dict[str, list[dict]] = {}
    for f in fields:
        section = f.get("section_name") or "Other"
        grouped.setdefault(section, []).append(f)

    # Load dropdown categories for reference
    sb = get_supabase()
    cat_resp = sb.table("reference_data").select("category").execute()
    categories = sorted(set(r["category"] for r in (cat_resp.data or [])))

    ctx = {
        "request": request,
        "user": current_user,
        "entity_type": entity_type,
        "entity_types": ENTITY_TYPES,
        "grouped_fields": grouped,
        "all_fields": fields,
        "categories": categories,
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("admin/_field_list_partial.html", ctx)
    return templates.TemplateResponse("admin/fields.html", ctx)


@router.get("/fields/new")
async def new_field_form(
    request: Request,
    entity_type: str = Query(default="organization"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render create form for a new field definition."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    cat_resp = sb.table("reference_data").select("category").execute()
    categories = sorted(set(r["category"] for r in (cat_resp.data or [])))

    # Get existing sections for this entity type for the dropdown
    existing_fields = get_field_definitions(entity_type, active_only=False)
    sections = sorted(set(f.get("section_name") or "Other" for f in existing_fields))

    return templates.TemplateResponse("admin/field_form.html", {
        "request": request,
        "user": current_user,
        "field": None,
        "entity_type": entity_type,
        "entity_types": ENTITY_TYPES,
        "field_types": FIELD_TYPES,
        "categories": categories,
        "sections": sections,
        "errors": [],
    })


@router.get("/fields/{field_id}/edit")
async def edit_field_form(
    request: Request,
    field_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render edit form for an existing field definition."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    resp = sb.table("field_definitions").select("*").eq("id", field_id).maybe_single().execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Field not found")

    field = resp.data
    entity_type = field["entity_type"]

    cat_resp = sb.table("reference_data").select("category").execute()
    categories = sorted(set(r["category"] for r in (cat_resp.data or [])))

    existing_fields = get_field_definitions(entity_type, active_only=False)
    sections = sorted(set(f.get("section_name") or "Other" for f in existing_fields))

    return templates.TemplateResponse("admin/field_form.html", {
        "request": request,
        "user": current_user,
        "field": field,
        "entity_type": entity_type,
        "entity_types": ENTITY_TYPES,
        "field_types": FIELD_TYPES,
        "categories": categories,
        "sections": sections,
        "errors": [],
    })


@router.post("/fields")
async def create_field(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new field definition."""
    require_role(current_user, ["admin"])

    form = await request.form()
    entity_type = (form.get("entity_type") or "").strip()
    field_name = (form.get("field_name") or "").strip().lower().replace(" ", "_")
    display_name = (form.get("display_name") or "").strip()
    field_type = (form.get("field_type") or "text").strip()
    storage_type = (form.get("storage_type") or "eav").strip()
    section_name = (form.get("section_name") or "").strip()
    new_section = (form.get("new_section") or "").strip()
    if new_section:
        section_name = new_section
    is_required = form.get("is_required") == "on"
    dropdown_category = (form.get("dropdown_category") or "").strip() or None
    default_value = (form.get("default_value") or "").strip() or None

    # Validation
    errors = []
    if not entity_type or entity_type not in ENTITY_TYPES:
        errors.append("Invalid entity type.")
    if not field_name:
        errors.append("Field name is required.")
    if not display_name:
        errors.append("Display name is required.")
    if not section_name:
        errors.append("Section is required.")
    if field_type in ("dropdown", "multi_select") and not dropdown_category:
        errors.append("Dropdown category is required for dropdown/multi-select fields.")

    # Check uniqueness
    if not errors:
        sb = get_supabase()
        dup = (
            sb.table("field_definitions")
            .select("id")
            .eq("entity_type", entity_type)
            .eq("field_name", field_name)
            .maybe_single()
            .execute()
        )
        if dup.data:
            errors.append(f"Field '{field_name}' already exists for {entity_type}.")

    if errors:
        sb = get_supabase()
        cat_resp = sb.table("reference_data").select("category").execute()
        categories = sorted(set(r["category"] for r in (cat_resp.data or [])))
        existing_fields = get_field_definitions(entity_type, active_only=False)
        sections = sorted(set(f.get("section_name") or "Other" for f in existing_fields))
        return templates.TemplateResponse("admin/field_form.html", {
            "request": request,
            "user": current_user,
            "field": dict(form),
            "entity_type": entity_type,
            "entity_types": ENTITY_TYPES,
            "field_types": FIELD_TYPES,
            "categories": categories,
            "sections": sections,
            "errors": errors,
        })

    # Calculate display_order — append to end of section
    sb = get_supabase()
    max_order_resp = (
        sb.table("field_definitions")
        .select("display_order")
        .eq("entity_type", entity_type)
        .eq("section_name", section_name)
        .order("display_order", desc=True)
        .limit(1)
        .execute()
    )
    max_order = (max_order_resp.data[0]["display_order"] if max_order_resp.data else 0) + 1

    row = {
        "entity_type": entity_type,
        "field_name": field_name,
        "display_name": display_name,
        "field_type": field_type,
        "storage_type": storage_type,
        "is_required": is_required,
        "is_system": False,
        "display_order": max_order,
        "section_name": section_name,
        "dropdown_category": dropdown_category,
        "default_value": default_value,
        "is_active": True,
        "validation_rules": {},
        "visibility_rules": {},
        "grid_default_visible": True,
        "grid_sortable": True,
        "grid_filterable": True,
        "created_by": str(current_user.id),
    }
    sb.table("field_definitions").insert(row).execute()

    return RedirectResponse(
        f"/admin/fields?entity_type={entity_type}", status_code=303
    )


@router.post("/fields/{field_id}")
async def update_field(
    request: Request,
    field_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an existing field definition."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    resp = sb.table("field_definitions").select("*").eq("id", field_id).maybe_single().execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Field not found")

    old_field = resp.data
    is_system = old_field.get("is_system", False)

    form = await request.form()
    display_name = (form.get("display_name") or "").strip()
    field_type = (form.get("field_type") or old_field["field_type"]).strip()
    section_name = (form.get("section_name") or "").strip()
    new_section = (form.get("new_section") or "").strip()
    if new_section:
        section_name = new_section
    is_required = form.get("is_required") == "on"
    dropdown_category = (form.get("dropdown_category") or "").strip() or None
    default_value = (form.get("default_value") or "").strip() or None

    errors = []
    if not display_name:
        errors.append("Display name is required.")
    if not section_name:
        errors.append("Section is required.")

    if errors:
        cat_resp = sb.table("reference_data").select("category").execute()
        categories = sorted(set(r["category"] for r in (cat_resp.data or [])))
        existing_fields = get_field_definitions(old_field["entity_type"], active_only=False)
        sections = sorted(set(f.get("section_name") or "Other" for f in existing_fields))
        return templates.TemplateResponse("admin/field_form.html", {
            "request": request,
            "user": current_user,
            "field": {**old_field, **dict(form)},
            "entity_type": old_field["entity_type"],
            "entity_types": ENTITY_TYPES,
            "field_types": FIELD_TYPES,
            "categories": categories,
            "sections": sections,
            "errors": errors,
        })

    update_data = {
        "display_name": display_name,
        "section_name": section_name,
        "is_required": is_required,
        "dropdown_category": dropdown_category,
        "default_value": default_value,
    }

    # System fields: cannot change field_name, storage_type, or field_type
    if not is_system:
        update_data["field_type"] = field_type
        storage_type = (form.get("storage_type") or old_field["storage_type"]).strip()
        update_data["storage_type"] = storage_type

    sb.table("field_definitions").update(update_data).eq("id", field_id).execute()

    # Audit
    audit_changes("field_definition", field_id, old_field, update_data, current_user.id)

    return RedirectResponse(
        f"/admin/fields?entity_type={old_field['entity_type']}", status_code=303
    )


@router.post("/fields/{field_id}/toggle")
async def toggle_field(
    request: Request,
    field_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Activate or deactivate a field. System fields cannot be deactivated."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    resp = sb.table("field_definitions").select("*").eq("id", field_id).maybe_single().execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Field not found")

    field = resp.data
    if field.get("is_system"):
        raise HTTPException(status_code=400, detail="System fields cannot be deactivated.")

    new_active = not field["is_active"]
    sb.table("field_definitions").update({"is_active": new_active}).eq("id", field_id).execute()

    log_field_change("field_definition", field_id, "is_active", field["is_active"], new_active, current_user.id)

    # Return updated partial
    entity_type = field["entity_type"]
    fields = get_field_definitions(entity_type, active_only=False)
    fields = enrich_field_definitions(fields)
    grouped: dict[str, list[dict]] = {}
    for f in fields:
        section = f.get("section_name") or "Other"
        grouped.setdefault(section, []).append(f)

    return templates.TemplateResponse("admin/_field_list_partial.html", {
        "request": request,
        "user": current_user,
        "entity_type": entity_type,
        "entity_types": ENTITY_TYPES,
        "grouped_fields": grouped,
        "all_fields": fields,
    })


@router.post("/fields/{field_id}/reorder")
async def reorder_field(
    request: Request,
    field_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Move a field up or down within its section."""
    require_role(current_user, ["admin"])

    form = await request.form()
    direction = (form.get("direction") or "").strip()  # "up" or "down"

    sb = get_supabase()
    resp = sb.table("field_definitions").select("*").eq("id", field_id).maybe_single().execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Field not found")

    field = resp.data
    entity_type = field["entity_type"]
    section_name = field["section_name"]

    # Get all fields in same section, ordered
    section_fields = (
        sb.table("field_definitions")
        .select("id, display_order")
        .eq("entity_type", entity_type)
        .eq("section_name", section_name)
        .order("display_order")
        .execute()
    ).data or []

    # Find current index
    idx = next((i for i, f in enumerate(section_fields) if str(f["id"]) == str(field_id)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Field not found in section")

    # Swap with neighbor
    if direction == "up" and idx > 0:
        neighbor = section_fields[idx - 1]
    elif direction == "down" and idx < len(section_fields) - 1:
        neighbor = section_fields[idx + 1]
    else:
        # Already at boundary
        return RedirectResponse(f"/admin/fields?entity_type={entity_type}", status_code=303)

    # Swap display_order values
    my_order = field["display_order"]
    their_order = neighbor["display_order"]
    sb.table("field_definitions").update({"display_order": their_order}).eq("id", field_id).execute()
    sb.table("field_definitions").update({"display_order": my_order}).eq("id", neighbor["id"]).execute()

    # Return updated partial
    fields = get_field_definitions(entity_type, active_only=False)
    fields = enrich_field_definitions(fields)
    grouped: dict[str, list[dict]] = {}
    for f in fields:
        sec = f.get("section_name") or "Other"
        grouped.setdefault(sec, []).append(f)

    return templates.TemplateResponse("admin/_field_list_partial.html", {
        "request": request,
        "user": current_user,
        "entity_type": entity_type,
        "entity_types": ENTITY_TYPES,
        "grouped_fields": grouped,
        "all_fields": fields,
    })


# ---------------------------------------------------------------------------
# Page Layout Designer [Change 10.2]
# ---------------------------------------------------------------------------

@router.get("/layouts")
async def list_layouts(
    request: Request,
    entity_type: str = Query(default="organization"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Page layout designer — list layouts for an entity type."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    layouts = (
        sb.table("page_layouts")
        .select("*")
        .eq("entity_type", entity_type)
        .order("layout_type")
        .execute()
    ).data or []

    return templates.TemplateResponse("admin/layout_designer.html", {
        "request": request,
        "user": current_user,
        "entity_type": entity_type,
        "entity_types": ENTITY_TYPES,
        "layouts": layouts,
    })


@router.post("/layouts")
async def create_layout(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create or update a page layout."""
    require_role(current_user, ["admin"])

    form = await request.form()
    entity_type = (form.get("entity_type") or "").strip()
    layout_type = (form.get("layout_type") or "view").strip()
    layout_id = (form.get("layout_id") or "").strip()

    # Parse sections from form — expecting JSON string
    import json
    sections_str = (form.get("sections") or "[]").strip()
    try:
        sections = json.loads(sections_str)
    except json.JSONDecodeError:
        sections = []

    is_active = form.get("is_active") == "on"

    sb = get_supabase()
    data = {
        "entity_type": entity_type,
        "layout_type": layout_type,
        "sections": sections,
        "is_active": is_active,
    }

    if layout_id:
        sb.table("page_layouts").update(data).eq("id", layout_id).execute()
    else:
        data["created_by"] = str(current_user.id)
        sb.table("page_layouts").insert(data).execute()

    return RedirectResponse(f"/admin/layouts?entity_type={entity_type}", status_code=303)


@router.post("/layouts/{layout_id}/delete")
async def delete_layout(
    request: Request,
    layout_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a page layout."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    resp = sb.table("page_layouts").select("entity_type").eq("id", layout_id).maybe_single().execute()
    entity_type = resp.data["entity_type"] if resp.data else "organization"

    sb.table("page_layouts").delete().eq("id", layout_id).execute()

    return RedirectResponse(f"/admin/layouts?entity_type={entity_type}", status_code=303)


# ---------------------------------------------------------------------------
# Role Management [Change 10.3]
# ---------------------------------------------------------------------------

@router.get("/roles")
async def list_roles(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Role management — list all roles."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    roles = sb.table("roles").select("*").order("role_name").execute().data or []

    # Count users per role
    user_roles = sb.table("user_roles").select("role_id").execute().data or []
    role_user_counts: dict[str, int] = {}
    for ur in user_roles:
        rid = str(ur["role_id"])
        role_user_counts[rid] = role_user_counts.get(rid, 0) + 1

    for role in roles:
        role["user_count"] = role_user_counts.get(str(role["id"]), 0)

    return templates.TemplateResponse("admin/roles.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
    })


@router.get("/roles/new")
async def new_role_form(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render create form for a new role."""
    require_role(current_user, ["admin"])

    return templates.TemplateResponse("admin/role_form.html", {
        "request": request,
        "user": current_user,
        "role": None,
        "entity_types": ENTITY_TYPES,
        "errors": [],
    })


@router.get("/roles/{role_id}/edit")
async def edit_role_form(
    request: Request,
    role_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render edit form for an existing role."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    resp = sb.table("roles").select("*").eq("id", role_id).maybe_single().execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Role not found")

    return templates.TemplateResponse("admin/role_form.html", {
        "request": request,
        "user": current_user,
        "role": resp.data,
        "entity_types": ENTITY_TYPES,
        "errors": [],
    })


@router.post("/roles")
async def create_role(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new role."""
    require_role(current_user, ["admin"])

    form = await request.form()
    role_name = (form.get("role_name") or "").strip().lower().replace(" ", "_")
    display_name = (form.get("display_name") or "").strip()
    description = (form.get("description") or "").strip()

    # Build permissions from form checkboxes
    permissions = _build_permissions_from_form(form)

    errors = []
    if not role_name:
        errors.append("Role name is required.")
    if not display_name:
        errors.append("Display name is required.")

    if not errors:
        sb = get_supabase()
        dup = sb.table("roles").select("id").eq("role_name", role_name).maybe_single().execute()
        if dup.data:
            errors.append(f"Role '{role_name}' already exists.")

    if errors:
        return templates.TemplateResponse("admin/role_form.html", {
            "request": request,
            "user": current_user,
            "role": {"role_name": role_name, "display_name": display_name, "description": description, "permissions": permissions},
            "entity_types": ENTITY_TYPES,
            "errors": errors,
        })

    sb = get_supabase()
    sb.table("roles").insert({
        "role_name": role_name,
        "display_name": display_name,
        "description": description,
        "permissions": permissions,
        "is_system": False,
        "is_active": True,
    }).execute()

    return RedirectResponse("/admin/roles", status_code=303)


@router.post("/roles/{role_id}")
async def update_role(
    request: Request,
    role_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an existing role."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    resp = sb.table("roles").select("*").eq("id", role_id).maybe_single().execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Role not found")

    old_role = resp.data
    form = await request.form()
    display_name = (form.get("display_name") or "").strip()
    description = (form.get("description") or "").strip()
    permissions = _build_permissions_from_form(form)

    errors = []
    if not display_name:
        errors.append("Display name is required.")

    if errors:
        return templates.TemplateResponse("admin/role_form.html", {
            "request": request,
            "user": current_user,
            "role": {**old_role, "display_name": display_name, "description": description, "permissions": permissions},
            "entity_types": ENTITY_TYPES,
            "errors": errors,
        })

    update_data = {
        "display_name": display_name,
        "description": description,
        "permissions": permissions,
    }

    # System roles: cannot change role_name
    if not old_role.get("is_system"):
        new_role_name = (form.get("role_name") or old_role["role_name"]).strip()
        update_data["role_name"] = new_role_name

    sb.table("roles").update(update_data).eq("id", role_id).execute()

    return RedirectResponse("/admin/roles", status_code=303)


def _build_permissions_from_form(form) -> dict:
    """Build permissions JSONB from form checkboxes.

    Form fields: perm_{entity}_{action} = "on"
    Plus: admin_panel, manage_users, manage_roles, manage_fields
    """
    actions = ["create", "read", "update", "delete", "archive", "restore"]
    entities: dict[str, list[str]] = {}

    for et in ENTITY_TYPES:
        et_actions = []
        for action in actions:
            if form.get(f"perm_{et}_{action}") == "on":
                et_actions.append(action)
        if et_actions:
            entities[et] = et_actions

    return {
        "entities": entities,
        "admin_panel": form.get("admin_panel") == "on",
        "manage_users": form.get("manage_users") == "on",
        "manage_roles": form.get("manage_roles") == "on",
        "manage_fields": form.get("manage_fields") == "on",
    }


# ---------------------------------------------------------------------------
# User Management [Change 10.3]
# ---------------------------------------------------------------------------

@router.get("/users")
async def list_users(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """User management — list all users with role assignments."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    users = sb.table("users").select("*").order("display_name").execute().data or []

    # Load all roles
    roles = sb.table("roles").select("id, role_name, display_name").order("role_name").execute().data or []
    role_map = {str(r["id"]): r for r in roles}

    # Load user_roles
    user_roles_resp = sb.table("user_roles").select("user_id, role_id").execute().data or []
    user_role_map: dict[str, list[dict]] = {}
    for ur in user_roles_resp:
        uid = str(ur["user_id"])
        role = role_map.get(str(ur["role_id"]))
        if role:
            user_role_map.setdefault(uid, []).append(role)

    for u in users:
        u["assigned_roles"] = user_role_map.get(str(u["id"]), [])

    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "user": current_user,
        "users": users,
        "roles": roles,
    })


@router.post("/users/{user_id}/roles")
async def update_user_roles(
    request: Request,
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update role assignments for a user."""
    require_role(current_user, ["admin"])

    form = await request.form()
    role_ids = form.getlist("role_ids") if hasattr(form, "getlist") else []
    role_ids = [r.strip() for r in role_ids if r.strip()]

    sb = get_supabase()

    # Verify user exists
    user_resp = sb.table("users").select("id").eq("id", user_id).maybe_single().execute()
    if not user_resp.data:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete existing assignments
    sb.table("user_roles").delete().eq("user_id", user_id).execute()

    # Insert new assignments
    for rid in role_ids:
        sb.table("user_roles").insert({
            "user_id": user_id,
            "role_id": rid,
            "assigned_by": str(current_user.id),
        }).execute()

    log_field_change("user", user_id, "roles", "updated", str(role_ids), current_user.id)

    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    request: Request,
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Deactivate a user (soft)."""
    require_role(current_user, ["admin"])

    if str(user_id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself.")

    sb = get_supabase()
    sb.table("users").update({"is_active": False}).eq("id", user_id).execute()

    log_field_change("user", user_id, "is_active", True, False, current_user.id)

    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/activate")
async def activate_user(
    request: Request,
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Reactivate a user."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    sb.table("users").update({"is_active": True}).eq("id", user_id).execute()

    log_field_change("user", user_id, "is_active", False, True, current_user.id)

    return RedirectResponse("/admin/users", status_code=303)


# ---------------------------------------------------------------------------
# Reference Data CRUD [Step 5.0]
# ---------------------------------------------------------------------------

def _get_category_counts() -> dict[str, int]:
    """Return {category: count_of_values} for all known categories."""
    sb = get_supabase()
    all_rd = sb.table("reference_data").select("category").execute().data or []
    counts: dict[str, int] = {}
    for row in all_rd:
        cat = row["category"]
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def _build_categories_ctx() -> dict:
    """Build ordered dict of category metadata with value counts for the sidebar."""
    counts = _get_category_counts()
    categories = {}
    for cat_key, meta in _CATEGORY_META.items():
        categories[cat_key] = {
            "label": meta["label"],
            "parent_category": meta["parent_category"],
            "count": counts.get(cat_key, 0),
        }
    return categories


@router.get("/reference-data")
async def reference_data_page(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Reference data management — category browser page."""
    require_role(current_user, ["admin"])

    categories = _build_categories_ctx()

    return templates.TemplateResponse("admin/reference_data.html", {
        "request": request,
        "user": current_user,
        "categories": categories,
        "active_category": None,
    })


@router.get("/reference-data/{category}")
async def reference_data_values(
    request: Request,
    category: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Values list partial for a category (HTMX)."""
    require_role(current_user, ["admin"])

    if category not in _CATEGORY_META:
        raise HTTPException(status_code=404, detail="Unknown category")

    meta = _CATEGORY_META[category]
    sb = get_supabase()

    # Fetch all values for this category (including inactive)
    values = (
        sb.table("reference_data")
        .select("*")
        .eq("category", category)
        .order("display_order")
        .execute()
    ).data or []

    # If hierarchical, load parent values for display
    parent_values = []
    if meta["parent_category"]:
        parent_values = (
            sb.table("reference_data")
            .select("value, label")
            .eq("category", meta["parent_category"])
            .eq("is_active", True)
            .order("display_order")
            .execute()
        ).data or []

    # Group by parent_value for hierarchical categories
    is_hierarchical = meta["parent_category"] is not None
    grouped: dict[str, list[dict]] = {}
    if is_hierarchical:
        parent_label_map = {p["value"]: p["label"] for p in parent_values}
        for v in values:
            pv = v.get("parent_value") or "(No Parent)"
            grouped.setdefault(pv, []).append(v)
    else:
        grouped["_all"] = values

    return templates.TemplateResponse("admin/_reference_data_values.html", {
        "request": request,
        "user": current_user,
        "category": category,
        "category_label": meta["label"],
        "is_hierarchical": is_hierarchical,
        "parent_category": meta["parent_category"],
        "parent_values": parent_values,
        "grouped_values": grouped,
        "all_values": values,
    })


@router.get("/reference-data/{category}/new")
async def reference_data_new_form(
    request: Request,
    category: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """New value form partial (HTMX)."""
    require_role(current_user, ["admin"])

    if category not in _CATEGORY_META:
        raise HTTPException(status_code=404, detail="Unknown category")

    meta = _CATEGORY_META[category]
    parent_values = []
    if meta["parent_category"]:
        sb = get_supabase()
        parent_values = (
            sb.table("reference_data")
            .select("value, label")
            .eq("category", meta["parent_category"])
            .eq("is_active", True)
            .order("display_order")
            .execute()
        ).data or []

    return templates.TemplateResponse("admin/_reference_data_form.html", {
        "request": request,
        "user": current_user,
        "category": category,
        "category_label": meta["label"],
        "is_hierarchical": meta["parent_category"] is not None,
        "parent_category": meta["parent_category"],
        "parent_values": parent_values,
        "rd": None,
        "errors": [],
    })


@router.post("/reference-data/{category}")
async def reference_data_create(
    request: Request,
    category: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new reference data value."""
    require_role(current_user, ["admin"])

    if category not in _CATEGORY_META:
        raise HTTPException(status_code=404, detail="Unknown category")

    meta = _CATEGORY_META[category]
    form = await request.form()
    value = (form.get("value") or "").strip()
    label = (form.get("label") or "").strip()
    parent_value = (form.get("parent_value") or "").strip() or None
    display_order_str = (form.get("display_order") or "").strip()

    errors = []

    # Validate value: required, snake_case
    if not value:
        errors.append("Value (code) is required.")
    elif not re.match(r'^[a-z0-9_]+$', value):
        errors.append("Value must be snake_case (lowercase letters, numbers, underscores only).")

    if not label:
        errors.append("Label is required.")

    # Parent value required for hierarchical categories
    is_hierarchical = meta["parent_category"] is not None
    if is_hierarchical and not parent_value:
        errors.append(f"Parent value is required for {meta['label']}.")

    sb = get_supabase()

    # Check uniqueness within category
    if not errors:
        dup = (
            sb.table("reference_data")
            .select("id")
            .eq("category", category)
            .eq("value", value)
            .maybe_single()
            .execute()
        )
        if dup.data:
            errors.append(f"Value '{value}' already exists in {meta['label']}.")

    if errors:
        parent_values = []
        if is_hierarchical:
            parent_values = (
                sb.table("reference_data")
                .select("value, label")
                .eq("category", meta["parent_category"])
                .eq("is_active", True)
                .order("display_order")
                .execute()
            ).data or []

        resp = templates.TemplateResponse("admin/_reference_data_form.html", {
            "request": request,
            "user": current_user,
            "category": category,
            "category_label": meta["label"],
            "is_hierarchical": is_hierarchical,
            "parent_category": meta["parent_category"],
            "parent_values": parent_values,
            "rd": {"value": value, "label": label, "parent_value": parent_value, "display_order": display_order_str},
            "errors": errors,
        })
        resp.headers["HX-Retarget"] = "#rd-form-panel"
        resp.headers["HX-Reswap"] = "innerHTML"
        return resp

    # Calculate display_order: use provided or max+1
    if display_order_str:
        try:
            display_order = int(display_order_str)
        except ValueError:
            display_order = 0
    else:
        # Get max display_order for this category (+ parent_value if hierarchical)
        max_q = (
            sb.table("reference_data")
            .select("display_order")
            .eq("category", category)
        )
        if is_hierarchical and parent_value:
            max_q = max_q.eq("parent_value", parent_value)
        max_resp = max_q.order("display_order", desc=True).limit(1).execute()
        display_order = (max_resp.data[0]["display_order"] if max_resp.data else 0) + 1

    row = {
        "category": category,
        "value": value,
        "label": label,
        "parent_value": parent_value,
        "display_order": display_order,
        "is_active": True,
    }
    result = sb.table("reference_data").insert(row).execute()
    new_id = result.data[0]["id"] if result.data else "unknown"

    # Audit log
    log_field_change("reference_data", str(new_id), "created", None, f"{category}/{value}", current_user.id)

    # Return updated values list
    return RedirectResponse(f"/admin/reference-data/{category}", status_code=303)


@router.get("/reference-data/{category}/{rd_id}/edit")
async def reference_data_edit_form(
    request: Request,
    category: str,
    rd_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Edit value form partial (HTMX)."""
    require_role(current_user, ["admin"])

    if category not in _CATEGORY_META:
        raise HTTPException(status_code=404, detail="Unknown category")

    meta = _CATEGORY_META[category]
    sb = get_supabase()

    resp = sb.table("reference_data").select("*").eq("id", rd_id).maybe_single().execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Value not found")

    parent_values = []
    if meta["parent_category"]:
        parent_values = (
            sb.table("reference_data")
            .select("value, label")
            .eq("category", meta["parent_category"])
            .eq("is_active", True)
            .order("display_order")
            .execute()
        ).data or []

    return templates.TemplateResponse("admin/_reference_data_form.html", {
        "request": request,
        "user": current_user,
        "category": category,
        "category_label": meta["label"],
        "is_hierarchical": meta["parent_category"] is not None,
        "parent_category": meta["parent_category"],
        "parent_values": parent_values,
        "rd": resp.data,
        "errors": [],
    })


@router.post("/reference-data/{category}/{rd_id}")
async def reference_data_update(
    request: Request,
    category: str,
    rd_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an existing reference data value."""
    require_role(current_user, ["admin"])

    if category not in _CATEGORY_META:
        raise HTTPException(status_code=404, detail="Unknown category")

    meta = _CATEGORY_META[category]
    sb = get_supabase()

    resp = sb.table("reference_data").select("*").eq("id", rd_id).maybe_single().execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Value not found")

    old_record = resp.data
    form = await request.form()
    label = (form.get("label") or "").strip()
    parent_value = (form.get("parent_value") or "").strip() or None
    display_order_str = (form.get("display_order") or "").strip()
    is_active = form.get("is_active") == "on"

    errors = []
    if not label:
        errors.append("Label is required.")

    is_hierarchical = meta["parent_category"] is not None
    if is_hierarchical and not parent_value:
        errors.append(f"Parent value is required for {meta['label']}.")

    if errors:
        parent_values = []
        if is_hierarchical:
            parent_values = (
                sb.table("reference_data")
                .select("value, label")
                .eq("category", meta["parent_category"])
                .eq("is_active", True)
                .order("display_order")
                .execute()
            ).data or []

        resp = templates.TemplateResponse("admin/_reference_data_form.html", {
            "request": request,
            "user": current_user,
            "category": category,
            "category_label": meta["label"],
            "is_hierarchical": is_hierarchical,
            "parent_category": meta["parent_category"],
            "parent_values": parent_values,
            "rd": {**old_record, "label": label, "parent_value": parent_value, "display_order": display_order_str, "is_active": is_active},
            "errors": errors,
        })
        resp.headers["HX-Retarget"] = "#rd-form-panel"
        resp.headers["HX-Reswap"] = "innerHTML"
        return resp

    display_order = int(display_order_str) if display_order_str else old_record["display_order"]

    update_data = {
        "label": label,
        "parent_value": parent_value,
        "display_order": display_order,
        "is_active": is_active,
    }

    sb.table("reference_data").update(update_data).eq("id", rd_id).execute()

    # Audit changes
    audit_changes("reference_data", rd_id, old_record, update_data, current_user.id)

    return RedirectResponse(f"/admin/reference-data/{category}", status_code=303)


@router.post("/reference-data/{category}/{rd_id}/toggle")
async def reference_data_toggle(
    request: Request,
    category: str,
    rd_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Toggle is_active on a reference data value."""
    require_role(current_user, ["admin"])

    if category not in _CATEGORY_META:
        raise HTTPException(status_code=404, detail="Unknown category")

    sb = get_supabase()
    resp = sb.table("reference_data").select("*").eq("id", rd_id).maybe_single().execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Value not found")

    old_record = resp.data
    new_active = not old_record["is_active"]

    # If deactivating, check if value is in use (warning only — still allow)
    warning = None
    if not new_active:
        value = old_record["value"]
        # Check common usage patterns based on category
        _usage_checks = {
            "organization_type": ("organizations", "organization_type"),
            "relationship_type": ("organizations", "relationship_type"),
            "country": ("organizations", "country"),
            "activity_type": ("activities", "activity_type"),
            "activity_subtype": ("activities", "activity_subtype"),
            "lead_stage": ("leads", "stage"),
            "service_type": ("leads", "service_type"),
            "lead_type": ("leads", "lead_type"),
            "lead_relationship_type": ("leads", "relationship_type"),
        }
        if category in _usage_checks:
            table, col = _usage_checks[category]
            usage = (
                sb.table(table)
                .select("id", count="exact")
                .eq(col, value)
                .execute()
            )
            if usage.count and usage.count > 0:
                warning = f"This value is currently used by {usage.count} record(s). It will remain on existing records but won't appear in dropdowns."

    sb.table("reference_data").update({"is_active": new_active}).eq("id", rd_id).execute()
    log_field_change("reference_data", rd_id, "is_active", old_record["is_active"], new_active, current_user.id)

    # Return updated values list
    return RedirectResponse(f"/admin/reference-data/{category}", status_code=303)


@router.post("/reference-data/{category}/{rd_id}/reorder")
async def reference_data_reorder(
    request: Request,
    category: str,
    rd_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Move a reference data value up or down in display order."""
    require_role(current_user, ["admin"])

    if category not in _CATEGORY_META:
        raise HTTPException(status_code=404, detail="Unknown category")

    form = await request.form()
    direction = (form.get("direction") or "").strip()

    sb = get_supabase()
    resp = sb.table("reference_data").select("*").eq("id", rd_id).maybe_single().execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Value not found")

    item = resp.data
    parent_value = item.get("parent_value")

    # Get all items in same category + parent_value, ordered
    query = (
        sb.table("reference_data")
        .select("id, display_order")
        .eq("category", category)
        .order("display_order")
    )
    if parent_value:
        query = query.eq("parent_value", parent_value)
    else:
        query = query.is_("parent_value", "null")

    siblings = query.execute().data or []

    # Find current index
    idx = next((i for i, s in enumerate(siblings) if str(s["id"]) == str(rd_id)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Item not found in ordering")

    # Swap with neighbor
    if direction == "up" and idx > 0:
        neighbor = siblings[idx - 1]
    elif direction == "down" and idx < len(siblings) - 1:
        neighbor = siblings[idx + 1]
    else:
        return RedirectResponse(f"/admin/reference-data/{category}", status_code=303)

    # Swap display_order values
    my_order = item["display_order"]
    their_order = neighbor["display_order"]
    sb.table("reference_data").update({"display_order": their_order}).eq("id", rd_id).execute()
    sb.table("reference_data").update({"display_order": my_order}).eq("id", neighbor["id"]).execute()

    return RedirectResponse(f"/admin/reference-data/{category}", status_code=303)


# ---------------------------------------------------------------------------
# Record Restoration (Admin un-delete) [Change 14]
# ---------------------------------------------------------------------------

_RESTORABLE_ENTITIES = {
    "organization": "organizations",
    "person": "people",
    "activity": "activities",
    "lead": "leads",
    "contract": "contracts",
    "task": "tasks",
}


@router.post("/{entity_type}/{record_id}/restore")
async def restore_record(
    request: Request,
    entity_type: str,
    record_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Restore a soft-deleted record (admin only)."""
    require_role(current_user, ["admin"])

    if entity_type not in _RESTORABLE_ENTITIES:
        raise HTTPException(status_code=400, detail=f"Cannot restore entity type: {entity_type}")

    table = _RESTORABLE_ENTITIES[entity_type]
    sb = get_supabase()

    # Verify record exists and is deleted
    resp = sb.table(table).select("id, is_deleted").eq("id", record_id).maybe_single().execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Record not found")
    if not resp.data.get("is_deleted"):
        raise HTTPException(status_code=400, detail="Record is not deleted")

    sb.table(table).update({"is_deleted": False}).eq("id", record_id).execute()
    log_field_change(entity_type, record_id, "is_deleted", True, False, current_user.id)

    if request.headers.get("HX-Request"):
        return HTMLResponse(f'<p class="text-sm text-green-600">Record restored successfully.</p>')
    return RedirectResponse(f"/{table}/{record_id}", status_code=303)


# ---------------------------------------------------------------------------
# Batch Duplicate Scan (Admin) [Change 15]
# ---------------------------------------------------------------------------

@router.get("/duplicates/{entity_type}", response_class=HTMLResponse)
async def batch_duplicate_scan(
    request: Request,
    entity_type: str,
    page: int = Query(1, ge=1),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Admin batch duplicate scan — shows top potential duplicate pairs."""
    require_role(current_user, ["admin"])

    if entity_type not in ("organization", "person"):
        raise HTTPException(status_code=400, detail="Entity type must be 'organization' or 'person'")

    sb = get_supabase()
    page_size = 50

    # Load all suppressions for this entity type
    supp_resp = sb.table("duplicate_suppressions").select("record_id_a, record_id_b").eq("entity_type", entity_type).execute()
    suppressed_pairs = set()
    for s in (supp_resp.data or []):
        suppressed_pairs.add(frozenset([s["record_id_a"], s["record_id_b"]]))

    # Get all active records
    if entity_type == "organization":
        records_resp = sb.table("organizations").select("id, company_name, organization_type, website").eq("is_deleted", False).order("company_name").execute()
        records = records_resp.data or []

        # Find pairs using the existing similarity RPC one-by-one for top records
        # This is more practical: query top N orgs sorted by name, check each for dupes
        pairs = []
        seen = set()
        for rec in records:
            dupes_resp = sb.rpc("check_org_name_similarity", {
                "search_name": rec["company_name"],
                "similarity_threshold": 0.4,
            }).execute()
            for dupe in (dupes_resp.data or []):
                if dupe["id"] == rec["id"]:
                    continue
                pair_key = frozenset([rec["id"], dupe["id"]])
                if pair_key in seen or pair_key in suppressed_pairs:
                    continue
                seen.add(pair_key)
                pairs.append({
                    "id_a": rec["id"],
                    "name_a": rec["company_name"],
                    "type_a": rec.get("organization_type", ""),
                    "id_b": dupe["id"],
                    "name_b": dupe["company_name"],
                    "type_b": dupe.get("organization_type", ""),
                    "similarity": dupe.get("similarity", 0),
                })
            if len(pairs) >= 200:  # cap for performance
                break
    else:
        records_resp = sb.table("people").select("id, first_name, last_name, email").eq("is_deleted", False).order("last_name").execute()
        records = records_resp.data or []

        pairs = []
        seen = set()
        for rec in records:
            dupes_resp = sb.rpc("check_person_name_similarity", {
                "search_first": rec["first_name"] or "",
                "search_last": rec["last_name"] or "",
                "similarity_threshold": 0.4,
            }).execute()
            for dupe in (dupes_resp.data or []):
                if dupe["id"] == rec["id"]:
                    continue
                pair_key = frozenset([rec["id"], dupe["id"]])
                if pair_key in seen or pair_key in suppressed_pairs:
                    continue
                seen.add(pair_key)
                pairs.append({
                    "id_a": rec["id"],
                    "name_a": f"{rec['first_name']} {rec['last_name']}",
                    "email_a": rec.get("email", ""),
                    "id_b": dupe["id"],
                    "name_b": f"{dupe.get('first_name', '')} {dupe.get('last_name', '')}".strip() or dupe.get("company_name", ""),
                    "email_b": dupe.get("email", ""),
                    "similarity": dupe.get("similarity", 0),
                })
            if len(pairs) >= 200:
                break

    # Sort by similarity descending
    pairs.sort(key=lambda p: p.get("similarity", 0), reverse=True)

    # Paginate
    total = len(pairs)
    offset = (page - 1) * page_size
    page_pairs = pairs[offset:offset + page_size]
    total_pages = max(1, (total + page_size - 1) // page_size)

    context = {
        "request": request,
        "user": current_user,
        "entity_type": entity_type,
        "pairs": page_pairs,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    }
    return templates.TemplateResponse("admin/duplicates.html", context)


@router.post("/duplicates/{entity_type}/suppress", response_class=HTMLResponse)
async def suppress_duplicate_admin(
    request: Request,
    entity_type: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Suppress a duplicate pair from the admin batch scan page."""
    require_role(current_user, ["admin"])

    if entity_type not in ("organization", "person"):
        raise HTTPException(status_code=400, detail="Invalid entity type")

    form = await request.form()
    id_a = form.get("id_a", "")
    id_b = form.get("id_b", "")
    if not id_a or not id_b:
        raise HTTPException(status_code=400, detail="Missing record IDs")

    # Normalize: smaller UUID as record_id_a
    norm_a, norm_b = (min(id_a, id_b), max(id_a, id_b))

    sb = get_supabase()
    sb.table("duplicate_suppressions").upsert({
        "entity_type": entity_type,
        "record_id_a": norm_a,
        "record_id_b": norm_b,
        "suppressed_by": str(current_user.id),
    }).execute()

    log_field_change(entity_type, norm_a, "duplicate_suppressed", norm_b, "suppressed", current_user.id)

    # Return empty string to remove the row via hx-swap="outerHTML"
    return HTMLResponse("")

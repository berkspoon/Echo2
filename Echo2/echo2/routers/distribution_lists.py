"""Distribution lists router — full CRUD, member management, send preview/history,
L2-superset-of-L1 enforcement, DNC/RFP Hold suppression."""

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from dependencies import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/distribution-lists", tags=["distribution_lists"])
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
            _log_field_change("distribution_list", record_id, field, old_val, new_val, changed_by)


def _get_user_name(user_id: str) -> str:
    """Look up a user display_name by ID."""
    sb = get_supabase()
    resp = sb.table("users").select("display_name").eq("id", user_id).single().execute()
    return resp.data["display_name"] if resp.data else "Unknown"


def _get_person_with_org(person_id: str) -> dict | None:
    """Look up a person with their primary org name."""
    sb = get_supabase()
    person_resp = (
        sb.table("people")
        .select("id, first_name, last_name, email, do_not_contact, is_archived, coverage_owner")
        .eq("id", person_id)
        .single()
        .execute()
    )
    if not person_resp.data:
        return None
    person = person_resp.data

    # Primary org
    org_link_resp = (
        sb.table("person_organization_links")
        .select("organization_id")
        .eq("person_id", person_id)
        .eq("link_type", "primary")
        .limit(1)
        .execute()
    )
    org_name = None
    org_rfp_hold = False
    if org_link_resp.data:
        org_resp = (
            sb.table("organizations")
            .select("company_name, rfp_hold")
            .eq("id", org_link_resp.data[0]["organization_id"])
            .single()
            .execute()
        )
        if org_resp.data:
            org_name = org_resp.data["company_name"]
            org_rfp_hold = org_resp.data.get("rfp_hold", False)

    person["org_name"] = org_name
    person["org_rfp_hold"] = org_rfp_hold
    person["full_name"] = f"{person['first_name']} {person['last_name']}"
    return person


def _can_edit_list(dist_list: dict, current_user: CurrentUser) -> bool:
    """Check if the current user can edit this distribution list."""
    if current_user.role == "admin":
        return True
    if dist_list.get("is_official"):
        return False  # Only admin can edit official lists
    # Custom lists: owner or admin/standard/rfp_team
    if current_user.role in ("standard_user", "rfp_team"):
        return str(dist_list.get("owner_id")) == str(current_user.id)
    return False


def _can_manage_members(dist_list: dict, current_user: CurrentUser) -> bool:
    """Check if the current user can add/remove members."""
    if current_user.role == "admin":
        return True
    if current_user.role in ("standard_user", "rfp_team"):
        if dist_list.get("is_official"):
            return True  # Standard users can manage official list members
        return str(dist_list.get("owner_id")) == str(current_user.id) or not dist_list.get("is_private")
    return False


def _can_send(dist_list: dict, current_user: CurrentUser) -> bool:
    """Check if the current user can send from this list."""
    if current_user.role == "admin":
        return True
    if dist_list.get("is_official"):
        return False  # Official list sends restricted to admin (authorized senders TBD)
    if current_user.role in ("standard_user", "rfp_team"):
        return str(dist_list.get("owner_id")) == str(current_user.id)
    return False


def _build_list_data_from_form(form) -> dict:
    """Extract distribution list fields from form data."""
    data = {}
    for text_field in ("list_name", "list_type", "brand", "asset_class", "frequency"):
        val = (form.get(text_field) or "").strip()
        data[text_field] = val if val else None

    # Booleans
    data["is_official"] = form.get("is_official") == "on"
    data["is_private"] = form.get("is_private") == "on"

    # If official, force not private
    if data["is_official"]:
        data["is_private"] = False

    # L2 superset FK
    l2_of = (form.get("l2_superset_of") or "").strip()
    data["l2_superset_of"] = l2_of if l2_of else None

    return data


def _validate_list_fields(data: dict) -> list[str]:
    """Validate distribution list fields. Returns list of error strings."""
    errors = []
    if not data.get("list_name"):
        errors.append("List Name is required.")
    if not data.get("list_type"):
        errors.append("List Type is required.")
    return errors


def _get_member_count(list_id: str) -> int:
    """Get count of active members for a distribution list."""
    sb = get_supabase()
    resp = (
        sb.table("distribution_list_members")
        .select("id", count="exact")
        .eq("distribution_list_id", list_id)
        .eq("is_active", True)
        .execute()
    )
    return resp.count or 0


def _build_send_preview(list_id: str) -> dict:
    """Build a send preview with L2 superset inclusion and DNC/RFP Hold suppression.

    Returns dict with included, excluded_dnc, excluded_rfp_hold, totals, and L2 info.
    """
    sb = get_supabase()

    # 1. Get target list
    target_list = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", list_id)
        .single()
        .execute()
        .data
    )
    if not target_list:
        return {"included": [], "excluded_dnc": [], "excluded_rfp_hold": [],
                "total_members": 0, "sendable_count": 0, "l2_lists": [], "l2_member_count": 0}

    # 2. Get direct active members
    direct_resp = (
        sb.table("distribution_list_members")
        .select("person_id")
        .eq("distribution_list_id", list_id)
        .eq("is_active", True)
        .execute()
    )
    person_ids = {m["person_id"] for m in (direct_resp.data or [])}

    # 3. L2 superset inclusion: find L2 lists that reference this list (this list is L1)
    l2_lists_resp = (
        sb.table("distribution_lists")
        .select("id, list_name")
        .eq("l2_superset_of", list_id)
        .eq("is_active", True)
        .execute()
    )
    l2_lists = l2_lists_resp.data or []
    l2_member_count = 0

    for l2 in l2_lists:
        l2_members_resp = (
            sb.table("distribution_list_members")
            .select("person_id")
            .eq("distribution_list_id", l2["id"])
            .eq("is_active", True)
            .execute()
        )
        for m in (l2_members_resp.data or []):
            if m["person_id"] not in person_ids:
                person_ids.add(m["person_id"])
                l2_member_count += 1

    # 4. For each person, check DNC and RFP Hold
    included = []
    excluded_dnc = []
    excluded_rfp_hold = []

    for pid in person_ids:
        person = _get_person_with_org(pid)
        if not person or person.get("is_archived"):
            continue

        person_info = {
            "id": person["id"],
            "name": person["full_name"],
            "email": person.get("email"),
            "org_name": person.get("org_name"),
        }

        if person.get("do_not_contact"):
            excluded_dnc.append({**person_info, "reason": "Do Not Contact"})
        elif person.get("org_rfp_hold"):
            excluded_rfp_hold.append({**person_info, "reason": f"RFP Hold ({person.get('org_name', 'Unknown Org')})"})
        else:
            included.append(person_info)

    return {
        "included": sorted(included, key=lambda x: x["name"]),
        "excluded_dnc": sorted(excluded_dnc, key=lambda x: x["name"]),
        "excluded_rfp_hold": sorted(excluded_rfp_hold, key=lambda x: x["name"]),
        "total_members": len(person_ids),
        "sendable_count": len(included),
        "l2_lists": l2_lists,
        "l2_member_count": l2_member_count,
    }


def _load_form_context(sb, current_user, dist_list=None, errors=None):
    """Load all reference data needed for the distribution list form."""
    list_types = _get_reference_data("distribution_list_type")
    brands = _get_reference_data("brand")
    asset_classes = _get_reference_data("asset_class")

    # L1 publication lists (for L2 superset dropdown)
    l1_lists_resp = (
        sb.table("distribution_lists")
        .select("id, list_name, asset_class")
        .eq("is_active", True)
        .eq("is_official", True)
        .eq("list_type", "publication")
        .is_("l2_superset_of", "null")
        .order("list_name")
        .execute()
    )
    l1_lists = l1_lists_resp.data or []

    return {
        "list_types": list_types,
        "brands": brands,
        "asset_classes": asset_classes,
        "l1_lists": l1_lists,
        "dist_list": dist_list,
        "errors": errors or [],
        "user": current_user,
    }


# ---------------------------------------------------------------------------
# PERSON SEARCH (HTMX autocomplete) — GET /distribution-lists/search-people
# ---------------------------------------------------------------------------

@router.get("/search-people", response_class=HTMLResponse)
async def search_people(
    request: Request,
    q: str = Query(""),
    list_id: str = Query(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX endpoint: return person search results for member add autocomplete.
    Excludes DNC people and people already active in the list."""
    if not q or len(q) < 2:
        return HTMLResponse("")

    sb = get_supabase()
    resp = (
        sb.table("people")
        .select("id, first_name, last_name, email, do_not_contact")
        .eq("is_archived", False)
        .eq("do_not_contact", False)
        .ilike("last_name", f"%{q}%")
        .order("last_name")
        .limit(15)
        .execute()
    )
    # Also search by first name
    resp2 = (
        sb.table("people")
        .select("id, first_name, last_name, email, do_not_contact")
        .eq("is_archived", False)
        .eq("do_not_contact", False)
        .ilike("first_name", f"%{q}%")
        .order("last_name")
        .limit(15)
        .execute()
    )

    # Merge and deduplicate
    seen = set()
    people = []
    for p in (resp.data or []) + (resp2.data or []):
        if p["id"] not in seen:
            seen.add(p["id"])
            people.append(p)

    # Exclude people already active in this list
    if list_id and people:
        existing_resp = (
            sb.table("distribution_list_members")
            .select("person_id")
            .eq("distribution_list_id", list_id)
            .eq("is_active", True)
            .execute()
        )
        existing_ids = {m["person_id"] for m in (existing_resp.data or [])}
        people = [p for p in people if p["id"] not in existing_ids]

    if not people:
        return HTMLResponse('<div class="px-4 py-2 text-sm text-gray-400">No matching people found</div>')

    # Enrich with primary org names
    html_parts = []
    for p in people[:10]:
        # Quick org lookup
        org_link = (
            sb.table("person_organization_links")
            .select("organization_id")
            .eq("person_id", p["id"])
            .eq("link_type", "primary")
            .limit(1)
            .execute()
        )
        org_name = ""
        if org_link.data:
            org_resp = (
                sb.table("organizations")
                .select("company_name")
                .eq("id", org_link.data[0]["organization_id"])
                .single()
                .execute()
            )
            if org_resp.data:
                org_name = org_resp.data["company_name"]

        full_name = f"{p['first_name']} {p['last_name']}"
        email_str = p.get("email") or ""
        safe_name = full_name.replace("'", "&#39;").replace('"', "&quot;")

        html_parts.append(
            f'<div class="flex items-center justify-between px-4 py-2 hover:bg-brand-50">'
            f'<div>'
            f'<div class="text-sm font-medium text-gray-900">{full_name}</div>'
            f'<div class="text-xs text-gray-400">{email_str}{" — " + org_name if org_name else ""}</div>'
            f'</div>'
            f'<button type="button" '
            f'hx-post="/distribution-lists/{list_id}/members/add" '
            f'hx-vals=\'{{"person_id": "{p["id"]}"}}\' '
            f'hx-target="#members-content" '
            f'hx-swap="innerHTML" '
            f'class="ml-2 px-2 py-1 text-xs font-medium text-brand-600 bg-brand-50 rounded hover:bg-brand-100">'
            f'Add</button>'
            f'</div>'
        )
    return HTMLResponse("\n".join(html_parts))


# ---------------------------------------------------------------------------
# CREATE FORM — GET /distribution-lists/new  (must be before /{list_id})
# ---------------------------------------------------------------------------

@router.get("/new", response_class=HTMLResponse)
async def new_list_form(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the new distribution list form."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])
    sb = get_supabase()
    context = _load_form_context(sb, current_user)
    context["request"] = request
    return templates.TemplateResponse("distribution_lists/form.html", context)


# ---------------------------------------------------------------------------
# LIST — GET /distribution-lists
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def list_distribution_lists(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=10, le=100),
    search: str = Query("", alias="q"),
    list_type: str = Query("", alias="type"),
    brand: str = Query("", alias="brand"),
    asset_class: str = Query("", alias="asset_class"),
    official: str = Query("", alias="official"),
    sort_by: str = Query("list_name"),
    sort_dir: str = Query("asc"),
):
    """List distribution lists with filtering, search, sorting, and pagination."""
    sb = get_supabase()

    query = (
        sb.table("distribution_lists")
        .select("id, list_name, list_type, brand, asset_class, frequency, "
                "is_official, is_private, owner_id, l2_superset_of, "
                "created_at", count="exact")
        .eq("is_active", True)
    )

    # Privacy filter: non-admin users only see official + own custom + public custom
    if current_user.role != "admin":
        query = query.or_(
            f"is_official.eq.true,owner_id.eq.{current_user.id},is_private.eq.false"
        )

    # Search by list name
    if search:
        query = query.ilike("list_name", f"%{search}%")

    # Filters
    if list_type:
        query = query.eq("list_type", list_type)
    if brand:
        query = query.eq("brand", brand)
    if asset_class:
        query = query.eq("asset_class", asset_class)
    if official == "official":
        query = query.eq("is_official", True)
    elif official == "custom":
        query = query.eq("is_official", False)

    # Sorting
    valid_sort_cols = ["list_name", "list_type", "brand", "created_at"]
    if sort_by not in valid_sort_cols:
        sort_by = "list_name"
    desc = sort_dir.lower() == "desc"
    query = query.order(sort_by, desc=desc)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    resp = query.execute()
    lists = resp.data or []
    total_count = resp.count or 0
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    # Enrich with member counts
    for dl in lists:
        dl["member_count"] = _get_member_count(str(dl["id"]))
        if dl.get("owner_id"):
            dl["owner_name"] = _get_user_name(str(dl["owner_id"]))
        else:
            dl["owner_name"] = None

    # Reference data for filter dropdowns
    list_types = _get_reference_data("distribution_list_type")
    brands = _get_reference_data("brand")
    asset_classes = _get_reference_data("asset_class")

    context = {
        "request": request,
        "user": current_user,
        "lists": lists,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "search": search,
        "list_type": list_type,
        "brand": brand,
        "asset_class": asset_class,
        "official": official,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "list_types": list_types,
        "brands": brands,
        "asset_classes": asset_classes,
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("distribution_lists/_list_table.html", context)
    return templates.TemplateResponse("distribution_lists/list.html", context)


# ---------------------------------------------------------------------------
# DETAIL — GET /distribution-lists/{list_id}
# ---------------------------------------------------------------------------

@router.get("/{list_id}", response_class=HTMLResponse)
async def get_distribution_list(
    request: Request,
    list_id: UUID,
    tab: str = Query("members"),
    m_page: int = Query(1, ge=1, alias="m_page"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Distribution list detail page with tabs: members, send_history."""
    sb = get_supabase()

    resp = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .single()
        .execute()
    )
    dist_list = resp.data
    if not dist_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    # Owner name
    owner_name = _get_user_name(str(dist_list["owner_id"])) if dist_list.get("owner_id") else None

    # L2 superset info
    l1_list = None
    if dist_list.get("l2_superset_of"):
        l1_resp = (
            sb.table("distribution_lists")
            .select("id, list_name")
            .eq("id", dist_list["l2_superset_of"])
            .single()
            .execute()
        )
        l1_list = l1_resp.data if l1_resp.data else None

    # Reverse lookup: find L2 lists that reference this list (if this is L1)
    l2_lists_resp = (
        sb.table("distribution_lists")
        .select("id, list_name")
        .eq("l2_superset_of", str(list_id))
        .eq("is_active", True)
        .execute()
    )
    l2_lists = l2_lists_resp.data or []

    # Member count
    member_count = _get_member_count(str(list_id))

    # Members tab data (paginated)
    m_page_size = 25
    m_offset = (m_page - 1) * m_page_size
    members_resp = (
        sb.table("distribution_list_members")
        .select("id, person_id, coverage_owner_id, joined_at", count="exact")
        .eq("distribution_list_id", str(list_id))
        .eq("is_active", True)
        .order("joined_at", desc=True)
        .range(m_offset, m_offset + m_page_size - 1)
        .execute()
    )
    members = members_resp.data or []
    members_total = members_resp.count or 0
    members_total_pages = max(1, (members_total + m_page_size - 1) // m_page_size)

    # Enrich members with person info
    for m in members:
        person = _get_person_with_org(m["person_id"])
        if person:
            m["person_name"] = person["full_name"]
            m["person_email"] = person.get("email")
            m["person_org"] = person.get("org_name")
        else:
            m["person_name"] = "Unknown"
            m["person_email"] = None
            m["person_org"] = None
        if m.get("coverage_owner_id"):
            m["coverage_owner_name"] = _get_user_name(str(m["coverage_owner_id"]))
        else:
            m["coverage_owner_name"] = None

    # Send history
    history_resp = (
        sb.table("send_history")
        .select("id, sent_by, sent_at, subject, recipient_count, status")
        .eq("distribution_list_id", str(list_id))
        .order("sent_at", desc=True)
        .limit(50)
        .execute()
    )
    send_history = history_resp.data or []
    for sh in send_history:
        if sh.get("sent_by"):
            sh["sender_name"] = _get_user_name(str(sh["sent_by"]))
        else:
            sh["sender_name"] = "Unknown"

    # Reference data for type labels
    type_labels = {t["value"]: t["label"] for t in _get_reference_data("distribution_list_type")}

    context = {
        "request": request,
        "user": current_user,
        "dist_list": dist_list,
        "owner_name": owner_name,
        "l1_list": l1_list,
        "l2_lists": l2_lists,
        "member_count": member_count,
        "members": members,
        "members_total": members_total,
        "members_total_pages": members_total_pages,
        "m_page": m_page,
        "send_history": send_history,
        "type_labels": type_labels,
        "active_tab": tab,
        "can_edit": _can_edit_list(dist_list, current_user),
        "can_manage": _can_manage_members(dist_list, current_user),
        "can_send": _can_send(dist_list, current_user),
    }

    if request.headers.get("HX-Request") and tab:
        template_name = f"distribution_lists/_tab_{tab}.html"
        return templates.TemplateResponse(template_name, context)
    return templates.TemplateResponse("distribution_lists/detail.html", context)


# ---------------------------------------------------------------------------
# SEND PREVIEW — GET /distribution-lists/{list_id}/send-preview
# ---------------------------------------------------------------------------

@router.get("/{list_id}/send-preview", response_class=HTMLResponse)
async def send_preview(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX endpoint: build and return send preview with DNC/RFP Hold suppression."""
    sb = get_supabase()
    dist_list = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .single()
        .execute()
        .data
    )
    if not dist_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    preview = _build_send_preview(str(list_id))

    context = {
        "request": request,
        "user": current_user,
        "dist_list": dist_list,
        "preview": preview,
        "can_send": _can_send(dist_list, current_user),
    }
    return templates.TemplateResponse("distribution_lists/_send_preview.html", context)


# ---------------------------------------------------------------------------
# SEND — POST /distribution-lists/{list_id}/send
# ---------------------------------------------------------------------------

@router.post("/{list_id}/send", response_class=HTMLResponse)
async def execute_send(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Execute a send: build current snapshot, save to send_history.
    Actual email delivery via Power Automate is Phase 2."""
    sb = get_supabase()
    dist_list = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .single()
        .execute()
        .data
    )
    if not dist_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    if not _can_send(dist_list, current_user):
        raise HTTPException(status_code=403, detail="You do not have permission to send from this list")

    form = await request.form()
    subject = (form.get("subject") or "").strip()
    body = (form.get("body") or "").strip()

    if not subject:
        preview = _build_send_preview(str(list_id))
        context = {
            "request": request,
            "user": current_user,
            "dist_list": dist_list,
            "preview": preview,
            "can_send": True,
            "errors": ["Subject is required."],
        }
        return templates.TemplateResponse("distribution_lists/_send_preview.html", context)

    # Build fresh snapshot
    preview = _build_send_preview(str(list_id))
    recipient_snapshot = json.dumps(preview["included"])

    # Save send history
    sb.table("send_history").insert({
        "distribution_list_id": str(list_id),
        "sent_by": str(current_user.id),
        "subject": subject,
        "body": body or None,
        "recipient_count": preview["sendable_count"],
        "recipient_snapshot": recipient_snapshot,
        "status": "sent",
    }).execute()

    _log_field_change(
        "distribution_list", str(list_id), "send_executed",
        None, f"Sent to {preview['sendable_count']} recipients: {subject}",
        current_user.id,
    )

    if request.headers.get("HX-Request"):
        return HTMLResponse(
            f'<div class="rounded-md bg-green-50 border border-green-200 p-4">'
            f'<p class="text-sm text-green-700">Send recorded successfully. '
            f'{preview["sendable_count"]} recipients. '
            f'<a href="/distribution-lists/{list_id}" class="font-medium underline">Back to list</a></p></div>'
        )
    return RedirectResponse(url=f"/distribution-lists/{list_id}", status_code=303)


# ---------------------------------------------------------------------------
# SEND HISTORY DETAIL — GET /distribution-lists/{list_id}/send-history/{send_id}
# ---------------------------------------------------------------------------

@router.get("/{list_id}/send-history/{send_id}", response_class=HTMLResponse)
async def get_send_detail(
    request: Request,
    list_id: UUID,
    send_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return send history detail with recipient snapshot."""
    sb = get_supabase()
    resp = (
        sb.table("send_history")
        .select("*")
        .eq("id", str(send_id))
        .eq("distribution_list_id", str(list_id))
        .single()
        .execute()
    )
    send = resp.data
    if not send:
        raise HTTPException(status_code=404, detail="Send record not found")

    send["sender_name"] = _get_user_name(str(send["sent_by"])) if send.get("sent_by") else "Unknown"

    # Parse recipient snapshot
    try:
        recipients = json.loads(send["recipient_snapshot"]) if isinstance(send["recipient_snapshot"], str) else send["recipient_snapshot"]
    except (json.JSONDecodeError, TypeError):
        recipients = []

    html = (
        f'<div class="space-y-4">'
        f'<div class="grid grid-cols-2 gap-4">'
        f'<div><dt class="text-xs font-medium text-gray-500 uppercase">Subject</dt>'
        f'<dd class="mt-1 text-sm text-gray-900">{send["subject"]}</dd></div>'
        f'<div><dt class="text-xs font-medium text-gray-500 uppercase">Sent By</dt>'
        f'<dd class="mt-1 text-sm text-gray-900">{send["sender_name"]}</dd></div>'
        f'<div><dt class="text-xs font-medium text-gray-500 uppercase">Date</dt>'
        f'<dd class="mt-1 text-sm text-gray-900">{send["sent_at"][:16] if send.get("sent_at") else "—"}</dd></div>'
        f'<div><dt class="text-xs font-medium text-gray-500 uppercase">Recipients</dt>'
        f'<dd class="mt-1 text-sm text-gray-900">{send["recipient_count"]}</dd></div>'
        f'</div>'
    )
    if send.get("body"):
        html += f'<div><dt class="text-xs font-medium text-gray-500 uppercase">Body</dt><dd class="mt-1 text-sm text-gray-900 whitespace-pre-wrap">{send["body"]}</dd></div>'

    if recipients:
        html += '<div><dt class="text-xs font-medium text-gray-500 uppercase mb-2">Recipient Snapshot</dt>'
        html += '<div class="max-h-60 overflow-auto border border-gray-200 rounded">'
        html += '<table class="min-w-full divide-y divide-gray-200 text-xs">'
        html += '<thead class="bg-gray-50"><tr><th class="px-3 py-2 text-left">Name</th><th class="px-3 py-2 text-left">Email</th><th class="px-3 py-2 text-left">Org</th></tr></thead><tbody>'
        for r in recipients:
            html += f'<tr class="border-t"><td class="px-3 py-1">{r.get("name", "—")}</td><td class="px-3 py-1">{r.get("email", "—")}</td><td class="px-3 py-1">{r.get("org_name", "—")}</td></tr>'
        html += '</tbody></table></div></div>'

    html += '</div>'
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# CREATE — POST /distribution-lists
# ---------------------------------------------------------------------------

@router.post("/", response_class=HTMLResponse)
async def create_distribution_list(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new distribution list."""
    require_role(current_user, ["admin", "standard_user", "rfp_team"])

    form = await request.form()
    list_data = _build_list_data_from_form(form)

    # Only admin can create official lists
    if list_data.get("is_official") and current_user.role != "admin":
        list_data["is_official"] = False

    errors = _validate_list_fields(list_data)
    if errors:
        sb = get_supabase()
        context = _load_form_context(sb, current_user, dist_list=list_data, errors=errors)
        context["request"] = request
        return templates.TemplateResponse("distribution_lists/form.html", context)

    # Set system fields
    list_data["owner_id"] = str(current_user.id)
    list_data["created_by"] = str(current_user.id)

    sb = get_supabase()
    resp = sb.table("distribution_lists").insert(list_data).execute()

    if resp.data:
        new_list = resp.data[0]
        _log_field_change("distribution_list", str(new_list["id"]), "_created", None, "record created", current_user.id)
        return RedirectResponse(url=f"/distribution-lists/{new_list['id']}", status_code=303)

    raise HTTPException(status_code=500, detail="Failed to create distribution list")


# ---------------------------------------------------------------------------
# EDIT FORM — GET /distribution-lists/{list_id}/edit
# ---------------------------------------------------------------------------

@router.get("/{list_id}/edit", response_class=HTMLResponse)
async def edit_list_form(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Render the edit distribution list form."""
    sb = get_supabase()
    resp = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .single()
        .execute()
    )
    dist_list = resp.data
    if not dist_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    if not _can_edit_list(dist_list, current_user):
        raise HTTPException(status_code=403, detail="You do not have permission to edit this list")

    context = _load_form_context(sb, current_user, dist_list=dist_list)
    context["request"] = request
    return templates.TemplateResponse("distribution_lists/form.html", context)


# ---------------------------------------------------------------------------
# UPDATE — POST /distribution-lists/{list_id}
# ---------------------------------------------------------------------------

@router.post("/{list_id}", response_class=HTMLResponse)
async def update_distribution_list(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an existing distribution list."""
    sb = get_supabase()

    old_resp = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .single()
        .execute()
    )
    old_list = old_resp.data
    if not old_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    if not _can_edit_list(old_list, current_user):
        raise HTTPException(status_code=403, detail="You do not have permission to edit this list")

    form = await request.form()
    list_data = _build_list_data_from_form(form)

    # Only admin can set official
    if list_data.get("is_official") and current_user.role != "admin":
        list_data["is_official"] = old_list.get("is_official", False)

    errors = _validate_list_fields(list_data)
    if errors:
        merged = {**old_list, **list_data}
        context = _load_form_context(sb, current_user, dist_list=merged, errors=errors)
        context["request"] = request
        return templates.TemplateResponse("distribution_lists/form.html", context)

    # Audit log
    _audit_changes(str(list_id), old_list, list_data, current_user.id)

    # Update
    sb.table("distribution_lists").update(list_data).eq("id", str(list_id)).execute()

    return RedirectResponse(url=f"/distribution-lists/{list_id}", status_code=303)


# ---------------------------------------------------------------------------
# ARCHIVE (soft-deactivate) — POST /distribution-lists/{list_id}/archive
# ---------------------------------------------------------------------------

@router.post("/{list_id}/archive", response_class=HTMLResponse)
async def archive_distribution_list(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-deactivate a distribution list."""
    require_role(current_user, ["admin"])

    sb = get_supabase()
    sb.table("distribution_lists").update({"is_active": False}).eq("id", str(list_id)).execute()
    _log_field_change("distribution_list", str(list_id), "is_active", True, False, current_user.id)

    if request.headers.get("HX-Request"):
        return HTMLResponse('<p class="text-sm text-green-600">Distribution list archived.</p>')
    return RedirectResponse(url="/distribution-lists", status_code=303)


# ---------------------------------------------------------------------------
# ADD MEMBER — POST /distribution-lists/{list_id}/members/add
# ---------------------------------------------------------------------------

@router.post("/{list_id}/members/add", response_class=HTMLResponse)
async def add_member(
    request: Request,
    list_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Add a person to the distribution list. Handles reactivation of removed members."""
    sb = get_supabase()

    # Verify list exists
    dist_list = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .single()
        .execute()
        .data
    )
    if not dist_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    if not _can_manage_members(dist_list, current_user):
        return HTMLResponse('<div class="text-sm text-red-600 p-2">Permission denied.</div>')

    form = await request.form()
    person_id = (form.get("person_id") or "").strip()
    if not person_id:
        return HTMLResponse('<div class="text-sm text-red-600 p-2">No person selected.</div>')

    # Validate person
    person = _get_person_with_org(person_id)
    if not person:
        return HTMLResponse('<div class="text-sm text-red-600 p-2">Person not found.</div>')
    if person.get("is_archived"):
        return HTMLResponse('<div class="text-sm text-red-600 p-2">Cannot add: person is archived.</div>')
    if person.get("do_not_contact"):
        return HTMLResponse('<div class="text-sm text-red-600 p-2">Cannot add: person is flagged as Do Not Contact.</div>')

    # Check for existing membership (including inactive)
    existing = (
        sb.table("distribution_list_members")
        .select("id, is_active")
        .eq("distribution_list_id", str(list_id))
        .eq("person_id", person_id)
        .execute()
    )

    now_str = datetime.now(timezone.utc).isoformat()

    if existing.data:
        row = existing.data[0]
        if row["is_active"]:
            return HTMLResponse('<div class="text-sm text-yellow-600 p-2">This person is already a member.</div>')
        # Reactivate
        sb.table("distribution_list_members").update({
            "is_active": True,
            "joined_at": now_str,
            "removed_at": None,
            "removal_reason": None,
            "coverage_owner_id": person.get("coverage_owner"),
        }).eq("id", row["id"]).execute()
    else:
        # Insert new membership
        sb.table("distribution_list_members").insert({
            "distribution_list_id": str(list_id),
            "person_id": person_id,
            "coverage_owner_id": person.get("coverage_owner"),
            "is_active": True,
        }).execute()

    _log_field_change(
        "distribution_list", str(list_id), "member_added",
        None, f"{person['full_name']} ({person_id})",
        current_user.id,
    )

    # Return updated members tab content
    return await _render_members_tab(request, str(list_id), current_user, dist_list)


# ---------------------------------------------------------------------------
# REMOVE MEMBER — POST /distribution-lists/{list_id}/members/{member_id}/remove
# ---------------------------------------------------------------------------

@router.post("/{list_id}/members/{member_id}/remove", response_class=HTMLResponse)
async def remove_member(
    request: Request,
    list_id: UUID,
    member_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-remove a member from the distribution list."""
    sb = get_supabase()

    dist_list = (
        sb.table("distribution_lists")
        .select("*")
        .eq("id", str(list_id))
        .eq("is_active", True)
        .single()
        .execute()
        .data
    )
    if not dist_list:
        raise HTTPException(status_code=404, detail="Distribution list not found")

    if not _can_manage_members(dist_list, current_user):
        return HTMLResponse('<div class="text-sm text-red-600 p-2">Permission denied.</div>')

    # Get member info for audit log before removing
    member_resp = (
        sb.table("distribution_list_members")
        .select("id, person_id")
        .eq("id", str(member_id))
        .eq("distribution_list_id", str(list_id))
        .eq("is_active", True)
        .single()
        .execute()
    )
    if not member_resp.data:
        return HTMLResponse('<div class="text-sm text-red-600 p-2">Member not found.</div>')

    member = member_resp.data
    person = _get_person_with_org(member["person_id"])
    person_label = person["full_name"] if person else member["person_id"]

    now_str = datetime.now(timezone.utc).isoformat()

    # Soft-remove
    sb.table("distribution_list_members").update({
        "is_active": False,
        "removed_at": now_str,
        "removal_reason": "manual",
    }).eq("id", str(member_id)).execute()

    _log_field_change(
        "distribution_list", str(list_id), "member_removed",
        f"{person_label} ({member['person_id']})", None,
        current_user.id,
    )

    # Return updated members tab content
    return await _render_members_tab(request, str(list_id), current_user, dist_list)


# ---------------------------------------------------------------------------
# Helper: render members tab (reused after add/remove)
# ---------------------------------------------------------------------------

async def _render_members_tab(
    request: Request,
    list_id: str,
    current_user: CurrentUser,
    dist_list: dict,
    m_page: int = 1,
) -> HTMLResponse:
    """Render the members tab partial."""
    sb = get_supabase()
    m_page_size = 25
    m_offset = (m_page - 1) * m_page_size

    members_resp = (
        sb.table("distribution_list_members")
        .select("id, person_id, coverage_owner_id, joined_at", count="exact")
        .eq("distribution_list_id", list_id)
        .eq("is_active", True)
        .order("joined_at", desc=True)
        .range(m_offset, m_offset + m_page_size - 1)
        .execute()
    )
    members = members_resp.data or []
    members_total = members_resp.count or 0
    members_total_pages = max(1, (members_total + m_page_size - 1) // m_page_size)

    for m in members:
        person = _get_person_with_org(m["person_id"])
        if person:
            m["person_name"] = person["full_name"]
            m["person_email"] = person.get("email")
            m["person_org"] = person.get("org_name")
        else:
            m["person_name"] = "Unknown"
            m["person_email"] = None
            m["person_org"] = None
        if m.get("coverage_owner_id"):
            m["coverage_owner_name"] = _get_user_name(str(m["coverage_owner_id"]))
        else:
            m["coverage_owner_name"] = None

    context = {
        "request": request,
        "user": current_user,
        "dist_list": dist_list,
        "members": members,
        "members_total": members_total,
        "members_total_pages": members_total_pages,
        "m_page": m_page,
        "member_count": members_total,
        "can_manage": _can_manage_members(dist_list, current_user),
    }
    return templates.TemplateResponse("distribution_lists/_tab_members.html", context)

"""Documents router — file attachments linked to any entity (org, person, lead, contract)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from db.helpers import log_field_change, get_user_name, batch_resolve_users
from dependencies import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/documents", tags=["documents"])
templates = Jinja2Templates(directory="templates")

ALLOWED_ENTITY_TYPES = {"organization", "person", "lead", "contract"}


# ---------------------------------------------------------------------------
# LIST — documents for a given entity (HTMX partial)
# ---------------------------------------------------------------------------

@router.get("/for/{entity_type}/{entity_id}", response_class=HTMLResponse)
async def list_documents(
    request: Request,
    entity_type: str,
    entity_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return the documents tab partial for an entity's detail page."""
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type: {entity_type}")

    sb = get_supabase()
    resp = (
        sb.table("documents")
        .select("*")
        .eq("entity_type", entity_type)
        .eq("entity_id", entity_id)
        .eq("is_deleted", False)
        .order("uploaded_at", desc=True)
        .execute()
    )
    docs = resp.data or []

    # Resolve uploader names
    uploader_ids = [d["uploaded_by"] for d in docs if d.get("uploaded_by")]
    user_map = batch_resolve_users(uploader_ids)
    for d in docs:
        d["uploader_name"] = user_map.get(str(d.get("uploaded_by")), "Unknown")

    return templates.TemplateResponse("components/_tab_documents.html", {
        "request": request,
        "documents": docs,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "user": current_user,
        "can_upload": current_user.has_role("admin") or current_user.has_role("standard_user") or current_user.has_role("rfp_team") or current_user.has_role("bd"),
    })


# ---------------------------------------------------------------------------
# UPLOAD — add a document (URL or file reference)
# ---------------------------------------------------------------------------

@router.post("/upload", response_class=HTMLResponse)
async def upload_document(
    request: Request,
    entity_type: str = Form(...),
    entity_id: str = Form(...),
    title: str = Form(...),
    file_url: str = Form(""),
    file_type: str = Form(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Upload a document attachment to an entity."""
    require_role(current_user, ["admin", "standard_user", "rfp_team", "bd"])

    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type: {entity_type}")

    if not title.strip():
        raise HTTPException(status_code=400, detail="Document title is required")

    if not file_url.strip():
        raise HTTPException(status_code=400, detail="File URL or path is required")

    sb = get_supabase()
    doc_data = {
        "title": title.strip(),
        "file_url": file_url.strip(),
        "file_type": file_type.strip() or _infer_file_type(file_url),
        "entity_type": entity_type,
        "entity_id": entity_id,
        "uploaded_by": str(current_user.id),
    }

    resp = sb.table("documents").insert(doc_data).execute()
    if resp.data:
        log_field_change("document", str(resp.data[0]["id"]), "_created", None, "document uploaded", current_user.id)

    # Return refreshed document list
    return RedirectResponse(
        url=f"/documents/for/{entity_type}/{entity_id}",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# DELETE — soft-delete a document
# ---------------------------------------------------------------------------

@router.post("/{doc_id}/delete", response_class=HTMLResponse)
async def delete_document(
    request: Request,
    doc_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-delete a document."""
    require_role(current_user, ["admin", "standard_user", "rfp_team", "bd"])

    sb = get_supabase()
    doc = sb.table("documents").select("*").eq("id", doc_id).maybe_single().execute()
    if not doc.data:
        raise HTTPException(status_code=404, detail="Document not found")

    sb.table("documents").update({"is_deleted": True}).eq("id", doc_id).execute()
    log_field_change("document", doc_id, "is_deleted", False, True, current_user.id)

    entity_type = doc.data["entity_type"]
    entity_id = doc.data["entity_id"]

    # If HTMX, return refreshed list
    if request.headers.get("HX-Request"):
        return RedirectResponse(
            url=f"/documents/for/{entity_type}/{entity_id}",
            status_code=303,
        )
    return RedirectResponse(url=f"/{entity_type}s/{entity_id}", status_code=303)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_file_type(url: str) -> str:
    """Infer file type from URL extension."""
    url_lower = url.lower()
    for ext in (".pdf", ".docx", ".xlsx", ".pptx", ".csv", ".png", ".jpg", ".jpeg"):
        if url_lower.endswith(ext):
            return ext.lstrip(".")
    return "link"

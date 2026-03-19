"""Field definitions service — query, cache, and manage EAV field metadata."""

from typing import Optional
from uuid import UUID

from db.client import get_supabase
from db.helpers import get_reference_data


# ---------------------------------------------------------------------------
# Field definition queries
# ---------------------------------------------------------------------------

def get_field_definitions(
    entity_type: str,
    active_only: bool = True,
    section_name: Optional[str] = None,
) -> list[dict]:
    """Fetch field definitions for an entity type, ordered by section + display_order.

    Args:
        entity_type: e.g. 'organization', 'person', 'lead'
        active_only: if True, only return is_active=True fields
        section_name: optional filter for a specific section
    """
    sb = get_supabase()
    query = sb.table("field_definitions").select("*").eq("entity_type", entity_type)
    if active_only:
        query = query.eq("is_active", True)
    if section_name:
        query = query.eq("section_name", section_name)
    query = query.order("section_name").order("display_order")
    return query.execute().data or []


def get_field_definition(entity_type: str, field_name: str) -> Optional[dict]:
    """Fetch a single field definition by entity_type and field_name."""
    sb = get_supabase()
    resp = (
        sb.table("field_definitions")
        .select("*")
        .eq("entity_type", entity_type)
        .eq("field_name", field_name)
        .maybe_single()
        .execute()
    )
    return resp.data


def get_field_definitions_grouped(entity_type: str) -> dict[str, list[dict]]:
    """Return field definitions grouped by section_name.

    Returns: {"Basic Information": [field_def, ...], "Address": [...], ...}
    """
    fields = get_field_definitions(entity_type)
    grouped: dict[str, list[dict]] = {}
    for f in fields:
        section = f.get("section_name") or "Other"
        grouped.setdefault(section, []).append(f)
    return grouped


def enrich_field_definitions(fields: list[dict]) -> list[dict]:
    """Enrich field definitions with dropdown options from reference_data.

    For fields with dropdown_category set, fetches the options from reference_data.
    """
    for f in fields:
        if f.get("dropdown_category") and f["field_type"] in ("dropdown", "multi_select"):
            f["options"] = get_reference_data(f["dropdown_category"])
        elif f.get("dropdown_options"):
            f["options"] = f["dropdown_options"]
        else:
            f["options"] = []
    return fields


# ---------------------------------------------------------------------------
# EAV value storage
# ---------------------------------------------------------------------------

def save_custom_values(
    entity_type: str,
    entity_id: str,
    field_values: dict,
    field_defs: list[dict],
) -> None:
    """Save EAV field values for an entity.

    Only processes fields where storage_type='eav'.
    Uses upsert (ON CONFLICT UPDATE) for idempotent writes.
    """
    sb = get_supabase()
    eav_fields = {f["field_name"]: f for f in field_defs if f["storage_type"] == "eav"}

    for field_name, field_def in eav_fields.items():
        value = field_values.get(field_name)
        if value is None:
            # Delete existing value if cleared
            sb.table("entity_custom_values").delete().match({
                "entity_type": entity_type,
                "entity_id": entity_id,
                "field_definition_id": field_def["id"],
            }).execute()
            continue

        # Determine which value column to use based on field_type
        row = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "field_definition_id": field_def["id"],
            "value_text": None,
            "value_number": None,
            "value_date": None,
            "value_boolean": None,
            "value_json": None,
        }

        ft = field_def["field_type"]
        if ft in ("text", "textarea", "url", "email", "phone", "dropdown"):
            row["value_text"] = str(value)
        elif ft in ("number", "currency"):
            row["value_number"] = float(value) if value else None
        elif ft == "date":
            row["value_date"] = str(value) if value else None
        elif ft == "boolean":
            row["value_boolean"] = bool(value)
        elif ft in ("multi_select", "address", "calculated", "text_list"):
            row["value_json"] = value  # expects list or dict
        else:
            row["value_text"] = str(value)

        sb.table("entity_custom_values").upsert(
            row,
            on_conflict="entity_type,entity_id,field_definition_id",
        ).execute()


def load_custom_values(entity_type: str, entity_id: str) -> dict:
    """Load all EAV values for an entity, returned as {field_name: typed_value}.

    Joins with field_definitions to get field metadata for type conversion.
    """
    sb = get_supabase()
    resp = (
        sb.table("entity_custom_values")
        .select("field_definition_id, value_text, value_number, value_date, value_boolean, value_json")
        .eq("entity_type", entity_type)
        .eq("entity_id", str(entity_id))
        .execute()
    )
    if not resp.data:
        return {}

    # Build a map from field_definition_id → field_name
    fd_ids = [str(r["field_definition_id"]) for r in resp.data]
    fd_resp = (
        sb.table("field_definitions")
        .select("id, field_name, field_type")
        .in_("id", fd_ids)
        .execute()
    )
    fd_map = {str(f["id"]): f for f in (fd_resp.data or [])}

    result = {}
    for row in resp.data:
        fd = fd_map.get(str(row["field_definition_id"]))
        if not fd:
            continue
        result[fd["field_name"]] = _extract_typed_value(row, fd["field_type"])
    return result


def load_custom_values_batch(
    entity_type: str, entity_ids: list[str]
) -> dict[str, dict]:
    """Batch load EAV values for multiple entities.

    Returns: {entity_id: {field_name: typed_value, ...}, ...}
    """
    if not entity_ids:
        return {}
    sb = get_supabase()
    unique_ids = list(set(str(eid) for eid in entity_ids if eid))
    if not unique_ids:
        return {}

    resp = (
        sb.table("entity_custom_values")
        .select("entity_id, field_definition_id, value_text, value_number, value_date, value_boolean, value_json")
        .eq("entity_type", entity_type)
        .in_("entity_id", unique_ids)
        .execute()
    )
    if not resp.data:
        return {}

    # Build field definition map
    fd_ids = list(set(str(r["field_definition_id"]) for r in resp.data))
    fd_resp = (
        sb.table("field_definitions")
        .select("id, field_name, field_type")
        .in_("id", fd_ids)
        .execute()
    )
    fd_map = {str(f["id"]): f for f in (fd_resp.data or [])}

    result: dict[str, dict] = {}
    for row in resp.data:
        eid = str(row["entity_id"])
        fd = fd_map.get(str(row["field_definition_id"]))
        if not fd:
            continue
        result.setdefault(eid, {})[fd["field_name"]] = _extract_typed_value(row, fd["field_type"])
    return result


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _extract_typed_value(row: dict, field_type: str):
    """Extract the typed value from an EAV row based on field_type."""
    if field_type in ("text", "textarea", "url", "email", "phone", "dropdown"):
        return row.get("value_text")
    elif field_type in ("number", "currency"):
        return row.get("value_number")
    elif field_type == "date":
        return row.get("value_date")
    elif field_type == "boolean":
        return row.get("value_boolean")
    elif field_type in ("multi_select", "address", "calculated", "text_list"):
        return row.get("value_json")
    return row.get("value_text")

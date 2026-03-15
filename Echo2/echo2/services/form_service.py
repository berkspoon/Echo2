"""Dynamic form service — build, parse, validate, and save forms from field_definitions metadata.

Replaces the hardcoded _build_*_data_from_form(), manual validation, and per-entity form context
building in each router with a single metadata-driven system.
"""

from typing import Optional
from uuid import UUID

from db.client import get_supabase
from db.field_service import (
    get_field_definitions,
    enrich_field_definitions,
    save_custom_values,
    load_custom_values,
)
from db.helpers import audit_changes, log_field_change


# ---------------------------------------------------------------------------
# Build form context (load field defs + dropdown options + current values)
# ---------------------------------------------------------------------------

def build_form_context(
    entity_type: str,
    record: Optional[dict] = None,
    extra_context: Optional[dict] = None,
) -> dict:
    """Build context dict for rendering a dynamic form.

    Returns:
        {
            "field_defs": [...],            # flat list, enriched with options
            "sections": {"name": [fields]}, # grouped by section
            "record": {...},                # merged core + EAV values
            "entity_type": str,
        }
    """
    field_defs = get_field_definitions(entity_type, active_only=True)
    field_defs = enrich_field_definitions(field_defs)

    # Group by section, preserving order
    sections: dict[str, list[dict]] = {}
    for fd in field_defs:
        section = fd.get("section_name") or "Other"
        sections.setdefault(section, []).append(fd)

    # Merge EAV values into the record dict
    merged_record = dict(record) if record else {}
    if record and record.get("id"):
        eav_values = load_custom_values(entity_type, str(record["id"]))
        merged_record.update(eav_values)

    ctx = {
        "field_defs": field_defs,
        "sections": sections,
        "record": merged_record,
        "entity_type": entity_type,
    }
    if extra_context:
        ctx.update(extra_context)
    return ctx


# ---------------------------------------------------------------------------
# Parse form data (extract values from submitted form using field_defs)
# ---------------------------------------------------------------------------

def parse_form_data(entity_type: str, form_data, field_defs: list[dict]) -> dict:
    """Parse submitted form data using field definitions metadata.

    Replaces per-router _build_*_data_from_form() functions.

    Args:
        entity_type: e.g. 'task', 'activity'
        form_data: FastAPI form object (has .get() and .getlist())
        field_defs: list of field definition dicts

    Returns:
        dict of {field_name: parsed_value}
    """
    parsed = {}

    for fd in field_defs:
        fname = fd["field_name"]
        ftype = fd["field_type"]

        if ftype == "boolean":
            parsed[fname] = form_data.get(fname) == "on"

        elif ftype == "multi_select":
            values = form_data.getlist(fname) if hasattr(form_data, "getlist") else []
            parsed[fname] = list(values) if values else None

        elif ftype in ("number", "currency"):
            raw = (form_data.get(fname) or "").strip()
            if raw:
                try:
                    parsed[fname] = float(raw.replace(",", ""))
                except (ValueError, TypeError):
                    parsed[fname] = None
            else:
                parsed[fname] = None

        elif ftype == "date":
            raw = (form_data.get(fname) or "").strip()
            parsed[fname] = raw if raw else None

        elif ftype == "lookup":
            raw = (form_data.get(fname) or "").strip()
            parsed[fname] = raw if raw else None

        else:
            # text, textarea, url, email, phone, dropdown
            raw = (form_data.get(fname) or "").strip()
            parsed[fname] = raw if raw else None

    return parsed


# ---------------------------------------------------------------------------
# Validate form data
# ---------------------------------------------------------------------------

def validate_form_data(
    entity_type: str,
    data: dict,
    field_defs: list[dict],
    record: Optional[dict] = None,
) -> list[str]:
    """Validate parsed form data against field definitions.

    Checks required fields, validation_rules (min/max), and returns error messages.

    Args:
        entity_type: the entity type
        data: parsed form data from parse_form_data()
        field_defs: list of field definitions
        record: existing record (for edit — used to evaluate visibility rules)

    Returns:
        List of error message strings. Empty list = valid.
    """
    errors = []
    # Use data itself as form state for visibility evaluation
    form_state = dict(record or {})
    form_state.update(data)

    for fd in field_defs:
        fname = fd["field_name"]
        value = data.get(fname)

        # Skip validation for fields hidden by visibility rules
        if not _is_field_visible(fd, form_state):
            continue

        # Required check
        if fd.get("is_required"):
            if value is None or value == "" or value == []:
                errors.append(f"{fd['display_name']} is required.")

        # Validation rules
        rules = fd.get("validation_rules") or {}
        if value is not None and value != "":
            if "min" in rules and isinstance(value, (int, float)):
                if value < rules["min"]:
                    errors.append(f"{fd['display_name']} must be at least {rules['min']}.")
            if "max" in rules and isinstance(value, (int, float)):
                if value > rules["max"]:
                    errors.append(f"{fd['display_name']} must be at most {rules['max']}.")

    return errors


def _is_field_visible(fd: dict, form_state: dict) -> bool:
    """Evaluate visibility_rules to determine if a field should be shown/validated.

    Supports:
        - {"when": "field", "equals": value}
        - {"when": "field", "not_equals": value}
        - {"when": "field", "in": [values]}
        - {"when": "field", "not_in": [values]}
        - {"min_stage": N} (lead stage gating)
        - {"lead_type": "type"} (lead type scoping)
    """
    rules = fd.get("visibility_rules")
    if not rules:
        return True

    # Lead type scoping
    if "lead_type" in rules:
        current_type = form_state.get("lead_type", "advisory")
        required_type = rules["lead_type"]
        if isinstance(required_type, list):
            if current_type not in required_type:
                return False
        elif current_type != required_type:
            return False

    # Stage gating
    if "min_stage" in rules:
        stage_order = _get_stage_order(form_state)
        if stage_order < rules["min_stage"]:
            return False

    # Conditional visibility
    if "when" in rules:
        trigger_field = rules["when"]
        current_value = form_state.get(trigger_field)

        if "equals" in rules:
            expected = rules["equals"]
            if _normalize_for_compare(current_value) != _normalize_for_compare(expected):
                return False

        if "not_equals" in rules:
            unexpected = rules["not_equals"]
            if _normalize_for_compare(current_value) == _normalize_for_compare(unexpected):
                return False

        if "in" in rules:
            allowed = rules["in"]
            if _normalize_for_compare(current_value) not in [_normalize_for_compare(v) for v in allowed]:
                return False

        if "not_in" in rules:
            disallowed = rules["not_in"]
            if _normalize_for_compare(current_value) in [_normalize_for_compare(v) for v in disallowed]:
                return False

    return True


def _normalize_for_compare(value):
    """Normalize a value for comparison (handle booleans, strings, None)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.lower().strip()
        if low in ("true", "on", "yes", "1"):
            return True
        if low in ("false", "off", "no", "0"):
            return False
        return low
    return value


# Stage order mapping for leads
_ADVISORY_STAGE_ORDER = {
    "exploratory": 1,
    "radar": 2,
    "focus": 3,
    "verbal_mandate": 4,
    "won": 5,
    "lost_dropped_out": 5,
    "lost_selected_other": 5,
    "lost_nobody_hired": 5,
}

_FUNDRAISE_STAGE_ORDER = {
    "target_identified": 1,
    "intro_scheduled": 2,
    "initial_meeting_complete": 3,
    "ddq_materials_sent": 4,
    "due_diligence": 5,
    "ic_review": 6,
    "soft_circle": 7,
    "legal_docs": 8,
    "closed": 9,
    "declined": 9,
}


def _get_stage_order(form_state: dict) -> int:
    """Get the numeric stage order from form state for visibility gating."""
    lead_type = form_state.get("lead_type", "advisory")
    rating = form_state.get("rating", "")

    if lead_type in ("fundraise", "product"):
        return _FUNDRAISE_STAGE_ORDER.get(rating, 0)
    return _ADVISORY_STAGE_ORDER.get(rating, 0)


# ---------------------------------------------------------------------------
# Save record (split core columns vs EAV, write both, audit)
# ---------------------------------------------------------------------------

def save_record(
    entity_type: str,
    data: dict,
    field_defs: list[dict],
    changed_by: UUID,
    record_id: Optional[str] = None,
) -> dict:
    """Save a record — inserts or updates, handling core columns and EAV split.

    For CREATE: inserts a new row with core column values, then saves EAV values.
    For UPDATE: updates existing row with core column values, audits changes, then saves EAV.

    Args:
        entity_type: e.g. 'task', 'activity'
        data: parsed + validated form data
        field_defs: list of field definitions
        changed_by: UUID of the user making the change
        record_id: if provided, this is an UPDATE; otherwise CREATE

    Returns:
        The saved record dict (from Supabase response)
    """
    sb = get_supabase()
    table_name = _entity_table(entity_type)

    # Split into core column data and EAV data
    core_data = {}
    eav_data = {}

    fd_map = {fd["field_name"]: fd for fd in field_defs}

    for fname, value in data.items():
        fd = fd_map.get(fname)
        if not fd:
            # Unknown field — include as core (might be a special field like lead_type)
            core_data[fname] = value
            continue
        if fd["storage_type"] == "core_column":
            core_data[fname] = value
        else:
            eav_data[fname] = value

    if record_id:
        # UPDATE
        old_resp = sb.table(table_name).select("*").eq("id", record_id).maybe_single().execute()
        old_record = old_resp.data or {}

        if core_data:
            sb.table(table_name).update(core_data).eq("id", record_id).execute()

        # Audit core changes
        audit_changes(entity_type, record_id, old_record, core_data, changed_by)

        # Save EAV values
        if eav_data:
            save_custom_values(entity_type, record_id, eav_data, field_defs)

        # Return updated record
        final_resp = sb.table(table_name).select("*").eq("id", record_id).maybe_single().execute()
        return final_resp.data or {}
    else:
        # CREATE
        core_data["created_by"] = str(changed_by)
        resp = sb.table(table_name).insert(core_data).execute()
        new_record = resp.data[0] if resp.data else {}
        new_id = new_record.get("id")

        # Save EAV values
        if new_id and eav_data:
            save_custom_values(entity_type, str(new_id), eav_data, field_defs)

        return new_record


def _entity_table(entity_type: str) -> str:
    """Map entity_type to database table name."""
    return {
        "organization": "organizations",
        "person": "people",
        "lead": "leads",
        "activity": "activities",
        "contract": "contracts",
        "task": "tasks",
    }.get(entity_type, entity_type + "s")


# ---------------------------------------------------------------------------
# Utility: get users list for lookup fields
# ---------------------------------------------------------------------------

def get_users_for_lookup() -> list[dict]:
    """Fetch active users for lookup/assigned_to dropdowns."""
    sb = get_supabase()
    resp = sb.table("users").select("id, display_name, email").eq("is_active", True).order("display_name").execute()
    return resp.data or []

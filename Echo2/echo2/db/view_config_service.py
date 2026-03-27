"""View configuration service — query, cache, and manage admin-configurable view settings."""

import json
import time
from typing import Any

from db.client import get_supabase


# ── Cache with TTL ────────────────────────────────────────────────────────
# Each entry: (config_value, timestamp).  Expires after _CACHE_TTL seconds.
# Safe for multi-worker: stale reads last at most _CACHE_TTL seconds.

_CACHE_TTL = 60  # seconds
_cache: dict[str, tuple[Any, float]] = {}


def get_view_config(view_key: str, default: Any = None) -> Any:
    """Return the config JSONB for a view_key, falling back to *default* if no row exists."""
    now = time.monotonic()
    cached = _cache.get(view_key)
    if cached and (now - cached[1]) < _CACHE_TTL:
        return cached[0]

    sb = get_supabase()
    resp = (
        sb.table("view_configurations")
        .select("config")
        .eq("view_key", view_key)
        .maybe_single()
        .execute()
    )
    if resp and resp.data:
        _cache[view_key] = (resp.data["config"], now)
        return resp.data["config"]
    return default


def get_all_view_configs() -> list[dict]:
    """Return all view configuration rows, ordered by category then display_name."""
    sb = get_supabase()
    resp = (
        sb.table("view_configurations")
        .select("*")
        .order("category")
        .order("display_name")
        .execute()
    )
    return resp.data or []


def get_view_config_row(view_key: str) -> dict | None:
    """Return the full row for a view_key, or None."""
    sb = get_supabase()
    resp = (
        sb.table("view_configurations")
        .select("*")
        .eq("view_key", view_key)
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None


# ── Validation ────────────────────────────────────────────────────────────

_EXPECTED_SHAPES = {
    "dashboard_columns": lambda c: (
        isinstance(c.get("columns"), list)
        and all(isinstance(col, dict) and "key" in col and "label" in col for col in c["columns"])
    ),
    "option_list": lambda c: (
        isinstance(c.get("options"), list)
        and all(isinstance(o, dict) and "value" in o and "label" in o for o in c["options"])
    ),
    "grid_columns": lambda c: (
        isinstance(c.get("columns"), list)
        and all(isinstance(col, str) for col in c["columns"])
    ),
    "dl_filter": lambda c: (
        isinstance(c.get("include_field_types"), list)
    ),
}


def detect_config_type(config: dict) -> str:
    """Detect the editor/config type from the config shape."""
    if isinstance(config.get("columns"), list):
        if config["columns"] and isinstance(config["columns"][0], dict):
            return "dashboard_columns"
        return "grid_columns"
    if isinstance(config.get("options"), list):
        return "option_list"
    if "person_fields" in config or "org_fields" in config:
        return "dl_filter"
    return "json"


def validate_config(config: dict, config_type: str = None) -> str | None:
    """Validate config shape.  Returns error string or None if valid."""
    if not isinstance(config, dict):
        return "Config must be a JSON object"

    if not config_type:
        config_type = detect_config_type(config)

    validator = _EXPECTED_SHAPES.get(config_type)
    if validator and not validator(config):
        if config_type == "dashboard_columns":
            return 'Expected {"columns": [{"key": "...", "label": "...", ...}, ...]}'
        if config_type == "option_list":
            return 'Expected {"options": [{"value": "...", "label": "..."}, ...]}'
        if config_type == "grid_columns":
            return 'Expected {"columns": ["field_name_1", "field_name_2", ...]}'
        if config_type == "dl_filter":
            return 'Expected {"person_fields": [...], "org_fields": [...], "include_field_types": [...]}'
    return None


# ── Save + audit ──────────────────────────────────────────────────────────

def save_view_config(view_key: str, config: dict, updated_by: str) -> None:
    """Update the config JSONB for a view_key.  Busts cache + writes audit log."""
    sb = get_supabase()

    # Load old config for audit diff
    old_row = get_view_config_row(view_key)
    old_config = old_row["config"] if old_row else {}

    sb.table("view_configurations").update({
        "config": config,
        "updated_by": updated_by,
    }).eq("view_key", view_key).execute()

    # Audit log
    if json.dumps(old_config, sort_keys=True) != json.dumps(config, sort_keys=True):
        sb.table("audit_log").insert({
            "record_type": "view_configuration",
            "record_id": str(old_row["id"]) if old_row else view_key,
            "field_name": "config",
            "old_value": json.dumps(old_config),
            "new_value": json.dumps(config),
            "changed_by": updated_by,
        }).execute()

    # Bust cache
    _cache.pop(view_key, None)

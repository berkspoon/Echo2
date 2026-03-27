"""View configuration service — query, cache, and manage admin-configurable view settings."""

from typing import Any, Optional

from db.client import get_supabase


# Simple in-process cache keyed by view_key
_cache: dict[str, dict] = {}


def get_view_config(view_key: str, default: Any = None) -> Any:
    """Return the config JSONB for a view_key, falling back to *default* if no row exists."""
    if view_key in _cache:
        return _cache[view_key]

    sb = get_supabase()
    resp = (
        sb.table("view_configurations")
        .select("config")
        .eq("view_key", view_key)
        .maybe_single()
        .execute()
    )
    if resp and resp.data:
        _cache[view_key] = resp.data["config"]
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


def save_view_config(view_key: str, config: dict, updated_by: str) -> None:
    """Update the config JSONB for a view_key.  Busts the cache entry."""
    sb = get_supabase()
    sb.table("view_configurations").update({
        "config": config,
        "updated_by": updated_by,
    }).eq("view_key", view_key).execute()

    # Bust cache
    _cache.pop(view_key, None)

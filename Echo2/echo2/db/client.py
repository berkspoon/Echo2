"""Supabase client initialisation."""

from supabase import create_client, Client
from config import get_settings


_client: Client | None = None


def get_supabase() -> Client:
    """Return a cached Supabase client instance."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client

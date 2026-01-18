"""Supabase database client."""

from typing import Optional
from supabase import create_client, Client

from src.config import get_settings


_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """Get the Supabase client singleton instance."""
    global _supabase_client
    if _supabase_client is None:
        settings = get_settings()
        _supabase_client = create_client(
            settings.supabase_url,
            settings.supabase_key
        )
    return _supabase_client

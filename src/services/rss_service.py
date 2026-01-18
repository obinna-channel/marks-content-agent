"""Service for managing RSS sources and items."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from supabase import Client

from src.models.content import (
    RSSSource,
    RSSSourceCreate,
    RSSItem,
    RSSItemCreate,
    AccountCategory,
)
from .database import get_supabase_client


class RSSService:
    """Service for RSS sources and items CRUD operations."""

    def __init__(self, db: Optional[Client] = None):
        self.db = db or get_supabase_client()
        self.sources_table = "rss_sources"
        self.items_table = "rss_items"

    # --- RSS Sources ---

    async def create_source(self, source: RSSSourceCreate) -> RSSSource:
        """Create a new RSS source."""
        data = source.model_dump()
        data["category"] = data["category"].value if data["category"] else None

        result = self.db.table(self.sources_table).insert(data).execute()
        return RSSSource.model_validate(result.data[0])

    async def get_source_by_id(self, source_id: UUID) -> Optional[RSSSource]:
        """Get RSS source by ID."""
        result = (
            self.db.table(self.sources_table)
            .select("*")
            .eq("id", str(source_id))
            .single()
            .execute()
        )
        if result.data:
            return RSSSource.model_validate(result.data)
        return None

    async def get_active_sources(
        self,
        category: Optional[AccountCategory] = None,
    ) -> List[RSSSource]:
        """Get all active RSS sources."""
        query = (
            self.db.table(self.sources_table)
            .select("*")
            .eq("is_active", True)
        )

        if category:
            query = query.eq("category", category.value)

        result = query.execute()
        return [RSSSource.model_validate(item) for item in result.data]

    async def get_sources_due_for_check(self) -> List[RSSSource]:
        """Get RSS sources that are due for checking based on poll interval."""
        sources = await self.get_active_sources()
        due_sources = []

        for source in sources:
            if source.last_checked_at is None:
                due_sources.append(source)
            else:
                next_check = source.last_checked_at + timedelta(
                    minutes=source.poll_interval_minutes
                )
                if datetime.now(timezone.utc) >= next_check:
                    due_sources.append(source)

        return due_sources

    async def update_source_last_checked(self, source_id: UUID) -> RSSSource:
        """Update the last checked timestamp for a source."""
        result = (
            self.db.table(self.sources_table)
            .update({"last_checked_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", str(source_id))
            .execute()
        )
        return RSSSource.model_validate(result.data[0])

    # --- RSS Items ---

    async def create_item(self, item: RSSItemCreate) -> RSSItem:
        """Create a new RSS item."""
        data = item.model_dump()
        data["source_id"] = str(data["source_id"])

        result = self.db.table(self.items_table).insert(data).execute()
        return RSSItem.model_validate(result.data[0])

    async def get_item_by_guid(self, guid: str) -> Optional[RSSItem]:
        """Get RSS item by GUID (for deduplication)."""
        result = (
            self.db.table(self.items_table)
            .select("*")
            .eq("guid", guid)
            .single()
            .execute()
        )
        if result.data:
            return RSSItem.model_validate(result.data)
        return None

    async def item_exists(self, guid: str) -> bool:
        """Check if an RSS item already exists (for deduplication)."""
        result = (
            self.db.table(self.items_table)
            .select("id")
            .eq("guid", guid)
            .execute()
        )
        return len(result.data) > 0

    async def get_unnotified_items(self, min_score: float = 0.7) -> List[RSSItem]:
        """Get RSS items that haven't been notified to Slack yet."""
        result = (
            self.db.table(self.items_table)
            .select("*")
            .eq("slack_notified", False)
            .gte("relevance_score", min_score)
            .order("fetched_at", desc=True)
            .execute()
        )
        return [RSSItem.model_validate(item) for item in result.data]

    async def get_recent_items(
        self,
        hours: int = 24,
        source_id: Optional[UUID] = None,
    ) -> List[RSSItem]:
        """Get recently fetched RSS items."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = (
            self.db.table(self.items_table)
            .select("*")
            .gte("fetched_at", cutoff.isoformat())
            .order("fetched_at", desc=True)
        )

        if source_id:
            query = query.eq("source_id", str(source_id))

        result = query.execute()
        return [RSSItem.model_validate(item) for item in result.data]

    async def update_item_relevance(
        self,
        item_id: UUID,
        relevance_score: float,
        suggested_content: Optional[str] = None,
    ) -> RSSItem:
        """Update relevance scoring for an RSS item."""
        update_data = {"relevance_score": relevance_score}
        if suggested_content:
            update_data["suggested_content"] = suggested_content

        result = (
            self.db.table(self.items_table)
            .update(update_data)
            .eq("id", str(item_id))
            .execute()
        )
        return RSSItem.model_validate(result.data[0])

    async def mark_item_notified(self, item_id: UUID) -> RSSItem:
        """Mark an RSS item as notified to Slack."""
        result = (
            self.db.table(self.items_table)
            .update({"slack_notified": True})
            .eq("id", str(item_id))
            .execute()
        )
        return RSSItem.model_validate(result.data[0])

    async def mark_item_actioned(self, item_id: UUID) -> RSSItem:
        """Mark an RSS item as actioned (user posted about it)."""
        result = (
            self.db.table(self.items_table)
            .update({"actioned": True})
            .eq("id", str(item_id))
            .execute()
        )
        return RSSItem.model_validate(result.data[0])

    async def cleanup_old_items(self, days: int = 30) -> int:
        """Delete RSS items older than specified days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = (
            self.db.table(self.items_table)
            .delete()
            .lt("fetched_at", cutoff.isoformat())
            .execute()
        )
        return len(result.data)

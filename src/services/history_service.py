"""Service for managing content history."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from supabase import Client

from src.models.content import (
    ContentHistory,
    ContentHistoryCreate,
    ContentType,
    ContentPillar,
)
from .database import get_supabase_client


class HistoryService:
    """Service for content history CRUD operations."""

    def __init__(self, db: Optional[Client] = None):
        self.db = db or get_supabase_client()
        self.table = "content_history"

    async def create(self, content: ContentHistoryCreate) -> ContentHistory:
        """Create a new content history record."""
        data = content.model_dump()
        # Convert enum to string
        data["type"] = data["type"].value if data["type"] else None
        data["pillar"] = data["pillar"].value if data["pillar"] else None

        result = self.db.table(self.table).insert(data).execute()
        return ContentHistory.model_validate(result.data[0])

    async def get_by_id(self, content_id: UUID) -> Optional[ContentHistory]:
        """Get content by ID."""
        result = (
            self.db.table(self.table)
            .select("*")
            .eq("id", str(content_id))
            .single()
            .execute()
        )
        if result.data:
            return ContentHistory.model_validate(result.data)
        return None

    async def get_recent(
        self,
        days: int = 30,
        content_type: Optional[ContentType] = None,
        pillar: Optional[ContentPillar] = None,
        limit: int = 100,
    ) -> List[ContentHistory]:
        """Get recent content history."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        query = (
            self.db.table(self.table)
            .select("*")
            .gte("created_at", cutoff.isoformat())
            .order("created_at", desc=True)
            .limit(limit)
        )

        if content_type:
            query = query.eq("type", content_type.value)
        if pillar:
            query = query.eq("pillar", pillar.value)

        result = query.execute()
        return [ContentHistory.model_validate(item) for item in result.data]

    async def get_recent_topics(self, days: int = 30) -> List[str]:
        """Get list of recently used topics."""
        recent = await self.get_recent(days=days)
        return list(set(item.topic for item in recent if item.topic))

    async def get_recent_angles(self, days: int = 30) -> List[str]:
        """Get list of recently used angles."""
        recent = await self.get_recent(days=days)
        return list(set(item.angle for item in recent if item.angle))

    async def mark_as_posted(
        self,
        content_id: UUID,
        twitter_post_id: Optional[str] = None,
    ) -> ContentHistory:
        """Mark content as posted."""
        update_data = {
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        if twitter_post_id:
            update_data["twitter_post_id"] = twitter_post_id

        result = (
            self.db.table(self.table)
            .update(update_data)
            .eq("id", str(content_id))
            .execute()
        )
        return ContentHistory.model_validate(result.data[0])

    async def update_engagement(
        self,
        content_id: UUID,
        engagement_data: dict,
    ) -> ContentHistory:
        """Update engagement data for posted content."""
        result = (
            self.db.table(self.table)
            .update({"engagement_data": engagement_data})
            .eq("id", str(content_id))
            .execute()
        )
        return ContentHistory.model_validate(result.data[0])

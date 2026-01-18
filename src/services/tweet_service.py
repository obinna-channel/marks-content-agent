"""Service for managing monitored tweets."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from supabase import Client

from src.models.content import (
    MonitoredTweet,
    MonitoredTweetCreate,
    RelevanceType,
)
from .database import get_supabase_client


class TweetService:
    """Service for monitored tweets CRUD operations."""

    def __init__(self, db: Optional[Client] = None):
        self.db = db or get_supabase_client()
        self.table = "monitored_tweets"

    async def create(self, tweet: MonitoredTweetCreate) -> MonitoredTweet:
        """Create a new monitored tweet record."""
        data = tweet.model_dump()
        data["account_id"] = str(data["account_id"])
        # Serialize datetime to ISO string for Supabase
        if data.get("tweet_created_at"):
            data["tweet_created_at"] = data["tweet_created_at"].isoformat()

        result = self.db.table(self.table).insert(data).execute()
        return MonitoredTweet.model_validate(result.data[0])

    async def get_by_id(self, tweet_id: UUID) -> Optional[MonitoredTweet]:
        """Get tweet by internal ID."""
        result = (
            self.db.table(self.table)
            .select("*")
            .eq("id", str(tweet_id))
            .single()
            .execute()
        )
        if result.data:
            return MonitoredTweet.model_validate(result.data)
        return None

    async def get_by_tweet_id(self, twitter_tweet_id: str) -> Optional[MonitoredTweet]:
        """Get tweet by Twitter tweet ID (for deduplication)."""
        result = (
            self.db.table(self.table)
            .select("*")
            .eq("tweet_id", twitter_tweet_id)
            .single()
            .execute()
        )
        if result.data:
            return MonitoredTweet.model_validate(result.data)
        return None

    async def exists(self, twitter_tweet_id: str) -> bool:
        """Check if a tweet already exists (for deduplication)."""
        result = (
            self.db.table(self.table)
            .select("id")
            .eq("tweet_id", twitter_tweet_id)
            .execute()
        )
        return len(result.data) > 0

    async def get_unnotified(
        self,
        relevance_type: Optional[RelevanceType] = None,
        min_score: float = 0.7,
    ) -> List[MonitoredTweet]:
        """Get tweets that haven't been notified to Slack yet."""
        query = (
            self.db.table(self.table)
            .select("*")
            .eq("slack_notified", False)
            .gte("relevance_score", min_score)
            .order("fetched_at", desc=True)
        )

        if relevance_type:
            query = query.eq("relevance_type", relevance_type.value)

        result = query.execute()
        return [MonitoredTweet.model_validate(item) for item in result.data]

    async def get_recent(
        self,
        hours: int = 24,
        account_id: Optional[UUID] = None,
    ) -> List[MonitoredTweet]:
        """Get recently fetched tweets."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = (
            self.db.table(self.table)
            .select("*")
            .gte("fetched_at", cutoff.isoformat())
            .order("fetched_at", desc=True)
        )

        if account_id:
            query = query.eq("account_id", str(account_id))

        result = query.execute()
        return [MonitoredTweet.model_validate(item) for item in result.data]

    async def update_relevance(
        self,
        tweet_id: UUID,
        relevance_score: float,
        relevance_type: RelevanceType,
        suggested_content: Optional[str] = None,
    ) -> MonitoredTweet:
        """Update relevance scoring for a tweet."""
        update_data = {
            "relevance_score": relevance_score,
            "relevance_type": relevance_type.value,
        }
        if suggested_content:
            update_data["suggested_content"] = suggested_content

        result = (
            self.db.table(self.table)
            .update(update_data)
            .eq("id", str(tweet_id))
            .execute()
        )
        return MonitoredTweet.model_validate(result.data[0])

    async def mark_notified(self, tweet_id: UUID) -> MonitoredTweet:
        """Mark a tweet as notified to Slack."""
        result = (
            self.db.table(self.table)
            .update({"slack_notified": True})
            .eq("id", str(tweet_id))
            .execute()
        )
        return MonitoredTweet.model_validate(result.data[0])

    async def mark_actioned(self, tweet_id: UUID) -> MonitoredTweet:
        """Mark a tweet as actioned (user posted about it)."""
        result = (
            self.db.table(self.table)
            .update({"actioned": True})
            .eq("id", str(tweet_id))
            .execute()
        )
        return MonitoredTweet.model_validate(result.data[0])

    async def cleanup_old(self, days: int = 30) -> int:
        """Delete tweets older than specified days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = (
            self.db.table(self.table)
            .delete()
            .lt("fetched_at", cutoff.isoformat())
            .execute()
        )
        return len(result.data)

"""Service for fetching and managing voice samples from reference accounts."""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

from supabase import Client

from src.models.content import (
    MonitoredAccount,
    VoiceSample,
    VoiceSampleCreate,
)
from src.integrations.twitter import TwitterClient, get_twitter_client
from .database import get_supabase_client
from .account_service import AccountService


class VoiceSamplerService:
    """Service for fetching and managing voice samples."""

    def __init__(
        self,
        db: Optional[Client] = None,
        twitter_client: Optional[TwitterClient] = None,
        account_service: Optional[AccountService] = None,
    ):
        self.db = db or get_supabase_client()
        self.twitter = twitter_client or get_twitter_client()
        self.account_service = account_service or AccountService()
        self.table = "voice_samples"

    async def create_sample(self, sample: VoiceSampleCreate) -> VoiceSample:
        """Create a new voice sample."""
        data = sample.model_dump()
        data["account_id"] = str(data["account_id"])
        # Serialize datetime to ISO string for Supabase
        if data.get("tweet_created_at"):
            data["tweet_created_at"] = data["tweet_created_at"].isoformat()

        result = self.db.table(self.table).insert(data).execute()
        return VoiceSample.model_validate(result.data[0])

    async def sample_exists(self, tweet_id: str) -> bool:
        """Check if a sample already exists (for deduplication)."""
        result = (
            self.db.table(self.table)
            .select("id")
            .eq("tweet_id", tweet_id)
            .execute()
        )
        return len(result.data) > 0

    async def get_samples_for_account(
        self,
        account_id: UUID,
        limit: int = 20,
    ) -> List[VoiceSample]:
        """Get voice samples for a specific account."""
        result = (
            self.db.table(self.table)
            .select("*")
            .eq("account_id", str(account_id))
            .eq("is_active", True)
            .order("likes", desc=True)  # Prioritize high-engagement tweets
            .limit(limit)
            .execute()
        )
        return [VoiceSample.model_validate(item) for item in result.data]

    async def get_all_active_samples(
        self,
        limit_per_account: int = 10,
        pillar: Optional[str] = None,
    ) -> Dict[str, List[VoiceSample]]:
        """Get active samples grouped by account handle, optionally filtered by pillar."""
        # Get voice reference accounts (filtered by pillar if specified)
        accounts = await self.account_service.get_voice_references(pillar=pillar)

        samples_by_account = {}
        for account in accounts:
            samples = await self.get_samples_for_account(
                account_id=account.id,
                limit=limit_per_account,
            )
            if samples:
                samples_by_account[account.twitter_handle] = samples

        return samples_by_account

    async def fetch_samples_for_account(
        self,
        account: MonitoredAccount,
        max_tweets: int = 30,
    ) -> List[VoiceSample]:
        """Fetch new voice samples from Twitter for an account."""
        # Get Twitter user ID if we don't have it
        twitter_id = account.twitter_id
        if not twitter_id:
            user_info = await self.twitter.get_user_by_username(account.twitter_handle)
            if not user_info:
                print(f"Could not find Twitter user @{account.twitter_handle}")
                return []
            twitter_id = user_info["id"]

        # Fetch recent tweets
        tweets = await self.twitter.get_user_tweets(
            user_id=twitter_id,
            max_results=max_tweets,
        )

        new_samples = []
        for tweet in tweets:
            # Skip if we already have this tweet
            if await self.sample_exists(tweet["id"]):
                continue

            # Skip very short tweets (likely not good examples)
            if len(tweet["text"]) < 50:
                continue

            # Skip tweets that are mostly links/mentions
            text = tweet["text"]
            if text.count("http") > 3 or text.count("@") > 5:
                continue

            # Create the sample
            sample_create = VoiceSampleCreate(
                account_id=account.id,
                account_handle=account.twitter_handle,
                tweet_id=tweet["id"],
                content=tweet["text"],
                tweet_created_at=datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00")) if tweet["created_at"] else None,
                likes=tweet.get("likes", 0),
                retweets=tweet.get("retweets", 0),
            )

            try:
                sample = await self.create_sample(sample_create)
                new_samples.append(sample)
            except Exception as e:
                print(f"Error creating voice sample: {e}")
                continue

        return new_samples

    async def refresh_all_samples(self) -> Dict[str, int]:
        """Refresh voice samples for all reference accounts."""
        accounts = await self.account_service.get_voice_references()

        results = {}
        for account in accounts:
            try:
                samples = await self.fetch_samples_for_account(account)
                results[account.twitter_handle] = len(samples)
            except Exception as e:
                print(f"Error refreshing samples for @{account.twitter_handle}: {e}")
                results[account.twitter_handle] = 0

        return results

    async def get_samples_for_prompt(
        self,
        samples_per_account: int = 5,
        pillar: Optional[str] = None,
    ) -> str:
        """Get formatted voice samples for inclusion in generation prompts."""
        samples_by_account = await self.get_all_active_samples(
            limit_per_account=samples_per_account,
            pillar=pillar,
        )

        if not samples_by_account:
            return ""

        lines = ["## Voice Reference Examples\n"]
        lines.append("Write in a style inspired by these examples:\n")

        for handle, samples in samples_by_account.items():
            lines.append(f"\n**@{handle}:**")
            for sample in samples[:samples_per_account]:
                # Clean up the content for display
                content = sample.content.replace("\n", " ").strip()
                if len(content) > 280:
                    content = content[:277] + "..."
                lines.append(f'- "{content}"')

        return "\n".join(lines)

    async def cleanup_old_samples(self, days: int = 90) -> int:
        """Delete samples older than specified days."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        result = (
            self.db.table(self.table)
            .delete()
            .lt("fetched_at", cutoff.isoformat())
            .execute()
        )
        return len(result.data)

    async def deactivate_sample(self, sample_id: UUID) -> VoiceSample:
        """Deactivate a sample (if it's not a good example)."""
        result = (
            self.db.table(self.table)
            .update({"is_active": False})
            .eq("id", str(sample_id))
            .execute()
        )
        return VoiceSample.model_validate(result.data[0])

    async def get_sample_stats(self) -> Dict[str, Any]:
        """Get statistics about voice samples."""
        accounts = await self.account_service.get_voice_references()

        stats = {
            "total_reference_accounts": len(accounts),
            "accounts": {},
            "total_samples": 0,
        }

        for account in accounts:
            samples = await self.get_samples_for_account(account.id, limit=100)
            stats["accounts"][account.twitter_handle] = len(samples)
            stats["total_samples"] += len(samples)

        return stats


# Singleton instance
_voice_sampler: Optional[VoiceSamplerService] = None


def get_voice_sampler() -> VoiceSamplerService:
    """Get the voice sampler singleton instance."""
    global _voice_sampler
    if _voice_sampler is None:
        _voice_sampler = VoiceSamplerService()
    return _voice_sampler

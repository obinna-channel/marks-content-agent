"""Service for managing monitored Twitter accounts."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from supabase import Client

from src.models.content import (
    MonitoredAccount,
    MonitoredAccountCreate,
    AccountCategory,
)
from .database import get_supabase_client


class AccountService:
    """Service for monitored accounts CRUD operations."""

    def __init__(self, db: Optional[Client] = None):
        self.db = db or get_supabase_client()
        self.table = "monitored_accounts"

    async def create(self, account: MonitoredAccountCreate) -> MonitoredAccount:
        """Create a new monitored account."""
        data = account.model_dump()
        data["category"] = data["category"].value if data["category"] else None

        result = self.db.table(self.table).insert(data).execute()
        return MonitoredAccount.model_validate(result.data[0])

    async def get_by_id(self, account_id: UUID) -> Optional[MonitoredAccount]:
        """Get account by ID."""
        result = (
            self.db.table(self.table)
            .select("*")
            .eq("id", str(account_id))
            .single()
            .execute()
        )
        if result.data:
            return MonitoredAccount.model_validate(result.data)
        return None

    async def get_by_handle(self, handle: str) -> Optional[MonitoredAccount]:
        """Get account by Twitter handle."""
        # Normalize handle (remove @ if present)
        handle = handle.lstrip("@").lower()

        result = (
            self.db.table(self.table)
            .select("*")
            .ilike("twitter_handle", handle)
            .limit(1)
            .execute()
        )
        if result.data and len(result.data) > 0:
            return MonitoredAccount.model_validate(result.data[0])
        return None

    async def get_active(
        self,
        category: Optional[AccountCategory] = None,
        priority: Optional[int] = None,
    ) -> List[MonitoredAccount]:
        """Get all active monitored accounts."""
        query = (
            self.db.table(self.table)
            .select("*")
            .eq("is_active", True)
            .order("priority", desc=False)
        )

        if category:
            query = query.eq("category", category.value)
        if priority:
            query = query.eq("priority", priority)

        result = query.execute()
        return [MonitoredAccount.model_validate(item) for item in result.data]

    async def get_all_active_handles(self) -> List[str]:
        """Get list of all active Twitter handles."""
        accounts = await self.get_active()
        return [acc.twitter_handle for acc in accounts]

    async def update_last_checked(
        self,
        account_id: UUID,
        last_tweet_id: Optional[str] = None,
    ) -> MonitoredAccount:
        """Update the last checked timestamp for an account."""
        update_data = {
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
        }
        if last_tweet_id:
            update_data["last_tweet_id"] = last_tweet_id

        result = (
            self.db.table(self.table)
            .update(update_data)
            .eq("id", str(account_id))
            .execute()
        )
        return MonitoredAccount.model_validate(result.data[0])

    async def deactivate(self, account_id: UUID) -> MonitoredAccount:
        """Deactivate a monitored account."""
        result = (
            self.db.table(self.table)
            .update({"is_active": False})
            .eq("id", str(account_id))
            .execute()
        )
        return MonitoredAccount.model_validate(result.data[0])

    async def activate(self, account_id: UUID) -> MonitoredAccount:
        """Activate a monitored account."""
        result = (
            self.db.table(self.table)
            .update({"is_active": True})
            .eq("id", str(account_id))
            .execute()
        )
        return MonitoredAccount.model_validate(result.data[0])

    async def bulk_create(
        self,
        accounts: List[MonitoredAccountCreate],
    ) -> List[MonitoredAccount]:
        """Create multiple accounts at once."""
        data = []
        for account in accounts:
            item = account.model_dump()
            item["category"] = item["category"].value if item["category"] else None
            data.append(item)

        result = self.db.table(self.table).insert(data).execute()
        return [MonitoredAccount.model_validate(item) for item in result.data]

    async def get_voice_references(
        self,
        pillar: Optional[str] = None,
    ) -> List[MonitoredAccount]:
        """Get all active voice reference accounts, optionally filtered by pillar."""
        query = (
            self.db.table(self.table)
            .select("*")
            .eq("is_active", True)
            .eq("is_voice_reference", True)
        )
        result = query.execute()
        accounts = [MonitoredAccount.model_validate(item) for item in result.data]

        # Filter by pillar if specified
        if pillar:
            accounts = [
                acc for acc in accounts
                if pillar in acc.voice_pillars or len(acc.voice_pillars) == 0
            ]

        return accounts

    async def set_voice_reference(
        self,
        account_id: UUID,
        is_voice_reference: bool = True,
        voice_pillars: Optional[List[str]] = None,
    ) -> MonitoredAccount:
        """Set or unset an account as a voice reference."""
        update_data = {"is_voice_reference": is_voice_reference}
        if voice_pillars is not None:
            update_data["voice_pillars"] = voice_pillars
        result = (
            self.db.table(self.table)
            .update(update_data)
            .eq("id", str(account_id))
            .execute()
        )
        return MonitoredAccount.model_validate(result.data[0])

    async def update_voice_pillars(
        self,
        account_id: UUID,
        voice_pillars: List[str],
    ) -> MonitoredAccount:
        """Update the voice pillars for an account."""
        result = (
            self.db.table(self.table)
            .update({"voice_pillars": voice_pillars})
            .eq("id", str(account_id))
            .execute()
        )
        return MonitoredAccount.model_validate(result.data[0])

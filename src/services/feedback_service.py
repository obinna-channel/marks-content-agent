"""Service for managing voice feedback."""

import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from supabase import Client

from src.models.content import ContentPillar
from .database import get_supabase_client


class FeedbackService:
    """Service for voice feedback CRUD operations."""

    def __init__(self, db: Optional[Client] = None):
        self.db = db or get_supabase_client()
        self.table = "voice_feedback"

    async def create(
        self,
        pillar: ContentPillar,
        original_content: str,
        feedback_text: Optional[str] = None,
        slack_thread_ts: Optional[str] = None,
        final_content: Optional[str] = None,
        learnings: Optional[List[str]] = None,
    ) -> dict:
        """Create a new feedback record.

        Args:
            pillar: Content pillar this feedback applies to
            original_content: First draft content
            feedback_text: Direct feedback text (for simple feedback)
            slack_thread_ts: Reference to Slack thread
            final_content: Final draft after revisions
            learnings: List of extracted style preferences
        """
        data = {
            "pillar": pillar.value,
            "original_content": original_content,
            "slack_thread_ts": slack_thread_ts,
        }

        if feedback_text:
            data["feedback_text"] = feedback_text
        if final_content:
            data["final_content"] = final_content
        if learnings:
            data["learnings"] = json.dumps(learnings)

        result = self.db.table(self.table).insert(data).execute()
        return result.data[0]

    async def get_recent_feedback(
        self,
        pillar: Optional[ContentPillar] = None,
        days: int = 30,
        limit: int = 10,
    ) -> List[dict]:
        """Get recent feedback, optionally filtered by pillar."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        query = (
            self.db.table(self.table)
            .select("*")
            .gte("created_at", cutoff.isoformat())
            .order("created_at", desc=True)
            .limit(limit)
        )

        if pillar:
            query = query.eq("pillar", pillar.value)

        result = query.execute()
        return result.data

    async def get_feedback_for_prompt(
        self,
        pillar: Optional[ContentPillar] = None,
        limit: int = 5,
    ) -> str:
        """Get formatted feedback string for inclusion in generation prompts."""
        feedback_items = await self.get_recent_feedback(pillar=pillar, limit=limit)

        if not feedback_items:
            return ""

        lines = ["## Style Preferences (learned from feedback)\n"]
        lines.append("Apply these preferences to your content:\n")

        for item in feedback_items:
            pillar_name = item.get("pillar", "general").replace("_", " ").title()

            # Handle learnings array (new format)
            learnings = item.get("learnings")
            if learnings:
                # Parse JSON if it's a string
                if isinstance(learnings, str):
                    try:
                        learnings = json.loads(learnings)
                    except json.JSONDecodeError:
                        learnings = []

                for learning in learnings:
                    lines.append(f"- **{pillar_name}**: {learning}")

            # Handle direct feedback_text (legacy/simple format)
            elif item.get("feedback_text"):
                lines.append(f"- **{pillar_name}**: {item['feedback_text']}")

        # Return empty if only header was added
        if len(lines) <= 2:
            return ""

        return "\n".join(lines)


# Singleton instance
_feedback_service: Optional[FeedbackService] = None


def get_feedback_service() -> FeedbackService:
    """Get the feedback service singleton instance."""
    global _feedback_service
    if _feedback_service is None:
        _feedback_service = FeedbackService()
    return _feedback_service

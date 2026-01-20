"""RSS feed monitor for polling news sources."""

import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from email.utils import parsedate_to_datetime

import feedparser

from src.config import get_settings
from src.models.content import (
    RSSSource,
    RSSItemCreate,
    SlackNewsAlert,
    AccountCategory,
)
from src.services.rss_service import RSSService
from src.services.feedback_service import FeedbackService, get_feedback_service
from src.integrations.slack import SlackClient, get_slack_client
from src.agent.relevance import RelevanceScorer, get_relevance_scorer


class RSSMonitor:
    """Monitor RSS feeds for relevant news."""

    def __init__(
        self,
        slack_client: Optional[SlackClient] = None,
        rss_service: Optional[RSSService] = None,
        relevance_scorer: Optional[RelevanceScorer] = None,
        feedback_service: Optional[FeedbackService] = None,
    ):
        self.slack = slack_client or get_slack_client()
        self.rss_service = rss_service or RSSService()
        self.relevance_scorer = relevance_scorer or get_relevance_scorer()
        self.feedback_service = feedback_service or get_feedback_service()
        self.settings = get_settings()

    def _parse_published_date(self, entry: dict) -> Optional[datetime]:
        """Parse the published date from an RSS entry."""
        # Try different date fields
        for field in ["published", "updated", "created"]:
            if field in entry:
                try:
                    # feedparser often provides a parsed version
                    parsed_field = f"{field}_parsed"
                    if parsed_field in entry and entry[parsed_field]:
                        from time import mktime
                        return datetime.fromtimestamp(mktime(entry[parsed_field]))
                    # Try parsing the string
                    return parsedate_to_datetime(entry[field])
                except Exception:
                    continue
        return None

    def _format_time_ago(self, timestamp: Optional[datetime]) -> str:
        """Format a timestamp as 'X min ago'."""
        if not timestamp:
            return "recently"

        now = datetime.now(timezone.utc)
        # Handle timezone-aware datetimes
        if timestamp.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=None)

        diff = now - timestamp
        minutes = int(diff.total_seconds() / 60)

        if minutes < 0:
            return "just now"
        if minutes < 60:
            return f"{minutes} min ago"

        hours = int(minutes / 60)
        if hours < 24:
            return f"{hours} hours ago"

        days = int(hours / 24)
        return f"{days} days ago"

    async def fetch_feed(self, source: RSSSource) -> List[Dict[str, Any]]:
        """
        Fetch and parse an RSS feed.

        Args:
            source: The RSS source to fetch

        Returns:
            List of new items from the feed
        """
        try:
            # feedparser is synchronous, but it's fast enough
            feed = feedparser.parse(source.url)

            if feed.bozo and not feed.entries:
                print(f"Error parsing feed {source.name}: {feed.bozo_exception}")
                return []

            new_items = []
            for entry in feed.entries:
                # Get GUID for deduplication
                guid = entry.get("id") or entry.get("link") or entry.get("title")
                if not guid:
                    continue

                # Check if we've already processed this item
                if await self.rss_service.item_exists(guid):
                    continue

                # Extract item data
                item_data = {
                    "guid": guid,
                    "title": entry.get("title", "Untitled"),
                    "url": entry.get("link", ""),
                    "summary": entry.get("summary") or entry.get("description", ""),
                    "published_at": self._parse_published_date(entry),
                    "source": source,
                }

                new_items.append(item_data)

            return new_items

        except Exception as e:
            print(f"Error fetching feed {source.name}: {e}")
            return []

    async def check_source(self, source: RSSSource) -> List[Dict[str, Any]]:
        """
        Check a single RSS source for new items.

        Args:
            source: The source to check

        Returns:
            List of new items stored
        """
        items = await self.fetch_feed(source)
        stored_items = []

        for item_data in items:
            # Filter by keywords if configured
            if source.keywords:
                content = f"{item_data['title']} {item_data['summary']}".lower()
                if not any(kw.lower() in content for kw in source.keywords):
                    continue

            # Store the item
            item_create = RSSItemCreate(
                source_id=source.id,
                guid=item_data["guid"],
                title=item_data["title"],
                url=item_data["url"],
                summary=item_data["summary"][:1000] if item_data["summary"] else None,
                published_at=item_data["published_at"],
            )

            try:
                stored_item = await self.rss_service.create_item(item_create)
                stored_items.append({
                    "item": stored_item,
                    "source": source,
                })
            except Exception as e:
                print(f"Error storing RSS item: {e}")
                continue

        # Update last checked timestamp
        await self.rss_service.update_source_last_checked(source.id)

        return stored_items

    async def check_all_sources(self) -> List[Dict[str, Any]]:
        """
        Check all active RSS sources for new items.

        Returns:
            List of all new items found
        """
        sources = await self.rss_service.get_active_sources()
        all_items = []

        for source in sources:
            try:
                items = await self.check_source(source)
                all_items.extend(items)

                # Small delay between sources
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Error checking source {source.name}: {e}")
                continue

        return all_items

    async def check_due_sources(self) -> List[Dict[str, Any]]:
        """
        Check only sources that are due for checking based on poll interval.

        Returns:
            List of new items found
        """
        sources = await self.rss_service.get_sources_due_for_check()
        all_items = []

        for source in sources:
            try:
                items = await self.check_source(source)
                all_items.extend(items)
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Error checking source {source.name}: {e}")
                continue

        return all_items

    async def process_item(self, item_data: Dict[str, Any]) -> bool:
        """
        Process an RSS item: score relevance and notify if relevant.

        Args:
            item_data: Dict with item and source

        Returns:
            True if item was relevant and notified
        """
        item = item_data["item"]
        source = item_data["source"]

        # Score relevance
        score_result = await self.relevance_scorer.score_article(
            title=item.title,
            summary=item.summary or "",
            source_name=source.name,
            category=source.category,
            url=item.url,
        )

        # Update item with relevance data
        await self.rss_service.update_item_relevance(
            item_id=item.id,
            relevance_score=score_result["score"],
            suggested_content=score_result.get("suggested_content"),
        )

        # Check if meets threshold
        if score_result["score"] < self.settings.relevance_threshold:
            return False

        # Get voice feedback and generate news reaction with it
        voice_feedback = await self.feedback_service.get_feedback_for_prompt()
        suggested_content = await self.relevance_scorer.generate_news_reaction(
            source=source.name,
            headline=item.title,
            summary=item.summary or "",
            market_context=score_result.get("reasoning", ""),
            voice_feedback=voice_feedback,
        )

        # Skip if no content generated
        if not suggested_content or not suggested_content.strip():
            return False

        # Send Slack notification
        time_ago = self._format_time_ago(item.published_at)

        alert = SlackNewsAlert(
            source_type="rss",
            source_name=source.name,
            headline=item.title,
            link=item.url,
            category=source.category,
            time_ago=time_ago,
            suggested_post=suggested_content,
            urgency="high" if score_result["score"] >= 0.9 else "normal",
        )

        await self.slack.send_news_alert(alert)
        await self.rss_service.mark_item_notified(item.id)

        return True

    async def run_check_cycle(self) -> Dict[str, Any]:
        """
        Run a full check cycle: fetch items, score, and notify.

        Returns:
            Summary of the check cycle
        """
        summary = {
            "sources_checked": 0,
            "items_found": 0,
            "items_relevant": 0,
            "notifications_sent": 0,
        }

        # Check due sources
        sources = await self.rss_service.get_sources_due_for_check()
        summary["sources_checked"] = len(sources)

        all_items = await self.check_due_sources()
        summary["items_found"] = len(all_items)

        # Process each item
        for item_data in all_items:
            try:
                was_relevant = await self.process_item(item_data)
                if was_relevant:
                    summary["items_relevant"] += 1
                    summary["notifications_sent"] += 1
            except Exception as e:
                print(f"Error processing RSS item: {e}")
                continue

        return summary


# Singleton instance
_rss_monitor: Optional[RSSMonitor] = None


def get_rss_monitor() -> RSSMonitor:
    """Get the RSS monitor singleton instance."""
    global _rss_monitor
    if _rss_monitor is None:
        _rss_monitor = RSSMonitor()
    return _rss_monitor

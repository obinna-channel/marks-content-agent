"""Slack client for sending notifications."""

from typing import Optional, List
from datetime import datetime, timezone

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.config import get_settings
from src.models.content import (
    SlackNewsAlert,
    SlackReplyOpportunity,
    WeeklyBatch,
    AccountCategory,
)


class SlackClient:
    """Client for sending Slack notifications."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        channel_id: Optional[str] = None,
    ):
        settings = get_settings()
        self.bot_token = bot_token or settings.slack_bot_token
        self.channel_id = channel_id or settings.slack_channel_id
        self._client: Optional[WebClient] = None

    def _get_client(self) -> WebClient:
        """Get or create the Slack client."""
        if self._client is None:
            self._client = WebClient(token=self.bot_token)
        return self._client

    def _format_time_ago(self, timestamp: datetime) -> str:
        """Format a timestamp as 'X min ago' or 'X hours ago'."""
        now = datetime.now(timezone.utc)
        diff = now - timestamp

        minutes = int(diff.total_seconds() / 60)
        if minutes < 60:
            return f"{minutes} min ago"

        hours = int(minutes / 60)
        if hours < 24:
            return f"{hours} hours ago"

        days = int(hours / 24)
        return f"{days} days ago"

    async def send_message(self, text: str, blocks: Optional[List[dict]] = None) -> Optional[str]:
        """
        Send a message to the configured channel.

        Args:
            text: Fallback text for notifications
            blocks: Rich message blocks

        Returns:
            Message timestamp (ts) if successful, None otherwise
        """
        try:
            client = self._get_client()
            response = client.chat_postMessage(
                channel=self.channel_id,
                text=text,
                blocks=blocks,
            )
            return response.get("ts")
        except SlackApiError as e:
            print(f"Slack API error: {e.response['error']}")
            return None

    async def send_news_alert(self, alert: SlackNewsAlert) -> Optional[str]:
        """
        Send a news alert to Slack.

        Args:
            alert: News alert data

        Returns:
            Message timestamp (ts) if successful, None otherwise
        """
        # Build emoji based on source type
        emoji = "🗞️" if alert.source_type == "twitter" else "📰"

        # Build source line
        if alert.source_type == "twitter":
            source_line = f"@{alert.source_handle} just posted:"
        else:
            source_line = f"{alert.source_name}:"

        # Build metadata line
        meta_parts = [f"Category: {alert.category.value.replace('_', ' ').title()}"]
        if alert.follower_count:
            meta_parts.append(f"Followers: {alert.follower_count:,}")
        meta_parts.append(alert.time_ago)
        meta_line = " | ".join(meta_parts)

        # Build urgency indicator
        urgency_line = ""
        if alert.urgency == "high":
            urgency_line = "\n\n⚡ *React fast — this is breaking news*"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} News Alert",
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{source_line}*\n\"{alert.headline}\""
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": meta_line
                    }
                ]
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📝 *Suggested post:*\n```{alert.suggested_post}```{urgency_line}"
                }
            },
        ]

        # Add link if available
        if alert.link:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"<{alert.link}|View source>"
                    }
                ]
            })

        return await self.send_message(
            text=f"{emoji} News Alert: {alert.headline}",
            blocks=blocks,
        )

    async def send_reply_opportunity(self, opportunity: SlackReplyOpportunity) -> Optional[str]:
        """
        Send a reply opportunity alert to Slack.

        Args:
            opportunity: Reply opportunity data

        Returns:
            Message timestamp (ts) if successful, None otherwise
        """
        # Build metadata line
        meta_parts = [f"Followers: {opportunity.follower_count:,}"]
        if opportunity.likes:
            meta_parts.append(f"Likes: {opportunity.likes:,}")
        meta_parts.append(opportunity.time_ago)
        meta_line = " | ".join(meta_parts)

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "💬 Reply Opportunity",
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*@{opportunity.account_handle} just posted:*\n\"{opportunity.tweet_content}\""
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": meta_line
                    }
                ]
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📝 *Suggested reply:*\n```{opportunity.suggested_reply}```"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"⚡ Post within 30 min for best visibility | <https://twitter.com/{opportunity.account_handle}/status/{opportunity.tweet_id}|View tweet>"
                    }
                ]
            },
        ]

        return await self.send_message(
            text=f"💬 Reply Opportunity: @{opportunity.account_handle}",
            blocks=blocks,
        )

    async def send_weekly_batch(self, batch: WeeklyBatch) -> bool:
        """
        Send the weekly content batch to Slack.

        Args:
            batch: Weekly batch data

        Returns:
            True if successful
        """
        # Format date range
        date_range = f"{batch.week_start.strftime('%b %d')} - {batch.week_end.strftime('%b %d')}"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📅 Weekly Content Batch ({date_range})",
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Here are your content drafts for the week. Copy any draft and post when ready."
                }
            },
            {"type": "divider"},
        ]

        # Add each day's content
        for item in batch.items:
            pillar_display = item.pillar.value.replace("_", " ").title()
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{item.day.title()} - {pillar_display}*\n_{item.topic}_\n```{item.content}```"
                }
            })

        result = await self.send_message(
            text=f"📅 Weekly Content Batch ({date_range})",
            blocks=blocks,
        )
        return result is not None

    async def send_daily_digest(
        self,
        news_count: int,
        reply_opportunities: int,
        high_priority_count: int,
        posts_made: int,
        pending_items: List[str],
    ) -> bool:
        """
        Send a daily digest summary to Slack.

        Args:
            news_count: Number of news stories covered
            reply_opportunities: Total reply opportunities
            high_priority_count: High priority opportunities
            posts_made: Posts made today
            pending_items: List of pending content items

        Returns:
            True if successful
        """
        today = datetime.now(timezone.utc).strftime("%b %d")

        pending_text = "\n".join(f"• {item}" for item in pending_items) if pending_items else "None"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📊 Daily Digest - {today}",
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*News covered:*\n{news_count} stories"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Reply opportunities:*\n{reply_opportunities} ({high_priority_count} high priority)"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Posts made:*\n{posts_made}"
                    },
                ]
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Pending:*\n{pending_text}"
                }
            },
        ]

        result = await self.send_message(
            text=f"📊 Daily Digest - {today}",
            blocks=blocks,
        )
        return result is not None


# Singleton instance
_slack_client: Optional[SlackClient] = None


def get_slack_client() -> SlackClient:
    """Get the Slack client singleton instance."""
    global _slack_client
    if _slack_client is None:
        _slack_client = SlackClient()
    return _slack_client

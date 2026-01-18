"""Content generation using Claude API."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

import anthropic

from src.config import get_settings
from src.models.content import (
    ContentHistoryCreate,
    ContentType,
    ContentPillar,
    WeeklyBatch,
    WeeklyBatchItem,
)
from src.services.history_service import HistoryService
from src.services.marks_api import MarksAPIClient, get_marks_client
from src.services.voice_sampler import VoiceSamplerService, get_voice_sampler
from src.services.feedback_service import FeedbackService, get_feedback_service
from .prompts import get_weekly_batch_prompt
from .variety import VarietyManager, get_variety_manager


class ContentGenerator:
    """Generate content for Marks Exchange."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        history_service: Optional[HistoryService] = None,
        marks_client: Optional[MarksAPIClient] = None,
        variety_manager: Optional[VarietyManager] = None,
        voice_sampler: Optional[VoiceSamplerService] = None,
        feedback_service: Optional[FeedbackService] = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.anthropic_api_key
        self._client: Optional[anthropic.Anthropic] = None
        self.history_service = history_service or HistoryService()
        self.marks_client = marks_client or get_marks_client()
        self.variety_manager = variety_manager or get_variety_manager()
        self.voice_sampler = voice_sampler or get_voice_sampler()
        self.feedback_service = feedback_service or get_feedback_service()

    def _get_client(self) -> anthropic.Anthropic:
        """Get or create the Anthropic client."""
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _get_marks_context(self) -> str:
        """Load Marks Exchange context from file."""
        try:
            context_path = Path(__file__).parent.parent.parent / "context" / "marks_context.md"
            if context_path.exists():
                return context_path.read_text()
            return ""
        except Exception as e:
            print(f"Error loading marks context: {e}")
            return ""

    async def _get_market_data_string(self) -> str:
        """Fetch and format market data for prompt."""
        try:
            summary = await self.marks_client.get_weekly_summary()

            lines = ["## Current Market Data\n"]
            for pair, data in summary.get("pairs", {}).items():
                price = data.get("current_price")
                change = data.get("weekly_change_pct")
                high = data.get("weekly_high")
                low = data.get("weekly_low")

                if price:
                    lines.append(f"**{pair}**:")
                    lines.append(f"  - Current: {price:,.2f}")
                    if change is not None:
                        direction = "+" if change >= 0 else ""
                        lines.append(f"  - Weekly change: {direction}{change:.2f}%")
                    if high and low:
                        lines.append(f"  - Range: {low:,.2f} - {high:,.2f}")
                    lines.append("")

            return "\n".join(lines) if len(lines) > 1 else "Market data unavailable"

        except Exception as e:
            print(f"Error fetching market data: {e}")
            return "Market data unavailable - please add manually"

    async def _get_platform_metrics_string(self) -> str:
        """Fetch and format platform metrics for prompt."""
        try:
            metrics = await self.marks_client.get_platform_metrics()
            if not metrics:
                return "Platform metrics unavailable"

            lines = ["## Platform Metrics\n"]
            if metrics.get("weekly_volume"):
                lines.append(f"- Weekly volume: ${metrics['weekly_volume']:,.0f}")
            if metrics.get("active_users"):
                lines.append(f"- Active users: {metrics['active_users']:,}")
            if metrics.get("total_trades"):
                lines.append(f"- Total trades: {metrics['total_trades']:,}")

            return "\n".join(lines) if len(lines) > 1 else "Platform metrics unavailable"

        except Exception as e:
            print(f"Error fetching platform metrics: {e}")
            return "Platform metrics unavailable - please add manually"

    async def _get_avoid_topics_string(self) -> str:
        """Get topics and angles to avoid from recent history."""
        avoid_topics = await self.variety_manager.get_topics_to_avoid()
        avoid_angles = await self.variety_manager.get_angles_to_avoid()

        lines = []
        if avoid_topics:
            lines.append("**Recent topics (don't repeat):**")
            for topic in avoid_topics[:10]:
                lines.append(f"- {topic}")
            lines.append("")

        if avoid_angles:
            lines.append("**Recent angles (don't repeat):**")
            for angle in avoid_angles[:10]:
                lines.append(f"- {angle}")

        return "\n".join(lines) if lines else "No recent topics to avoid"

    async def _get_voice_samples_string(self, pillar: Optional[str] = None) -> str:
        """Get formatted voice samples for prompt, optionally filtered by pillar."""
        try:
            return await self.voice_sampler.get_samples_for_prompt(
                samples_per_account=5,
                pillar=pillar,
            )
        except Exception as e:
            print(f"Error fetching voice samples: {e}")
            return ""

    async def _get_feedback_string(self, pillar: Optional[ContentPillar] = None) -> str:
        """Get stored feedback for prompt."""
        try:
            return await self.feedback_service.get_feedback_for_prompt(
                pillar=pillar,
                limit=5,
            )
        except Exception as e:
            print(f"Error fetching feedback: {e}")
            return ""

    async def generate_weekly_batch(
        self,
        recent_news: str = "",
        voice_feedback: str = "",
    ) -> WeeklyBatch:
        """
        Generate a week's worth of content.

        Args:
            recent_news: Recent news headlines for context
            voice_feedback: Voice preferences from feedback

        Returns:
            WeeklyBatch with 7 content items
        """
        # Calculate week dates
        today = datetime.now(timezone.utc)
        # Find next Monday
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        week_start = today + timedelta(days=days_until_monday)
        week_end = week_start + timedelta(days=6)

        # Gather context
        market_data = await self._get_market_data_string()
        platform_metrics = await self._get_platform_metrics_string()
        avoid_topics = await self._get_avoid_topics_string()
        voice_samples = await self._get_voice_samples_string()

        # Combine voice feedback with voice samples
        combined_voice = voice_feedback
        if voice_samples:
            combined_voice = f"{voice_samples}\n\n{voice_feedback}" if voice_feedback else voice_samples

        # Build prompt
        system_prompt, user_prompt = get_weekly_batch_prompt(
            week_start=week_start.strftime("%B %d"),
            week_end=week_end.strftime("%B %d, %Y"),
            market_data=market_data,
            platform_metrics=platform_metrics,
            recent_news=recent_news or "No recent news provided",
            avoid_topics=avoid_topics,
            voice_feedback=combined_voice,
        )

        try:
            client = self._get_client()
            response = client.messages.create(
                model="claude-opus-4-5-20251101",
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            response_text = response.content[0].text

            # Extract JSON from response (handle markdown code blocks)
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            items_data = json.loads(response_text.strip())

            # Convert to WeeklyBatchItem objects
            items = []
            for item in items_data:
                pillar = ContentPillar(item["pillar"])
                batch_item = WeeklyBatchItem(
                    day=item["day"],
                    pillar=pillar,
                    topic=item["topic"],
                    content=item["content"],
                )
                items.append(batch_item)

                # Store in history
                await self.history_service.create(
                    ContentHistoryCreate(
                        type=ContentType.WEEKLY_POST,
                        pillar=pillar,
                        topic=item["topic"],
                        angle=item.get("angle", ""),
                        content=item["content"],
                    )
                )

            return WeeklyBatch(
                week_start=week_start,
                week_end=week_end,
                items=items,
            )

        except json.JSONDecodeError as e:
            print(f"Error parsing weekly batch response: {e}")
            raise ValueError(f"Failed to parse content generation response: {e}")
        except Exception as e:
            print(f"Error generating weekly batch: {e}")
            raise

    async def generate_single_post(
        self,
        pillar: ContentPillar,
        topic_hint: Optional[str] = None,
        voice_feedback: str = "",
    ) -> Dict[str, Any]:
        """
        Generate a single post for a specific pillar.

        Args:
            pillar: The content pillar
            topic_hint: Optional topic suggestion
            voice_feedback: Voice preferences

        Returns:
            Dict with topic and content
        """
        marks_context = self._get_marks_context()
        market_data = await self._get_market_data_string()
        avoid_topics = await self._get_avoid_topics_string()
        # Get voice samples filtered by this pillar
        voice_samples = await self._get_voice_samples_string(pillar=pillar.value)
        # Get stored feedback for this pillar
        stored_feedback = await self._get_feedback_string(pillar=pillar)

        # Build voice section
        voice_section = ""
        if voice_samples:
            voice_section = f"\n{voice_samples}\n"
        if stored_feedback:
            voice_section += f"\n{stored_feedback}\n"
        if voice_feedback:
            voice_section += f"\n{voice_feedback}\n"

        prompt = f"""Generate a single {pillar.value.replace('_', ' ')} post for Marks Exchange.

{marks_context}

{market_data}
{voice_section}
Topics to avoid: {avoid_topics}

{f'Topic hint: {topic_hint}' if topic_hint else 'Choose an engaging topic.'}

Return JSON: {{"topic": "...", "angle": "...", "content": "..."}}"""

        try:
            client = self._get_client()
            response = client.messages.create(
                model="claude-opus-4-5-20251101",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text

            # Extract JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            result = json.loads(response_text.strip())

            # Store in history
            await self.history_service.create(
                ContentHistoryCreate(
                    type=ContentType.WEEKLY_POST,
                    pillar=pillar,
                    topic=result["topic"],
                    angle=result.get("angle", ""),
                    content=result["content"],
                )
            )

            return result

        except Exception as e:
            print(f"Error generating single post: {e}")
            raise


# Singleton instance
_content_generator: Optional[ContentGenerator] = None


def get_content_generator() -> ContentGenerator:
    """Get the content generator singleton instance."""
    global _content_generator
    if _content_generator is None:
        _content_generator = ContentGenerator()
    return _content_generator

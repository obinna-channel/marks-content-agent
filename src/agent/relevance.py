"""Relevance scoring for tweets and articles using Claude API."""

import json
from typing import Optional, Dict, Any

import anthropic

from src.config import get_settings, RELEVANCE_KEYWORDS
from src.models.content import AccountCategory, RelevanceType
from .prompts import get_relevance_prompt, get_news_reaction_prompt, get_reply_prompt


class RelevanceScorer:
    """Score content for relevance and generate suggested responses."""

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.anthropic_api_key
        self._client: Optional[anthropic.Anthropic] = None

    def _get_client(self) -> anthropic.Anthropic:
        """Get or create the Anthropic client."""
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _quick_keyword_check(self, content: str) -> bool:
        """Quick check if content contains any relevant keywords."""
        content_lower = content.lower()
        return any(kw.lower() in content_lower for kw in RELEVANCE_KEYWORDS)

    async def score_tweet(
        self,
        tweet_text: str,
        account_handle: str,
        account_category: AccountCategory,
        follower_count: Optional[int] = None,
        likes: int = 0,
        retweets: int = 0,
    ) -> Dict[str, Any]:
        """
        Score a tweet for relevance and generate suggested content.

        Args:
            tweet_text: The tweet content
            account_handle: Twitter handle
            account_category: Category of the account
            follower_count: Number of followers
            likes: Number of likes on the tweet
            retweets: Number of retweets

        Returns:
            Dict with score, type, reasoning, and suggested_content
        """
        # Quick keyword filter - skip Claude API if clearly irrelevant
        if not self._quick_keyword_check(tweet_text):
            return {
                "score": 0.1,
                "type": RelevanceType.SKIP.value,
                "reasoning": "No relevant keywords found",
                "suggested_content": None,
            }

        # Build engagement info string
        engagement_parts = []
        if likes:
            engagement_parts.append(f"{likes:,} likes")
        if retweets:
            engagement_parts.append(f"{retweets:,} retweets")
        engagement_info = ", ".join(engagement_parts) if engagement_parts else "N/A"

        # Get prompts
        system_prompt, user_prompt = get_relevance_prompt(
            content=tweet_text,
            source_type="Twitter",
            account_handle=account_handle,
            category=account_category.value.replace("_", " ").title(),
            follower_count=follower_count or 0,
            engagement_info=engagement_info,
        )

        try:
            client = self._get_client()
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            # Parse JSON response
            response_text = response.content[0].text
            result = json.loads(response_text)

            return {
                "score": float(result.get("score", 0)),
                "type": result.get("type", RelevanceType.SKIP.value),
                "reasoning": result.get("reasoning", ""),
                "suggested_content": result.get("suggested_content"),
            }

        except json.JSONDecodeError as e:
            print(f"Error parsing relevance response: {e}")
            print(f"Raw response was: {response_text[:500] if response_text else 'EMPTY'}")
            return {
                "score": 0.5,
                "type": RelevanceType.SKIP.value,
                "reasoning": "Failed to parse response",
                "suggested_content": None,
            }
        except Exception as e:
            print(f"Error scoring tweet: {e}", flush=True)
            return {
                "score": 0.0,
                "type": RelevanceType.SKIP.value,
                "reasoning": f"Error: {str(e)}",
                "suggested_content": None,
            }

    async def score_article(
        self,
        title: str,
        summary: str,
        source_name: str,
        category: AccountCategory,
        url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Score an RSS article for relevance.

        Args:
            title: Article title
            summary: Article summary/description
            source_name: Name of the RSS source
            category: Category of the source
            url: Article URL

        Returns:
            Dict with score, type, reasoning, and suggested_content
        """
        content = f"{title}\n\n{summary}" if summary else title

        # Quick keyword filter
        if not self._quick_keyword_check(content):
            return {
                "score": 0.1,
                "type": RelevanceType.SKIP.value,
                "reasoning": "No relevant keywords found",
                "suggested_content": None,
            }

        # Get prompts
        system_prompt, user_prompt = get_relevance_prompt(
            content=content,
            source_type="RSS Article",
            account_handle=source_name,
            category=category.value.replace("_", " ").title(),
            follower_count=0,
            engagement_info="N/A",
        )

        try:
            client = self._get_client()
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            response_text = response.content[0].text
            result = json.loads(response_text)

            return {
                "score": float(result.get("score", 0)),
                "type": result.get("type", RelevanceType.SKIP.value),
                "reasoning": result.get("reasoning", ""),
                "suggested_content": result.get("suggested_content"),
            }

        except json.JSONDecodeError as e:
            print(f"Error parsing relevance response: {e}")
            return {
                "score": 0.5,
                "type": RelevanceType.SKIP.value,
                "reasoning": "Failed to parse response",
                "suggested_content": None,
            }
        except Exception as e:
            print(f"Error scoring article: {e}")
            return {
                "score": 0.0,
                "type": RelevanceType.SKIP.value,
                "reasoning": f"Error: {str(e)}",
                "suggested_content": None,
            }

    async def generate_news_reaction(
        self,
        source: str,
        headline: str,
        summary: str,
        market_context: str,
        voice_feedback: str = "",
    ) -> Optional[str]:
        """
        Generate a news reaction post.

        Args:
            source: Source name (e.g., "CBN", "Reuters")
            headline: News headline
            summary: News summary
            market_context: Current market context
            voice_feedback: Voice preferences from feedback

        Returns:
            Generated post text or None if failed
        """
        system_prompt, user_prompt = get_news_reaction_prompt(
            source=source,
            headline=headline,
            summary=summary,
            market_context=market_context,
            voice_feedback=voice_feedback,
        )

        try:
            client = self._get_client()
            response = client.messages.create(
                model="claude-opus-4-5-20251101",
                max_tokens=512,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            return response.content[0].text.strip()

        except Exception as e:
            print(f"Error generating news reaction: {e}")
            return None

    async def generate_reply(
        self,
        account_handle: str,
        follower_count: int,
        tweet_content: str,
        account_context: str,
        topic: str,
        voice_feedback: str = "",
    ) -> Optional[str]:
        """
        Generate a reply to a tweet.

        Args:
            account_handle: Handle of account being replied to
            follower_count: Their follower count
            tweet_content: Content of their tweet
            account_context: Context about the account
            topic: What the conversation is about
            voice_feedback: Voice preferences from feedback

        Returns:
            Generated reply text or None if failed
        """
        system_prompt, user_prompt = get_reply_prompt(
            account_handle=account_handle,
            follower_count=follower_count,
            tweet_content=tweet_content,
            account_context=account_context,
            topic=topic,
            voice_feedback=voice_feedback,
        )

        try:
            client = self._get_client()
            response = client.messages.create(
                model="claude-opus-4-5-20251101",
                max_tokens=256,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            return response.content[0].text.strip()

        except Exception as e:
            print(f"Error generating reply: {e}")
            return None


# Singleton instance
_relevance_scorer: Optional[RelevanceScorer] = None


def get_relevance_scorer() -> RelevanceScorer:
    """Get the relevance scorer singleton instance."""
    global _relevance_scorer
    if _relevance_scorer is None:
        _relevance_scorer = RelevanceScorer()
    return _relevance_scorer

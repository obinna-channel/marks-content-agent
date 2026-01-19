"""Twitter monitor for polling accounts and detecting relevant tweets."""

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from src.config import get_settings
from src.models.content import (
    MonitoredAccount,
    MonitoredTweetCreate,
    RelevanceType,
    SlackNewsAlert,
    SlackReplyOpportunity,
    AccountCategory,
)
from src.services.account_service import AccountService
from src.services.tweet_service import TweetService
from src.integrations.twitter import TwitterClient, get_twitter_client
from src.integrations.slack import SlackClient, get_slack_client


class TwitterMonitor:
    """Monitor Twitter accounts for relevant content."""

    def __init__(
        self,
        twitter_client: Optional[TwitterClient] = None,
        slack_client: Optional[SlackClient] = None,
        account_service: Optional[AccountService] = None,
        tweet_service: Optional[TweetService] = None,
    ):
        self.twitter = twitter_client or get_twitter_client()
        self.slack = slack_client or get_slack_client()
        self.account_service = account_service or AccountService()
        self.tweet_service = tweet_service or TweetService()
        self.settings = get_settings()

    def _format_time_ago(self, timestamp: datetime) -> str:
        """Format a timestamp as 'X min ago'."""
        now = datetime.now(timezone.utc)
        # Ensure timestamp is timezone-aware (assume UTC if naive)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        diff = now - timestamp

        minutes = int(diff.total_seconds() / 60)
        if minutes < 60:
            return f"{minutes} min ago"

        hours = int(minutes / 60)
        if hours < 24:
            return f"{hours} hours ago"

        days = int(hours / 24)
        return f"{days} days ago"

    async def check_account(self, account: MonitoredAccount) -> List[dict]:
        """
        Check a single account for new tweets.

        Args:
            account: The account to check

        Returns:
            List of new tweets found
        """
        # Get user ID if we don't have it
        twitter_id = account.twitter_id
        if not twitter_id:
            user_info = await self.twitter.get_user_by_username(account.twitter_handle)
            if not user_info:
                print(f"Could not find user @{account.twitter_handle}")
                return []
            twitter_id = user_info["id"]

        # Fetch tweets since last check
        tweets = await self.twitter.get_user_tweets(
            user_id=twitter_id,
            since_id=account.last_tweet_id,
            max_results=10,
        )

        new_tweets = []
        latest_tweet_id = account.last_tweet_id

        for tweet in tweets:
            # Skip if we've already processed this tweet
            if await self.tweet_service.exists(tweet["id"]):
                continue

            # Store the tweet
            tweet_create = MonitoredTweetCreate(
                tweet_id=tweet["id"],
                account_id=account.id,
                account_handle=account.twitter_handle,
                content=tweet["text"],
                tweet_created_at=datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00")) if tweet["created_at"] else None,
            )
            stored_tweet = await self.tweet_service.create(tweet_create)

            new_tweets.append({
                "tweet": stored_tweet,
                "raw": tweet,
                "account": account,
            })

            # Track latest tweet ID
            if not latest_tweet_id or tweet["id"] > latest_tweet_id:
                latest_tweet_id = tweet["id"]

        # Update last checked timestamp
        await self.account_service.update_last_checked(
            account.id,
            last_tweet_id=latest_tweet_id,
        )

        return new_tweets

    async def check_all_accounts(self) -> List[dict]:
        """
        Check all active accounts for new tweets.

        Returns:
            List of all new tweets found
        """
        accounts = await self.account_service.get_active()
        all_tweets = []

        for account in accounts:
            try:
                tweets = await self.check_account(account)
                all_tweets.extend(tweets)

                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Error checking @{account.twitter_handle}: {e}")
                continue

        return all_tweets

    async def process_tweet(
        self,
        tweet_data: dict,
        relevance_scorer,  # Will be passed from agent module
    ) -> bool:
        """
        Process a tweet: score relevance, generate content, and notify if relevant.

        Args:
            tweet_data: Dict with tweet, raw data, and account
            relevance_scorer: RelevanceScorer instance for scoring

        Returns:
            True if tweet was relevant and notified
        """
        tweet = tweet_data["tweet"]
        raw = tweet_data["raw"]
        account = tweet_data["account"]

        # Score relevance
        score_result = await relevance_scorer.score_tweet(
            tweet_text=tweet.content,
            account_handle=account.twitter_handle,
            account_category=account.category,
            follower_count=account.follower_count,
            likes=raw.get("likes", 0),
        )

        # Update tweet with relevance data
        await self.tweet_service.update_relevance(
            tweet_id=tweet.id,
            relevance_score=score_result["score"],
            relevance_type=RelevanceType(score_result["type"]),
            suggested_content=score_result.get("suggested_content"),
        )

        # Check if meets threshold
        if score_result["score"] < self.settings.relevance_threshold:
            return False

        # Send appropriate Slack notification
        time_ago = self._format_time_ago(tweet.tweet_created_at) if tweet.tweet_created_at else "just now"
        message_ts = None

        if score_result["type"] == "reply_opportunity":
            opportunity = SlackReplyOpportunity(
                account_handle=account.twitter_handle,
                tweet_content=tweet.content,
                tweet_id=tweet.tweet_id,
                follower_count=account.follower_count or 0,
                likes=raw.get("likes"),
                time_ago=time_ago,
                suggested_reply=score_result.get("suggested_content") or "No suggestion generated",
            )
            message_ts = await self.slack.send_reply_opportunity(opportunity)
        else:
            tweet_link = f"https://twitter.com/{account.twitter_handle}/status/{tweet.tweet_id}"
            alert = SlackNewsAlert(
                source_type="twitter",
                source_handle=account.twitter_handle,
                headline=tweet.content[:200] + "..." if len(tweet.content) > 200 else tweet.content,
                link=tweet_link,
                category=account.category,
                follower_count=account.follower_count,
                time_ago=time_ago,
                suggested_post=score_result.get("suggested_content") or "No suggestion generated",
                urgency="high" if account.priority == 1 else "normal",
            )
            message_ts = await self.slack.send_news_alert(alert)

        # Mark as notified and store Slack message_ts for thread replies
        await self.tweet_service.mark_notified(tweet.id, slack_message_ts=message_ts)
        return True

    async def run_check_cycle(self, relevance_scorer) -> dict:
        """
        Run a full check cycle: fetch tweets, score, and notify.

        Args:
            relevance_scorer: RelevanceScorer instance

        Returns:
            Summary of the check cycle
        """
        summary = {
            "accounts_checked": 0,
            "tweets_found": 0,
            "tweets_relevant": 0,
            "notifications_sent": 0,
        }

        # Check all accounts
        accounts = await self.account_service.get_active()
        summary["accounts_checked"] = len(accounts)

        all_tweets = await self.check_all_accounts()
        summary["tweets_found"] = len(all_tweets)

        # Process each tweet
        for tweet_data in all_tweets:
            try:
                was_relevant = await self.process_tweet(tweet_data, relevance_scorer)
                if was_relevant:
                    summary["tweets_relevant"] += 1
                    summary["notifications_sent"] += 1
            except Exception as e:
                print(f"Error processing tweet: {e}")
                continue

        return summary

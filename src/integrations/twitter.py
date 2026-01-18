"""Twitter API client for monitoring accounts (read-only)."""

from typing import List, Optional, Dict, Any
from datetime import datetime

import tweepy

from src.config import get_settings


class TwitterClient:
    """Client for Twitter API v2 (read-only operations)."""

    def __init__(self, bearer_token: Optional[str] = None):
        settings = get_settings()
        self.bearer_token = bearer_token or settings.twitter_bearer_token
        self._client: Optional[tweepy.Client] = None

    def _get_client(self) -> tweepy.Client:
        """Get or create the Twitter client."""
        if self._client is None:
            self._client = tweepy.Client(
                bearer_token=self.bearer_token,
                wait_on_rate_limit=True,
            )
        return self._client

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get user info by username.

        Args:
            username: Twitter username (without @)

        Returns:
            Dict with user data or None
        """
        try:
            client = self._get_client()
            user = client.get_user(
                username=username.lstrip("@"),
                user_fields=["id", "name", "username", "public_metrics", "description"],
            )
            if user.data:
                return {
                    "id": str(user.data.id),
                    "name": user.data.name,
                    "username": user.data.username,
                    "followers_count": user.data.public_metrics.get("followers_count", 0),
                    "description": user.data.description,
                }
            return None
        except Exception as e:
            print(f"Error fetching user {username}: {e}")
            return None

    async def get_user_tweets(
        self,
        user_id: str,
        since_id: Optional[str] = None,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get recent tweets from a user.

        Args:
            user_id: Twitter user ID (numeric)
            since_id: Only return tweets newer than this ID
            max_results: Maximum number of tweets to return (5-100)

        Returns:
            List of tweet dicts
        """
        try:
            client = self._get_client()
            tweets = client.get_users_tweets(
                id=user_id,
                since_id=since_id,
                max_results=min(max_results, 100),
                tweet_fields=["id", "text", "created_at", "public_metrics", "author_id"],
                exclude=["retweets", "replies"],  # Only original tweets
            )

            if not tweets.data:
                return []

            return [
                {
                    "id": str(tweet.id),
                    "text": tweet.text,
                    "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
                    "likes": tweet.public_metrics.get("like_count", 0) if tweet.public_metrics else 0,
                    "retweets": tweet.public_metrics.get("retweet_count", 0) if tweet.public_metrics else 0,
                    "replies": tweet.public_metrics.get("reply_count", 0) if tweet.public_metrics else 0,
                    "author_id": str(tweet.author_id),
                }
                for tweet in tweets.data
            ]
        except Exception as e:
            print(f"Error fetching tweets for user {user_id}: {e}")
            return []

    async def get_tweet_by_id(self, tweet_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single tweet by ID.

        Args:
            tweet_id: Twitter tweet ID

        Returns:
            Dict with tweet data or None
        """
        try:
            client = self._get_client()
            tweet = client.get_tweet(
                id=tweet_id,
                tweet_fields=["id", "text", "created_at", "public_metrics", "author_id"],
                expansions=["author_id"],
                user_fields=["username", "name", "public_metrics"],
            )

            if not tweet.data:
                return None

            # Get author info from includes
            author = None
            if tweet.includes and "users" in tweet.includes:
                author = tweet.includes["users"][0]

            return {
                "id": str(tweet.data.id),
                "text": tweet.data.text,
                "created_at": tweet.data.created_at.isoformat() if tweet.data.created_at else None,
                "likes": tweet.data.public_metrics.get("like_count", 0) if tweet.data.public_metrics else 0,
                "retweets": tweet.data.public_metrics.get("retweet_count", 0) if tweet.data.public_metrics else 0,
                "author_id": str(tweet.data.author_id),
                "author_username": author.username if author else None,
                "author_name": author.name if author else None,
                "author_followers": author.public_metrics.get("followers_count", 0) if author and author.public_metrics else 0,
            }
        except Exception as e:
            print(f"Error fetching tweet {tweet_id}: {e}")
            return None

    async def search_recent_tweets(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search recent tweets (last 7 days).

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of tweet dicts
        """
        try:
            client = self._get_client()
            tweets = client.search_recent_tweets(
                query=query,
                max_results=min(max_results, 100),
                tweet_fields=["id", "text", "created_at", "public_metrics", "author_id"],
                expansions=["author_id"],
                user_fields=["username", "name", "public_metrics"],
            )

            if not tweets.data:
                return []

            # Build author lookup
            authors = {}
            if tweets.includes and "users" in tweets.includes:
                for user in tweets.includes["users"]:
                    authors[str(user.id)] = user

            return [
                {
                    "id": str(tweet.id),
                    "text": tweet.text,
                    "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
                    "likes": tweet.public_metrics.get("like_count", 0) if tweet.public_metrics else 0,
                    "retweets": tweet.public_metrics.get("retweet_count", 0) if tweet.public_metrics else 0,
                    "author_id": str(tweet.author_id),
                    "author_username": authors.get(str(tweet.author_id), {}).username if str(tweet.author_id) in authors else None,
                }
                for tweet in tweets.data
            ]
        except Exception as e:
            print(f"Error searching tweets: {e}")
            return []


# Singleton instance
_twitter_client: Optional[TwitterClient] = None


def get_twitter_client() -> TwitterClient:
    """Get the Twitter client singleton instance."""
    global _twitter_client
    if _twitter_client is None:
        _twitter_client = TwitterClient()
    return _twitter_client

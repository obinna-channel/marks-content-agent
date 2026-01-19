"""Pydantic models for content agent data structures."""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Any
from uuid import UUID

from pydantic import BaseModel, Field


# Enums
class ContentType(str, Enum):
    """Types of content that can be generated."""
    WEEKLY_POST = "weekly_post"
    NEWS_REACTION = "news_reaction"
    REPLY = "reply"


class ContentPillar(str, Enum):
    """Content pillars from the content framework."""
    MARKET_COMMENTARY = "market_commentary"
    EDUCATION = "education"
    PRODUCT = "product"
    SOCIAL_PROOF = "social_proof"


class AccountCategory(str, Enum):
    """Categories for monitored Twitter accounts."""
    NIGERIA = "nigeria"
    ARGENTINA = "argentina"
    COLOMBIA = "colombia"
    GLOBAL_MACRO = "global_macro"
    CRYPTO_DEFI = "crypto_defi"
    REPLY_TARGET = "reply_target"


class RelevanceType(str, Enum):
    """Types of relevance for scored content."""
    NEWS = "news"
    REPLY_OPPORTUNITY = "reply_opportunity"
    SKIP = "skip"


# Content History Models
class ContentHistoryBase(BaseModel):
    """Base model for content history."""
    type: ContentType
    pillar: Optional[ContentPillar] = None
    topic: Optional[str] = None
    angle: Optional[str] = None
    content: str
    source_tweet_id: Optional[str] = None
    source_account: Optional[str] = None


class ContentHistoryCreate(ContentHistoryBase):
    """Model for creating content history records."""
    pass


class ContentHistory(ContentHistoryBase):
    """Model for content history from database."""
    id: UUID
    created_at: datetime
    posted_at: Optional[datetime] = None
    twitter_post_id: Optional[str] = None
    engagement_data: Optional[dict] = None

    class Config:
        from_attributes = True


# Monitored Account Models
class MonitoredAccountBase(BaseModel):
    """Base model for monitored Twitter accounts."""
    twitter_handle: str
    twitter_id: Optional[str] = None
    category: AccountCategory
    subcategory: Optional[str] = None
    priority: int = Field(default=2, ge=1, le=3)
    follower_count: Optional[int] = None
    is_voice_reference: bool = Field(default=False)  # Use this account's style for content generation
    voice_pillars: List[str] = Field(default_factory=list)  # Which content pillars this voice applies to


class MonitoredAccountCreate(MonitoredAccountBase):
    """Model for creating monitored account records."""
    added_by: str = "manual"


class MonitoredAccount(MonitoredAccountBase):
    """Model for monitored account from database."""
    id: UUID
    added_by: str = "manual"
    is_active: bool = True
    is_voice_reference: bool = False
    last_tweet_id: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Monitored Tweet Models
class MonitoredTweetBase(BaseModel):
    """Base model for monitored tweets."""
    tweet_id: str
    account_handle: str
    content: str
    tweet_created_at: Optional[datetime] = None


class MonitoredTweetCreate(MonitoredTweetBase):
    """Model for creating monitored tweet records."""
    account_id: UUID


class MonitoredTweet(MonitoredTweetBase):
    """Model for monitored tweet from database."""
    id: UUID
    account_id: UUID
    fetched_at: datetime
    relevance_score: Optional[float] = None
    relevance_type: Optional[RelevanceType] = None
    suggested_content: Optional[str] = None
    slack_notified: bool = False
    slack_message_ts: Optional[str] = None  # For linking Slack thread replies
    actioned: bool = False

    class Config:
        from_attributes = True


# RSS Source Models
class RSSSourceBase(BaseModel):
    """Base model for RSS sources."""
    name: str
    url: str
    category: AccountCategory
    subcategory: Optional[str] = None
    keywords: Optional[List[str]] = None
    poll_interval_minutes: int = 15


class RSSSourceCreate(RSSSourceBase):
    """Model for creating RSS source records."""
    pass


class RSSSource(RSSSourceBase):
    """Model for RSS source from database."""
    id: UUID
    is_active: bool = True
    last_checked_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# RSS Item Models
class RSSItemBase(BaseModel):
    """Base model for RSS items."""
    guid: str
    title: str
    url: str
    summary: Optional[str] = None
    published_at: Optional[datetime] = None


class RSSItemCreate(RSSItemBase):
    """Model for creating RSS item records."""
    source_id: UUID


class RSSItem(RSSItemBase):
    """Model for RSS item from database."""
    id: UUID
    source_id: UUID
    fetched_at: datetime
    relevance_score: Optional[float] = None
    suggested_content: Optional[str] = None
    slack_notified: bool = False
    actioned: bool = False

    class Config:
        from_attributes = True


# Voice Feedback Models
class VoiceFeedbackBase(BaseModel):
    """Base model for voice feedback."""
    original_content: str
    edited_content: Optional[str] = None
    reaction: Optional[str] = None  # 'thumbs_up', 'thumbs_down'
    feedback_text: Optional[str] = None


class VoiceFeedbackCreate(VoiceFeedbackBase):
    """Model for creating voice feedback records."""
    content_id: UUID


class VoiceFeedback(VoiceFeedbackBase):
    """Model for voice feedback from database."""
    id: UUID
    content_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


# Voice Sample Models (for learning style from reference accounts)
class VoiceSampleBase(BaseModel):
    """Base model for voice samples from reference accounts."""
    account_handle: str
    tweet_id: str
    content: str
    tweet_created_at: Optional[datetime] = None
    likes: int = 0
    retweets: int = 0


class VoiceSampleCreate(VoiceSampleBase):
    """Model for creating voice sample records."""
    account_id: UUID


class VoiceSample(VoiceSampleBase):
    """Model for voice sample from database."""
    id: UUID
    account_id: UUID
    fetched_at: datetime
    is_active: bool = True  # Can be disabled if sample isn't good

    class Config:
        from_attributes = True


# Response Models for Slack
class SlackNewsAlert(BaseModel):
    """Model for news alert Slack messages."""
    source_type: str  # 'twitter' or 'rss'
    source_handle: Optional[str] = None
    source_name: Optional[str] = None
    headline: str
    link: Optional[str] = None
    category: AccountCategory
    follower_count: Optional[int] = None
    time_ago: str
    suggested_post: str
    urgency: str = "normal"  # 'high', 'normal'


class SlackReplyOpportunity(BaseModel):
    """Model for reply opportunity Slack messages."""
    account_handle: str
    tweet_content: str
    tweet_id: str
    follower_count: int
    likes: Optional[int] = None
    time_ago: str
    suggested_reply: str


class WeeklyBatchItem(BaseModel):
    """Model for individual item in weekly batch."""
    day: str
    pillar: ContentPillar
    topic: str
    content: str


class WeeklyBatch(BaseModel):
    """Model for weekly content batch."""
    week_start: datetime
    week_end: datetime
    items: List[WeeklyBatchItem]

-- =============================================================================
-- CONTENT AGENT DATABASE SCHEMA
-- Run this in Supabase SQL Editor
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. CONTENT HISTORY
-- Tracks all generated and posted content
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS content_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type TEXT NOT NULL,  -- 'weekly_post', 'news_reaction', 'reply'
    pillar TEXT,  -- 'market_commentary', 'education', 'product', 'social_proof'
    topic TEXT,
    angle TEXT,
    content TEXT NOT NULL,
    source_tweet_id TEXT,  -- Tweet that triggered this (for reactions/replies)
    source_account TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    posted_at TIMESTAMPTZ,  -- NULL if not posted yet
    twitter_post_id TEXT,  -- Our tweet ID if posted
    engagement_data JSONB  -- Likes, retweets, etc. (future)
);

-- Index for querying recent content
CREATE INDEX IF NOT EXISTS idx_content_history_created_at ON content_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_content_history_type ON content_history(type);
CREATE INDEX IF NOT EXISTS idx_content_history_pillar ON content_history(pillar);


-- -----------------------------------------------------------------------------
-- 2. MONITORED ACCOUNTS
-- Twitter accounts to watch for news and reply opportunities
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monitored_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twitter_handle TEXT UNIQUE NOT NULL,
    twitter_id TEXT,  -- Numeric Twitter ID
    category TEXT NOT NULL,  -- 'nigeria', 'argentina', 'global_macro', 'crypto_defi', 'reply_target'
    subcategory TEXT,  -- 'central_bank', 'news', 'influencer', 'competitor'
    priority INT DEFAULT 2,  -- 1=high (alert immediately), 2=medium, 3=low
    follower_count INT,
    added_by TEXT DEFAULT 'manual',  -- 'manual' or 'discovered'
    is_active BOOLEAN DEFAULT true,
    is_voice_reference BOOLEAN DEFAULT false,  -- Use this account's style for content generation
    voice_pillars TEXT[] DEFAULT '{}',  -- Which content pillars this voice applies to
    last_tweet_id TEXT,  -- For pagination / dedup
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_monitored_accounts_active ON monitored_accounts(is_active);
CREATE INDEX IF NOT EXISTS idx_monitored_accounts_category ON monitored_accounts(category);
CREATE INDEX IF NOT EXISTS idx_monitored_accounts_voice_ref ON monitored_accounts(is_voice_reference) WHERE is_voice_reference = true;


-- -----------------------------------------------------------------------------
-- 3. MONITORED TWEETS
-- Recent tweets from monitored accounts (for dedup and tracking)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monitored_tweets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tweet_id TEXT UNIQUE NOT NULL,
    account_id UUID REFERENCES monitored_accounts(id) ON DELETE CASCADE,
    account_handle TEXT NOT NULL,
    content TEXT NOT NULL,
    tweet_created_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    relevance_score FLOAT,  -- 0-1, from Claude
    relevance_type TEXT,  -- 'news', 'reply_opportunity', 'skip'
    suggested_content TEXT,  -- Generated response
    slack_notified BOOLEAN DEFAULT false,
    actioned BOOLEAN DEFAULT false  -- Did user post about this?
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_monitored_tweets_tweet_id ON monitored_tweets(tweet_id);
CREATE INDEX IF NOT EXISTS idx_monitored_tweets_account ON monitored_tweets(account_id);
CREATE INDEX IF NOT EXISTS idx_monitored_tweets_fetched ON monitored_tweets(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_monitored_tweets_unnotified ON monitored_tweets(slack_notified) WHERE slack_notified = false;


-- -----------------------------------------------------------------------------
-- 4. RSS SOURCES
-- RSS feeds to monitor for news
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rss_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL,  -- 'nigeria', 'argentina', 'global_macro', 'crypto_defi'
    subcategory TEXT,  -- 'official', 'news', 'analysis'
    keywords JSONB,  -- Filtering keywords for this feed
    poll_interval_minutes INT DEFAULT 15,
    is_active BOOLEAN DEFAULT true,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_rss_sources_active ON rss_sources(is_active);
CREATE INDEX IF NOT EXISTS idx_rss_sources_category ON rss_sources(category);


-- -----------------------------------------------------------------------------
-- 5. RSS ITEMS
-- Articles fetched from RSS feeds
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rss_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES rss_sources(id) ON DELETE CASCADE,
    guid TEXT UNIQUE NOT NULL,  -- RSS item GUID for dedup
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    summary TEXT,
    published_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    relevance_score FLOAT,  -- 0-1, from Claude
    suggested_content TEXT,
    slack_notified BOOLEAN DEFAULT false,
    actioned BOOLEAN DEFAULT false
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_rss_items_guid ON rss_items(guid);
CREATE INDEX IF NOT EXISTS idx_rss_items_source ON rss_items(source_id);
CREATE INDEX IF NOT EXISTS idx_rss_items_fetched ON rss_items(fetched_at DESC);


-- -----------------------------------------------------------------------------
-- 6. VOICE FEEDBACK
-- Tracks edits and reactions to improve voice over time
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS voice_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_id UUID REFERENCES content_history(id) ON DELETE CASCADE,
    pillar TEXT,  -- 'market_commentary', 'education', 'product', 'social_proof'
    original_content TEXT NOT NULL,
    final_content TEXT,  -- Last draft after revisions
    edited_content TEXT,  -- NULL if not edited (legacy)
    reaction TEXT,  -- 'thumbs_up', 'thumbs_down', NULL
    feedback_text TEXT,  -- Free-form feedback from Slack reply
    learnings JSONB,  -- Array of extracted style preferences
    slack_thread_ts TEXT,  -- Reference to Slack thread
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_voice_feedback_content ON voice_feedback(content_id);
CREATE INDEX IF NOT EXISTS idx_voice_feedback_pillar ON voice_feedback(pillar);
CREATE INDEX IF NOT EXISTS idx_voice_feedback_created ON voice_feedback(created_at DESC);


-- -----------------------------------------------------------------------------
-- 7. VOICE SAMPLES
-- Sample tweets from voice reference accounts
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS voice_samples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES monitored_accounts(id) ON DELETE CASCADE,
    account_handle TEXT NOT NULL,
    tweet_id TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    tweet_created_at TIMESTAMPTZ,
    likes INT DEFAULT 0,
    retweets INT DEFAULT 0,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true  -- Can be disabled if sample isn't good
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_voice_samples_account ON voice_samples(account_id);
CREATE INDEX IF NOT EXISTS idx_voice_samples_tweet ON voice_samples(tweet_id);
CREATE INDEX IF NOT EXISTS idx_voice_samples_active ON voice_samples(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_voice_samples_likes ON voice_samples(likes DESC);


-- =============================================================================
-- ROW LEVEL SECURITY (Optional - enable if using Supabase Auth)
-- =============================================================================

-- Uncomment these if you want to enable RLS:
-- ALTER TABLE content_history ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE monitored_accounts ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE monitored_tweets ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE rss_sources ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE rss_items ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE voice_feedback ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE voice_samples ENABLE ROW LEVEL SECURITY;


-- =============================================================================
-- DONE!
-- =============================================================================
-- Tables created:
--   1. content_history     - Generated content tracking
--   2. monitored_accounts  - Twitter accounts to watch
--   3. monitored_tweets    - Tweets from monitored accounts
--   4. rss_sources         - RSS feeds to poll
--   5. rss_items           - Articles from RSS feeds
--   6. voice_feedback      - Feedback on generated content
--   7. voice_samples       - Sample tweets for voice matching
-- =============================================================================

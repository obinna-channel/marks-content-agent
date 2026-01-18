# Content Agent System Design (V1)

## Overview

A content assistant for Marks Exchange that:
1. **Generates content** — Creates weekly content batches based on your framework
2. **Monitors news** — Tracks EM economics, country-specific news, and DeFi for content opportunities
3. **Monitors accounts** — Watches large accounts for reply opportunities, sends real-time Slack alerts
4. **Suggests replies** — Drafts reply content when relevant posts are detected

**V1 is suggestion-only** — You review and post manually.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CONTENT AGENT (V1)                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────────┐   │
│  │  News Monitor   │────▶│                 │────▶│                     │   │
│  │  - RSS feeds    │     │  Content Agent  │     │    Slack Bot        │   │
│  │  - News APIs    │     │  (Claude API)   │     │    (suggestions)    │   │
│  └─────────────────┘     │                 │     │                     │   │
│                          │                 │     │  - Weekly batch     │   │
│  ┌─────────────────┐     │                 │     │  - News alerts      │   │
│  │ Account Monitor │────▶│                 │     │  - Reply opps       │   │
│  │  - Twitter API  │     │                 │     │                     │   │
│  │  - Your list +  │     └─────────────────┘     └─────────────────────┘   │
│  │    discovered   │              │                                        │
│  └─────────────────┘              │                                        │
│                                   ▼                                        │
│                          ┌─────────────────┐                               │
│                          │  Data Services  │                               │
│                          │  - Marks APIs   │                               │
│                          │  - Price feeds  │                               │
│                          │  - Metrics      │                               │
│                          └─────────────────┘                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Features

### 1. Weekly Content Generation

**Trigger:** Saturday morning (manual or scheduled)

**Process:**
1. Fetch market data (NGN/ARS weekly performance)
2. Fetch platform metrics (volume, users)
3. Pull recent news headlines for context
4. Query content history to avoid repetition
5. Generate 7 drafts following your content framework
6. Send to Slack for review

**Output:** 7 draft posts (Mon-Sun) in Slack, organized by pillar

---

### 2. News & Account Monitoring (Twitter + RSS)

**Dual-source monitoring** — Twitter for real-time social, RSS for official sources and articles.

**Account Categories:**

| Category | Example Accounts | Purpose |
|----------|------------------|---------|
| **Nigeria** | @cenaborofc, @aboraborisade, @Nabormetrics, @MBuhari, @NGRPresident | CBN policy, naira news, local econ |
| **Argentina** | @BCaborA_Oficial, @Aborinflacion, @Aborambito, @jaborariomilei | BCRA policy, peso news, inflation |
| **Global Macro** | @markets, @breakingnews, @FT, @WSJ, @economics | Major global events |
| **Central Banks** | @federalreserve, @ecb, @bankofengland | Rate decisions, policy |
| **Crypto/DeFi** | @DefiLlama, @TheBlock__, @CoinDesk, @WuBlockchain | DeFi news, perpetuals |
| **Forex/Trading** | @Fxhedgers, @zaborerohedge, @unusual_whales | FX moves, trading sentiment |
| **Reply Targets** | [Your competitors, influencers] | Engagement opportunities |

**Suggested Initial Account List (30+ accounts):**

**Nigeria (10):**
- @cenaborofc (CBN official)
- @aboraborisade (Finance commentator)
- @Nabormetrics (Business news)
- @paborcheconomist (Economist)
- @taborhisday_ng (ThisDay newspaper)
- @aborabordelano (Forex analyst)
- @faborsdcnigeria (FSDH research)
- @aboraborjibola (Economic policy)
- @premiumtimesng (News)
- @channaborstv (News)

**Argentina (10):**
- @BCaborA_Oficial (BCRA official)
- @Aborambito (Business news)
- @elaborcronista (Business news)
- @infobae (News)
- @claaborin (News)
- @Aborinflacion (Inflation tracking)
- @tabormaslatina (LatAm economics)
- @econaborarg (Economics)
- @faborernandezomar (Policy commentary)
- @maborileitomilei (Crypto-friendly president)

**Global Macro (10):**
- @markets (Bloomberg)
- @Reuters (Global news)
- @FT (Financial Times)
- @WSJ (Wall Street Journal)
- @economics (Bloomberg Econ)
- @federalreserve (Fed)
- @ecb (ECB)
- @IMFNews (IMF)
- @WorldBank (World Bank)
- @zerohedge (Alt finance)

**Crypto/DeFi (10):**
- @DefiLlama (DeFi analytics)
- @TheBlock__ (Crypto news)
- @CoinDesk (Crypto news)
- @WuBlockchain (Asia crypto)
- @tier10k (Crypto news)
- @gmaborx_io (GMX - perpetuals)
- @SynthetixIO (Synthetix)
- @daborYdXaborprotocol (dYdX)
- @HyperaborliquidX (Hyperliquid)
- @Cosabormos (Cosmos ecosystem)

**How it works:**
1. Poll Twitter API every 5 minutes for new tweets from monitored accounts
2. Score each tweet for relevance using Claude API:
   - Is this about currencies we support (NGN, ARS)?
   - Is this breaking news worth reacting to?
   - Is this a reply opportunity?
3. If relevance score > threshold:
   - Send real-time Slack alert
   - Generate suggested content (post or reply)
   - Include urgency indicator

**Slack alert format (News):**
```
🗞️ News Alert

@cenbank_ng just posted:
"The Monetary Policy Committee has decided to hold the policy rate at 27.5%"

Category: Nigeria | Followers: 500K | 5 min ago

📝 Suggested post:
"Nigeria's CBN held rates at 27.5% today. USDT/NGN has moved X% since the announcement.

What this means for traders hedging naira exposure: [context]"

⚡ React fast — this is breaking news
```

**Slack alert format (Reply Opportunity):**
```
💬 Reply Opportunity

@SomeInfluencer just posted:
"The naira just hit a new low. What's everyone's hedging strategy?"

Followers: 150K | Likes: 234 | 10 min ago

📝 Suggested reply:
"We built Marks for exactly this — trade USDT/NGN perpetuals with up to 50x leverage. Hedge or speculate on naira moves. [link]"

⚡ Post within 30 min for best visibility
```

---

### 3. RSS Feed Monitoring

**RSS Sources:**

| Category | Sources | URL Examples |
|----------|---------|--------------|
| **Nigeria Official** | CBN, NBS | cbn.gov.ng/rss, nigerianstat.gov.ng |
| **Nigeria News** | Nairametrics, BusinessDay, Punch | nairametrics.com/feed |
| **Argentina Official** | BCRA, INDEC | bcra.gob.ar/rss |
| **Argentina News** | Ambito, Infobae, El Cronista | ambito.com/rss |
| **Global Macro** | Reuters, Bloomberg, FT | feeds.reuters.com/reuters/businessNews |
| **Crypto/DeFi** | CoinDesk, The Block, Decrypt | coindesk.com/arc/outboundfeeds/rss |

**How RSS works:**
1. Poll RSS feeds every 15 minutes
2. Filter new items by keywords: NGN, ARS, naira, peso, central bank, inflation, FX, perpetuals
3. Score relevance with Claude API
4. If relevant → send Slack alert with suggested post

**Slack alert format (RSS):**
```
📰 Article Alert

Nairametrics: "CBN Governor Signals Potential Rate Cut in Q2"

Published: 10 min ago
Link: https://...

📝 Suggested post:
"Breaking: CBN signaling potential rate cuts. Here's what this could mean for USDT/NGN..."

React to copy
```

---

### 4. Account Monitoring (Reply Opportunities)

**Initial accounts to monitor (you'll provide full list):**
- Major EM/forex accounts
- DeFi protocol accounts
- Crypto influencers discussing perpetuals
- Competitors

**Discovery:**
- Agent suggests new accounts based on engagement with your monitored accounts
- Weekly "accounts to add?" suggestion

**How it works:**
1. Use Twitter API to poll monitored accounts every 5 minutes
2. When new tweet detected:
   - Evaluate relevance (is this worth replying to?)
   - If relevant, send real-time Slack alert
   - Generate suggested reply

**Slack alert format:**
```
💬 Reply Opportunity

@SomeInfluencer just posted:
"The naira just hit a new low against the dollar. What's everyone's hedging strategy?"

Followers: 150K | Likes: 234 (and counting)

📝 Suggested reply:
"We built Marks specifically for this. Trade USDT/NGN perpetuals with up to 50x leverage to hedge your naira exposure. [link]"

⚡ Post within 30 min for best visibility
```

---

### 4. Content History & Variety

**Tracks:**
- What topics/angles have been used recently
- Which news stories have been covered
- Which accounts have been replied to

**Ensures:**
- No repeated angles within 30 days
- No duplicate news coverage
- Varied reply styles (not always promotional)

---

## Database Schema

### Table: `content_history`
```sql
CREATE TABLE content_history (
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
```

### Table: `monitored_accounts`
```sql
CREATE TABLE monitored_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    twitter_handle TEXT UNIQUE NOT NULL,
    twitter_id TEXT,  -- Numeric Twitter ID
    category TEXT NOT NULL,  -- 'nigeria', 'argentina', 'global_macro', 'crypto_defi', 'reply_target'
    subcategory TEXT,  -- 'central_bank', 'news', 'influencer', 'competitor'
    priority INT DEFAULT 2,  -- 1=high (alert immediately), 2=medium, 3=low
    follower_count INT,
    added_by TEXT DEFAULT 'manual',  -- 'manual' or 'discovered'
    is_active BOOLEAN DEFAULT true,
    last_tweet_id TEXT,  -- For pagination / dedup
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Table: `monitored_tweets`
```sql
CREATE TABLE monitored_tweets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tweet_id TEXT UNIQUE NOT NULL,
    account_id UUID REFERENCES monitored_accounts(id),
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
```

### Table: `rss_sources`
```sql
CREATE TABLE rss_sources (
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
```

### Table: `rss_items`
```sql
CREATE TABLE rss_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES rss_sources(id),
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
```

---

## Repository Structure

**Location**: `/Users/obinnaokwodu/Dev/marks/content-agent/` (subfolder in Marks monorepo)

**Communicates with Marks via HTTP API** for price data.

```
marks/content-agent/
├── README.md
├── requirements.txt
├── .env.example
├── pyproject.toml
│
├── src/
│   ├── __init__.py
│   ├── config.py                 # Settings (API keys, thresholds)
│   ├── cli.py                    # CLI commands
│   ├── main.py                   # Entry point for background workers
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── generator.py          # Claude API - content generation
│   │   ├── prompts.py            # System prompts for generation + relevance
│   │   ├── relevance.py          # Score tweets/articles for relevance
│   │   └── variety.py            # Topic/angle rotation logic
│   │
│   ├── monitors/
│   │   ├── __init__.py
│   │   ├── twitter_monitor.py    # Poll Twitter for new tweets
│   │   ├── rss_monitor.py        # Poll RSS feeds for new articles
│   │   └── account_discovery.py  # Suggest new accounts to follow
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── database.py           # Supabase client
│   │   ├── history_service.py    # Content history CRUD
│   │   ├── account_service.py    # Monitored accounts CRUD
│   │   ├── tweet_service.py      # Monitored tweets CRUD
│   │   ├── rss_service.py        # RSS sources and items CRUD
│   │   └── marks_api.py          # HTTP client for Marks price API
│   │
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── slack.py              # Slack notifications
│   │   └── twitter.py            # Twitter API client (read-only)
│   │
│   └── models/
│       ├── __init__.py
│       └── content.py            # Pydantic models
│
└── tests/
    └── ...
```

---

## Voice Profile

The content agent will generate posts in a voice inspired by these accounts:

### Reference Accounts Analyzed
| Account | Followers | Style |
|---------|-----------|-------|
| @KobeissiLetter | 1.2M | Urgent breaking news, data-heavy, "BREAKING:" prefix |
| @capitalcom | 212K | Emoji bullets, analytical, educational, chart-focused |
| @ventuals | 27.9K | Clean lists, product-focused, specific numbers |

### Marks Voice Guidelines

**Structure:**
- Use "BREAKING:" for major news (CBN announcements, big moves)
- Use emoji bullets (📉 📊 🚨) for scannable lists
- Clean dashes for product/feature announcements
- Short paragraphs, no walls of text

**Data:**
- Always include specific numbers (%, $, price levels)
- Reference current prices: "USDT/NGN at X, down Y% today"
- Compare to timeframes: "This hasn't happened since..."

**Tone:**
- Confident, not hype
- Analytical, not promotional
- "Here's what happened" not "We're excited to announce"
- Direct, no corporate speak

**Format Patterns:**
```
BREAKING: [News headline]

[1-2 sentence context]

What it means for NGN/ARS:
- [Data point 1]
- [Data point 2]

[Optional: Trade it on Marks]
```

```
📊 [Topic] update

📉 [Bullet 1]
💵 [Bullet 2]
🛢️ [Bullet 3]

Full breakdown: [link]
```

**Example Marks Post:**
```
BREAKING: CBN holds rates at 27.5%

USDT/NGN response:
- Down 1.2% since announcement
- P2P spread narrowing to 3.1%

What it means: Rate stability = continued pressure on parallel market rates.

Trade USDT/NGN on Marks →
```

### Voice Feedback System

The agent improves its voice over time through two mechanisms:

**1. Edit Tracking**
When you modify a suggested post before posting:
- Agent stores original vs. your edited version
- Analyzes patterns: "User shortens sentences", "User removes emojis", "User adds more data"
- Applies learnings to future generations

**2. Slack Reactions & Replies**
React to any suggestion in Slack:
- 👍 = Good tone, keep doing this
- 👎 = Bad tone, avoid this style
- 💬 Reply with feedback: "too promotional", "more data", "shorter"

**Database Table: `voice_feedback`**
```sql
CREATE TABLE voice_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_id UUID REFERENCES content_history(id),
    original_content TEXT NOT NULL,
    edited_content TEXT,  -- NULL if not edited
    reaction TEXT,  -- 'thumbs_up', 'thumbs_down', NULL
    feedback_text TEXT,  -- Free-form feedback from Slack reply
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**How It's Used:**
- Before generating, agent queries recent feedback
- Includes patterns in the prompt: "User prefers shorter sentences. User dislikes emojis in education posts."
- Continuously refines voice without manual intervention

---

## Configuration

### Environment Variables

```env
# Content Agent
ANTHROPIC_API_KEY=sk-ant-...
CONTENT_AGENT_ENABLED=true

# Slack (for notifications)
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C0123456789

# Twitter (read-only for monitoring)
TWITTER_BEARER_TOKEN=...

# News APIs (optional, can use RSS)
NEWS_API_KEY=...  # newsapi.org
```

---

## Slack Interaction Model

Since V1 is suggestion-only, Slack is used for:

### 1. Weekly Batch
```
📅 Weekly Content Batch (Jan 20-26)

*Monday - Market Commentary (NGN)*
USDT/NGN moved -2.3% this week...
[full draft]

*Tuesday - Education*
What is leverage? Here's why 10x means...
[full draft]

... (7 total)

Copy any draft and post when ready.
```

### 2. News Alerts (Real-time)
```
🗞️ News Alert
[headline + suggested post]
```

### 3. Reply Opportunities (Real-time)
```
💬 Reply Opportunity
[tweet + suggested reply]
```

### 4. Daily Digest (Optional)
```
📊 Daily Digest - Jan 15

News covered: 3 stories
Reply opportunities: 5 (2 high priority)
Posts made: 0/1 scheduled

Pending:
- Tuesday Education post ready to go
```

---

## Implementation Plan

### Phase 1: Core Infrastructure
1. Create `server/app/content_agent/` directory structure
2. Set up database tables in Supabase:
   - `content_history` — tracks all generated/posted content
   - `monitored_accounts` — Twitter accounts to watch
   - `monitored_tweets` — recent tweets processed (dedup)
   - `rss_sources` — RSS feeds to poll
   - `rss_items` — articles fetched (dedup)
3. Create Pydantic models
4. Set up configuration (`config.py`)
5. Add dependencies to `requirements.txt`: `anthropic`, `slack-sdk`, `tweepy`, `feedparser`

### Phase 2: Twitter Integration
6. Set up Twitter API client (read-only, using `tweepy`)
7. Implement account polling (fetch recent tweets from monitored accounts)
8. Implement tweet deduplication (track what we've already processed)
9. Test fetching tweets from a few accounts

### Phase 3: RSS Integration
10. Set up RSS parser (using `feedparser`)
11. Implement feed polling
12. Implement article deduplication
13. Test fetching from a few feeds

### Phase 4: Slack Integration
14. Set up Slack bot (send-only, using `slack-sdk`)
15. Create message formatting helpers:
    - Twitter news alert format
    - RSS article alert format
    - Reply opportunity format
    - Weekly batch format
16. Test sending messages to your channel

### Phase 5: Content Generation
17. Implement data fetcher (reuse existing Marks price services)
18. Create prompts system with your content framework
19. Implement relevance scoring (Claude API):
    - Score tweets for news relevance
    - Score tweets for reply opportunity
    - Score RSS articles for relevance
20. Implement variety manager (topic/angle rotation)
21. Implement weekly batch generator
22. Wire up: generate → format → send to Slack

### Phase 6: Monitoring Loops
23. Implement Twitter polling loop (async, every 5 min)
24. Implement RSS polling loop (async, every 15 min)
25. Wire up: poll → score → alert if relevant → send to Slack
26. Implement account discovery suggestions (weekly)

### Phase 7: CLI & Deployment
27. Create CLI for manual triggers:
    - `generate-batch` — generate weekly content
    - `check-twitter` — poll Twitter now
    - `check-rss` — poll RSS now
    - `history` — view content history
28. Add logging and error handling
29. Integrate with `main.py` startup (background tasks)
30. Deploy to Heroku as worker
31. Seed initial data:
    - 40+ Twitter accounts across categories
    - 15+ RSS feeds across categories

---

## Verification Plan

### Manual Testing
1. **Twitter monitoring**: Trigger check, verify relevant tweets alert in Slack
2. **RSS monitoring**: Trigger check, verify relevant articles alert in Slack
3. **Reply opportunities**: Verify high-engagement tweets get reply suggestions
4. **Weekly batch**: Run CLI, verify 7 drafts appear in Slack
5. **Variety**: Generate two batches, verify no repeated topics/angles

### CLI Testing
```bash
# Generate weekly batch
cd server && python -m app.content_agent.cli generate-batch

# Check Twitter accounts now
cd server && python -m app.content_agent.cli check-twitter

# Check RSS feeds now
cd server && python -m app.content_agent.cli check-rss

# View content history
cd server && python -m app.content_agent.cli history --days 30
```

### End-to-End Flow
1. Seed monitored accounts and RSS sources in Supabase
2. Run `check-twitter` — verify relevant tweets trigger Slack alerts
3. Run `check-rss` — verify relevant articles trigger Slack alerts
4. Run `generate-batch` — verify 7 drafts sent to Slack
5. Copy a draft, post manually to Twitter
6. Mark as posted in history (manual for V1)

---

## Decisions Made

1. **Slack**: Ready to use (user has workspace)
2. **Twitter API**: Approved — full monitoring from day 1
3. **News sources**: Twitter + RSS (both equal priority, real-time alerts)
4. **V1 scope**: Suggestion-only (user posts manually)
5. **Account categories**: Country-specific (Nigeria, Argentina) + Global macro + Crypto/DeFi

---

## V2 Roadmap (Future)

- Auto-posting to Twitter
- Telegram integration + Spanish translations
- Image generation (charts, branded templates)
- Engagement tracking (auto-pull likes/retweets)
- Smart scheduling (optimal posting times)
- Thread generation for longer content

"""Configuration settings for the Content Agent."""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field

# Fix SSL certificate issue on macOS
try:
    import certifi
    os.environ.setdefault('SSL_CERT_FILE', certifi.where())
except ImportError:
    pass


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Anthropic (Claude API)
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")

    # Supabase
    supabase_url: str = Field(..., env="SUPABASE_URL")
    supabase_key: str = Field(..., env="SUPABASE_KEY")

    # Slack
    slack_bot_token: str = Field(..., env="SLACK_BOT_TOKEN")
    slack_channel_id: str = Field(..., env="SLACK_CHANNEL_ID")
    slack_app_token: Optional[str] = Field(default=None, env="SLACK_APP_TOKEN")  # For Socket Mode

    # Twitter
    twitter_bearer_token: str = Field(..., env="TWITTER_BEARER_TOKEN")

    # Marks API (optional - for price data)
    marks_api_url: Optional[str] = Field(default=None, env="MARKS_API_URL")

    # Polling intervals (seconds)
    twitter_poll_interval: int = Field(default=300, env="TWITTER_POLL_INTERVAL")  # 5 min
    rss_poll_interval: int = Field(default=900, env="RSS_POLL_INTERVAL")  # 15 min

    # Relevance threshold (0-1)
    relevance_threshold: float = Field(default=0.7, env="RELEVANCE_THRESHOLD")

    # Google Gemini API (for Imagen 3 image generation)
    gemini_api_key: Optional[str] = Field(default=None, env="GEMINI_API_KEY")

    # Feature flags
    content_agent_enabled: bool = Field(default=True, env="CONTENT_AGENT_ENABLED")
    image_generation_enabled: bool = Field(default=False, env="IMAGE_GENERATION_ENABLED")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the settings singleton instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Voice profile for content generation
VOICE_PROFILE = """
## Marks Voice Guidelines

Based on: @KobeissiLetter, @capitalcom, @ventuals

### Structure
- Use "BREAKING:" for major news (CBN announcements, big moves)
- Use emoji bullets (📉 📊 🚨) for scannable lists
- Clean dashes for product/feature announcements
- Short paragraphs, no walls of text

### Data
- Always include specific numbers (%, $, price levels)
- Reference current prices: "USDT/NGN at X, down Y% today"
- Compare to timeframes: "This hasn't happened since..."

### Tone
- Confident, not hype
- Analytical, not promotional
- "Here's what happened" not "We're excited to announce"
- Direct, no corporate speak

### Example Post
```
BREAKING: CBN holds rates at 27.5%

USDT/NGN response:
- Down 1.2% since announcement
- P2P spread narrowing to 3.1%

What it means: Rate stability = continued pressure on parallel market rates.

Trade USDT/NGN on Marks →
```
"""

# Content pillars from user's framework
CONTENT_PILLARS = {
    "market_commentary": {
        "goal": "Relevance — show Marks understands the markets traders live in",
        "tone": "Observational, data-driven, not predictive",
        "days": ["monday"],
    },
    "education": {
        "goal": "Understanding — reduce friction by teaching how the product works",
        "tone": "Simple, clear, no jargon assumed",
        "days": ["tuesday", "wednesday", "thursday"],
    },
    "product": {
        "goal": "Credibility — prove the product works",
        "tone": "Demonstrative, not salesy",
        "days": ["tuesday", "wednesday", "thursday"],
    },
    "social_proof": {
        "goal": "Momentum — create legitimacy and FOMO",
        "tone": "Celebratory but not exaggerated",
        "days": ["friday"],
    },
}

# Supported currency pairs
SUPPORTED_PAIRS = ["USDTNGN", "USDTARS", "USDTCOP"]

# Keywords for relevance filtering
RELEVANCE_KEYWORDS = [
    # Emerging market currencies
    "NGN", "naira", "nigeria", "nigerian",
    "ARS", "peso", "argentina", "argentine",
    "COP", "colombia", "colombian",
    # Developed market currencies
    "EUR", "euro", "eurozone",
    "GBP", "pound", "sterling",
    "JPY", "yen", "japan",
    "CHF", "swiss franc", "switzerland",
    "AUD", "aussie", "australia",
    "CAD", "loonie", "canada",
    # Central banks (English)
    "CBN", "central bank", "BCRA", "BanRep",
    "Fed", "Federal Reserve", "ECB", "BOJ", "BOE", "SNB",
    "MPC", "monetary policy", "interest rate", "rate decision",
    # Central banks (Spanish/Portuguese)
    "banco central", "tasa de interés", "taxa de juros",
    "política monetaria", "política monetária",
    # Trading
    "FX", "forex", "perpetual", "leverage",
    "hedging", "hedge", "trading", "currency pair",
    # Stablecoins & issuers
    "USDT", "USDC", "stablecoin", "stablecoins",
    "Tether", "Circle", "Paxos",
    "EURC", "PYUSD", "PayPal USD",
    "EURS", "EURT", "euro stablecoin",
    "stablecoin regulation", "MiCA",
    # Non-US stablecoins & stablecoin FX
    "stablecoin FX", "stablecoin forex",
    "offshore stablecoin", "non-USD stablecoin",
    "synthetic dollar", "dollar alternative",
    # DeFi / Perps
    "DeFi", "perpetuals", "perps", "funding rate",
    # Market terms (English)
    "inflation", "devaluation", "P2P", "parallel market",
    "exchange rate", "currency", "dollar index", "DXY",
    # Market terms (Spanish)
    "inflación", "devaluación", "tipo de cambio",
    "dólar", "dolar", "cotización", "divisa", "divisas",
    "mercado paralelo", "dólar blue", "dolar blue",
    "cepo", "brecha cambiaria", "reservas",
    # Market terms (Portuguese)
    "inflação", "desvalorização", "taxa de câmbio",
    "câmbio", "moeda", "real", "BRL",
]

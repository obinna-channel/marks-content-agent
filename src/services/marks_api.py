"""HTTP client for Marks API to fetch price data."""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

import httpx

from src.config import get_settings


class MarksAPIClient:
    """Client for fetching price data from Marks API."""

    def __init__(self, base_url: Optional[str] = None):
        settings = get_settings()
        self.base_url = base_url or settings.marks_api_url
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_current_price(self, pair: str) -> Optional[Dict[str, Any]]:
        """
        Get current price for a trading pair.

        Args:
            pair: Trading pair (e.g., 'USDTNGN', 'USDTARS')

        Returns:
            Dict with price data or None if not available
        """
        if not self.base_url:
            return None

        try:
            client = await self._get_client()
            response = await client.get(f"/price/{pair}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching price for {pair}: {e}")
            return None

    async def get_price_change(
        self,
        pair: str,
        period: str = "7d",
    ) -> Optional[Dict[str, Any]]:
        """
        Get price change over a period.

        Args:
            pair: Trading pair
            period: Time period ('1d', '7d', '30d')

        Returns:
            Dict with change data or None if not available
        """
        if not self.base_url:
            return None

        try:
            client = await self._get_client()
            response = await client.get(f"/price/{pair}/change", params={"period": period})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching price change for {pair}: {e}")
            return None

    async def get_market_summary(self) -> Optional[Dict[str, Any]]:
        """
        Get summary of all supported markets.

        Returns:
            Dict with market summary or None if not available
        """
        if not self.base_url:
            return None

        try:
            client = await self._get_client()
            response = await client.get("/markets/summary")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching market summary: {e}")
            return None

    async def get_platform_metrics(self) -> Optional[Dict[str, Any]]:
        """
        Get platform metrics (volume, users, etc.).

        Returns:
            Dict with metrics or None if not available
        """
        if not self.base_url:
            return None

        try:
            client = await self._get_client()
            response = await client.get("/metrics")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching platform metrics: {e}")
            return None

    async def get_weekly_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the week's market data for content generation.

        Returns:
            Dict with weekly summary data
        """
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pairs": {},
        }

        # Supported pairs
        pairs = ["USDTNGN", "USDTARS", "USDTCOP"]

        for pair in pairs:
            current = await self.get_current_price(pair)
            change = await self.get_price_change(pair, "7d")

            summary["pairs"][pair] = {
                "current_price": current.get("price") if current else None,
                "weekly_change_pct": change.get("change_pct") if change else None,
                "weekly_high": change.get("high") if change else None,
                "weekly_low": change.get("low") if change else None,
            }

        # Platform metrics
        metrics = await self.get_platform_metrics()
        if metrics:
            summary["platform"] = {
                "weekly_volume": metrics.get("weekly_volume"),
                "active_users": metrics.get("active_users"),
                "total_trades": metrics.get("total_trades"),
            }

        return summary


# Singleton instance
_marks_client: Optional[MarksAPIClient] = None


def get_marks_client() -> MarksAPIClient:
    """Get the Marks API client singleton instance."""
    global _marks_client
    if _marks_client is None:
        _marks_client = MarksAPIClient()
    return _marks_client

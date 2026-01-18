"""Variety management for content topic and angle rotation."""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Set
from collections import defaultdict

from src.models.content import ContentPillar, ContentType
from src.services.history_service import HistoryService


class VarietyManager:
    """Manage content variety to avoid repetition."""

    # Predefined topic pools for each pillar
    TOPIC_POOLS: Dict[ContentPillar, List[str]] = {
        ContentPillar.MARKET_COMMENTARY: [
            "NGN weekly performance",
            "ARS weekly performance",
            "COP weekly performance",
            "Cross-currency comparison",
            "P2P spread analysis",
            "Central bank impact",
            "Inflation data reaction",
            "FX reserve changes",
            "Parallel market dynamics",
            "Global macro impact on EM",
        ],
        ContentPillar.EDUCATION: [
            "What are perpetuals",
            "Understanding leverage",
            "Funding rates explained",
            "Hedging with perpetuals",
            "Long vs short positions",
            "Margin and liquidation",
            "Position sizing basics",
            "Risk management",
            "Reading order books",
            "Technical vs fundamental",
            "Dollar-cost averaging",
            "Stop losses and take profits",
        ],
        ContentPillar.PRODUCT: [
            "Trading interface walkthrough",
            "Deposit and withdrawal",
            "Leverage options",
            "Supported pairs",
            "Fee structure",
            "Mobile experience",
            "Order types",
            "Position management",
            "Account security",
            "API access",
        ],
        ContentPillar.SOCIAL_PROOF: [
            "Volume milestone",
            "User growth",
            "Community highlight",
            "Trader success story",
            "Platform uptime",
            "New market launch",
            "Partnership announcement",
            "Feature release",
        ],
    }

    # Angle variations for each topic type
    ANGLE_VARIATIONS = [
        "breaking news",
        "data deep-dive",
        "simple explainer",
        "comparison",
        "historical context",
        "step-by-step guide",
        "myth-busting",
        "quick tip",
        "case study",
        "FAQ format",
        "thread format",
        "single insight",
    ]

    def __init__(
        self,
        history_service: Optional[HistoryService] = None,
        lookback_days: int = 30,
    ):
        self.history_service = history_service or HistoryService()
        self.lookback_days = lookback_days

    async def get_topics_to_avoid(self) -> List[str]:
        """Get list of topics used in the lookback period."""
        return await self.history_service.get_recent_topics(days=self.lookback_days)

    async def get_angles_to_avoid(self) -> List[str]:
        """Get list of angles used in the lookback period."""
        return await self.history_service.get_recent_angles(days=self.lookback_days)

    async def get_available_topics(self, pillar: ContentPillar) -> List[str]:
        """Get topics that haven't been used recently for a pillar."""
        used_topics = set(await self.get_topics_to_avoid())
        pool = self.TOPIC_POOLS.get(pillar, [])

        # Return topics not in used set (case-insensitive comparison)
        used_lower = {t.lower() for t in used_topics}
        available = [t for t in pool if t.lower() not in used_lower]

        # If all topics used, return the full pool (will need to vary angle)
        return available if available else pool

    async def get_available_angles(self) -> List[str]:
        """Get angles that haven't been used recently."""
        used_angles = set(await self.get_angles_to_avoid())
        used_lower = {a.lower() for a in used_angles}

        available = [a for a in self.ANGLE_VARIATIONS if a.lower() not in used_lower]
        return available if available else self.ANGLE_VARIATIONS

    async def suggest_topic_angle(
        self,
        pillar: ContentPillar,
    ) -> Dict[str, str]:
        """
        Suggest a topic and angle combination for a pillar.

        Returns:
            Dict with 'topic' and 'angle' keys
        """
        topics = await self.get_available_topics(pillar)
        angles = await self.get_available_angles()

        # Pick first available (they're already filtered for recency)
        topic = topics[0] if topics else "General update"
        angle = angles[0] if angles else "single insight"

        return {
            "topic": topic,
            "angle": angle,
        }

    async def get_weekly_schedule(self) -> List[Dict[str, any]]:
        """
        Generate a varied weekly content schedule.

        Returns:
            List of dicts with day, pillar, suggested_topic, suggested_angle
        """
        schedule = [
            {"day": "monday", "pillar": ContentPillar.MARKET_COMMENTARY},
            {"day": "tuesday", "pillar": ContentPillar.EDUCATION},
            {"day": "wednesday", "pillar": ContentPillar.PRODUCT},
            {"day": "thursday", "pillar": ContentPillar.EDUCATION},
            {"day": "friday", "pillar": ContentPillar.SOCIAL_PROOF},
            {"day": "saturday", "pillar": ContentPillar.MARKET_COMMENTARY},
            {"day": "sunday", "pillar": ContentPillar.EDUCATION},
        ]

        # Track what we've suggested to avoid intra-week repetition
        used_topics: Set[str] = set()
        used_angles: Set[str] = set()

        result = []
        for item in schedule:
            pillar = item["pillar"]

            # Get available topics excluding what we've already scheduled this week
            all_available = await self.get_available_topics(pillar)
            available_topics = [t for t in all_available if t not in used_topics]
            if not available_topics:
                available_topics = all_available

            # Get available angles excluding what we've already scheduled
            all_angles = await self.get_available_angles()
            available_angles = [a for a in all_angles if a not in used_angles]
            if not available_angles:
                available_angles = all_angles

            topic = available_topics[0] if available_topics else "General update"
            angle = available_angles[0] if available_angles else "single insight"

            used_topics.add(topic)
            used_angles.add(angle)

            result.append({
                "day": item["day"],
                "pillar": pillar,
                "suggested_topic": topic,
                "suggested_angle": angle,
            })

        return result

    async def check_variety_health(self) -> Dict[str, any]:
        """
        Check the health of content variety.

        Returns:
            Dict with variety metrics and warnings
        """
        recent_content = await self.history_service.get_recent(days=self.lookback_days)

        # Count by pillar
        pillar_counts: Dict[str, int] = defaultdict(int)
        for item in recent_content:
            if item.pillar:
                pillar_counts[item.pillar.value] += 1

        # Count unique topics and angles
        unique_topics = len(set(item.topic for item in recent_content if item.topic))
        unique_angles = len(set(item.angle for item in recent_content if item.angle))

        # Check for warnings
        warnings = []

        # Warn if any pillar is underrepresented
        total = sum(pillar_counts.values())
        if total > 0:
            for pillar in ContentPillar:
                count = pillar_counts.get(pillar.value, 0)
                ratio = count / total
                if ratio < 0.1:
                    warnings.append(f"{pillar.value} is underrepresented ({count}/{total} posts)")

        # Warn if variety is low
        if total > 7 and unique_topics < total * 0.5:
            warnings.append(f"Low topic variety: {unique_topics} unique topics in {total} posts")

        if total > 7 and unique_angles < total * 0.3:
            warnings.append(f"Low angle variety: {unique_angles} unique angles in {total} posts")

        return {
            "total_posts": total,
            "pillar_distribution": dict(pillar_counts),
            "unique_topics": unique_topics,
            "unique_angles": unique_angles,
            "warnings": warnings,
            "health": "good" if not warnings else "needs_attention",
        }


# Singleton instance
_variety_manager: Optional[VarietyManager] = None


def get_variety_manager() -> VarietyManager:
    """Get the variety manager singleton instance."""
    global _variety_manager
    if _variety_manager is None:
        _variety_manager = VarietyManager()
    return _variety_manager

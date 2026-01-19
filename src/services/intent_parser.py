"""Intent parser for natural language Slack commands."""

import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import anthropic

from src.config import get_settings


@dataclass
class ParsedIntent:
    """Result of parsing a natural language message."""
    intent: str
    confidence: float
    entities: Dict[str, Any]
    clarification_needed: Optional[str] = None


class IntentParser:
    """Parse natural language messages into structured intents."""

    SUPPORTED_INTENTS = [
        "add_voice",
        "add_monitor",
        "remove_account",
        "list_voices",
        "list_monitors",
        "tag_voice",
        "refresh_voices",
        "generate_post",
        "help",
        "unknown",
    ]

    VALID_PILLARS = ["market_commentary", "education", "product", "social_proof"]
    VALID_CATEGORIES = ["nigeria", "argentina", "colombia", "global_macro", "crypto_defi", "reply_target"]

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.anthropic_api_key
        self._client: Optional[anthropic.Anthropic] = None

    def _get_client(self) -> anthropic.Anthropic:
        """Get or create the Anthropic client."""
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _get_system_prompt(self) -> str:
        """Get the system prompt for intent parsing."""
        return """You are parsing Slack messages for a content management bot. Extract the user's intent and entities.

IMPORTANT: You may receive conversation history. Use it to understand context:
- "this one too @handle" means repeat the previous action with the new handle
- "same for @handle" means apply the same action/category as before
- "also monitor @handle" means add_monitor with the same category as the previous add_monitor
- If the user provides just a handle or category, infer intent from recent context

Available intents:
- add_voice: Add a Twitter account as a voice reference (to mimic their writing style)
- add_monitor: Add a Twitter account to monitor for news
- remove_account: Stop monitoring an account or remove a voice reference
- list_voices: List voice reference accounts
- list_monitors: List monitored accounts (optionally by category)
- tag_voice: Update which pillars a voice applies to
- refresh_voices: Refresh voice samples from Twitter
- generate_post: Generate content for a pillar
- help: User wants help or doesn't know what the bot can do
- unknown: Can't determine intent or message is unrelated to bot functions

Content pillars: market_commentary, education, product, social_proof
Account categories: nigeria, argentina, colombia, global_macro, crypto_defi, reply_target
Priority: 1 (high), 2 (medium), 3 (low) - default is 2

For Twitter handles:
- Extract just the username without @
- Common variations: "kobeissi", "@KobeissiLetter", "the kobeissi letter" should all become "KobeissiLetter"

For pillars:
- "market commentary" or "market" -> "market_commentary"
- "education" or "educational" -> "education"
- "product" -> "product"
- "social proof" or "testimonials" -> "social_proof"

For categories:
- "nigeria" or "nigerian" or "NGN" or "naira" -> "nigeria"
- "argentina" or "argentine" or "ARS" or "peso" -> "argentina"
- "colombia" or "colombian" or "COP" -> "colombia"
- "global" or "macro" -> "global_macro"
- "crypto" or "defi" -> "crypto_defi"

Return ONLY valid JSON (no markdown, no explanation):
{
  "intent": "one of the intents above",
  "confidence": 0.0 to 1.0,
  "entities": {
    "handle": "twitter_handle or null",
    "pillars": ["pillar1", "pillar2"] or [],
    "category": "category or null",
    "priority": 1-3 or null,
    "topic": "topic hint or null"
  },
  "clarification_needed": "question to ask user, or null if clear"
}

Examples:
- "add kobeissi as a voice for market commentary" -> add_voice, handle: "KobeissiLetter", pillars: ["market_commentary"]
- "generate an education post about funding rates" -> generate_post, pillars: ["education"], topic: "funding rates"
- "what voices do we have?" -> list_voices
- "monitor central bank of nigeria, high priority" -> add_monitor, handle needs clarification (ask for Twitter handle)
- "hello" or "thanks" -> unknown (friendly but not actionable)

Contextual examples (when conversation history is provided):
- Previous: "add @FinanzasArgy to monitor for argentina", Current: "this one too @perfilcom" -> add_monitor, handle: "perfilcom", category: "argentina"
- Previous: "monitor @CBNgov for nigeria", Current: "@vaborzi too" -> add_monitor, handle: "vaborzi", category: "nigeria"
- Previous: "add @someaccount as voice", Current: "also add @another" -> add_voice, handle: "another\""""

    async def parse(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> ParsedIntent:
        """
        Parse a natural language message into a structured intent.

        Args:
            message: The user's message
            conversation_history: Optional list of recent messages for context
                Each dict has 'role' ('user' or 'assistant') and 'content'

        Returns:
            ParsedIntent with intent, confidence, entities, and optional clarification
        """
        if not message or not message.strip():
            return ParsedIntent(
                intent="unknown",
                confidence=0.0,
                entities={},
                clarification_needed=None,
            )

        try:
            client = self._get_client()

            # Build message with conversation context
            if conversation_history:
                context_lines = ["Recent conversation:"]
                for msg in conversation_history[-6:]:  # Last 6 messages max
                    role = "User" if msg["role"] == "user" else "Bot"
                    context_lines.append(f"{role}: {msg['content']}")
                context_lines.append(f"\nCurrent message to parse: {message}")
                full_message = "\n".join(context_lines)
            else:
                full_message = message

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                system=self._get_system_prompt(),
                messages=[{"role": "user", "content": full_message}],
            )

            response_text = response.content[0].text.strip()

            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            result = json.loads(response_text)

            # Validate and normalize the result
            intent = result.get("intent", "unknown")
            if intent not in self.SUPPORTED_INTENTS:
                intent = "unknown"

            confidence = float(result.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))  # Clamp to 0-1

            entities = result.get("entities", {})

            # Normalize pillars
            if "pillars" in entities and entities["pillars"]:
                entities["pillars"] = [
                    p for p in entities["pillars"]
                    if p in self.VALID_PILLARS
                ]

            # Normalize category
            if "category" in entities and entities["category"]:
                if entities["category"] not in self.VALID_CATEGORIES:
                    entities["category"] = None

            return ParsedIntent(
                intent=intent,
                confidence=confidence,
                entities=entities,
                clarification_needed=result.get("clarification_needed"),
            )

        except json.JSONDecodeError as e:
            print(f"Error parsing intent response: {e}")
            print(f"Raw response: {response_text[:200] if response_text else 'EMPTY'}")
            return ParsedIntent(
                intent="unknown",
                confidence=0.0,
                entities={},
                clarification_needed=None,
            )
        except Exception as e:
            print(f"Error parsing intent: {e}")
            return ParsedIntent(
                intent="unknown",
                confidence=0.0,
                entities={},
                clarification_needed=None,
            )


# Singleton instance
_intent_parser: Optional[IntentParser] = None


def get_intent_parser() -> IntentParser:
    """Get the intent parser singleton instance."""
    global _intent_parser
    if _intent_parser is None:
        _intent_parser = IntentParser()
    return _intent_parser

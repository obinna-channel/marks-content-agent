# Plan: Conversational Slack Bot

Make the Slack bot more natural to interact with - like talking to a coworker instead of typing strict commands.

---

## Current State

Users must type exact commands:
```
!add-voice @KobeissiLetter market_commentary
!generate market_commentary
!list-monitors nigeria
```

Problems:
- Must remember exact syntax
- Underscores required (market_commentary not "market commentary")
- Must use ! prefix
- No conversational flow

---

## Goal

Users can type naturally:
```
"add kobeissi as a voice for market commentary"
"generate a market commentary post"
"show me the nigeria monitors"
"what voices do we have?"
```

---

## Approach: Hybrid Intent Parser

Keep `!commands` for power users, but parse natural language for everything else.

### Architecture

```
User Message
     │
     ▼
┌─────────────────┐
│ Starts with ! ? │
└────────┬────────┘
         │
    yes  │  no
    ▼    │   ▼
┌────────┴──────────┐
│ Existing handlers │ → Execute directly
└───────────────────┘
         │
         ▼
┌───────────────────┐
│ Intent Parser     │ → Claude Haiku
│ (extract intent   │
│  + entities)      │
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│ Confidence check  │
└────────┬──────────┘
         │
    high │  low
         │
    ▼    │   ▼
┌────────┴──────────┐
│ Execute action    │ → "I didn't understand..."
└───────────────────┘
```

---

## Implementation Steps

### Step 1: Create Intent Parser Service

New file: `src/services/intent_parser.py`

**Responsibilities:**
- Take a natural language message
- Call Claude Haiku to extract intent and entities
- Return structured result

**Intents to support:**
| Intent | Entities | Example |
|--------|----------|---------|
| `add_voice` | handle, pillars[] | "add kobeissi as a voice for market commentary" |
| `add_monitor` | handle, category, priority | "monitor the central bank of nigeria, high priority" |
| `remove_account` | handle | "stop monitoring noisyaccount" |
| `list_voices` | - | "what voices do we have?" |
| `list_monitors` | category? | "show nigeria monitors" |
| `tag_voice` | handle, pillars[] | "update kobeissi to cover education too" |
| `refresh_voices` | - | "refresh the voice samples" |
| `generate_post` | pillar, topic? | "write a market commentary post about the naira" |
| `help` | - | "what can you do?" |
| `unknown` | - | (fallback) |

**Response format:**
```json
{
  "intent": "add_voice",
  "confidence": 0.95,
  "entities": {
    "handle": "KobeissiLetter",
    "pillars": ["market_commentary"]
  },
  "clarification_needed": null
}
```

**Low confidence / ambiguous example:**
```json
{
  "intent": "add_voice",
  "confidence": 0.6,
  "entities": {
    "handle": null,
    "pillars": ["market_commentary"]
  },
  "clarification_needed": "Which Twitter handle should I add?"
}
```

### Step 2: Create Intent Prompt

The prompt for Claude Haiku to parse messages:

```
You are parsing Slack messages for a content management bot. Extract the user's intent and entities.

Available intents:
- add_voice: Add a Twitter account as a voice reference
- add_monitor: Add a Twitter account to monitor for news
- remove_account: Stop monitoring an account
- list_voices: List voice reference accounts
- list_monitors: List monitored accounts (optionally by category)
- tag_voice: Update which pillars a voice applies to
- refresh_voices: Refresh voice samples from Twitter
- generate_post: Generate content for a pillar
- help: User wants help
- unknown: Can't determine intent

Pillars: market_commentary, education, product, social_proof
Categories: nigeria, argentina, colombia, global_macro, crypto_defi, reply_target
Priority: 1 (high), 2 (medium), 3 (low) - default is 2

For Twitter handles, extract just the username without @.

Return JSON only:
{
  "intent": "...",
  "confidence": 0.0-1.0,
  "entities": { ... },
  "clarification_needed": "question if needed, else null"
}
```

### Step 3: Update Slack Bot Message Handler

Modify `src/integrations/slack_bot.py`:

1. Add catch-all message handler for non-command messages
2. Call intent parser
3. If confidence > 0.7 and no clarification needed → execute
4. If clarification needed → ask follow-up question
5. If confidence < 0.5 → suggest using !help

**Pseudo-code:**
```python
@self.app.event("message")
def handle_message(event, say):
    text = event.get("text", "")

    # Skip if it's a command (handled elsewhere)
    if text.startswith("!"):
        return

    # Skip bot messages, threads handled separately
    if event.get("bot_id") or event.get("thread_ts"):
        return

    # Parse intent
    result = await self.intent_parser.parse(text)

    if result.clarification_needed:
        say(result.clarification_needed)
        return

    if result.confidence < 0.5:
        say("I'm not sure what you mean. Try `!help` to see available commands.")
        return

    # Execute based on intent
    await self._execute_intent(say, result)
```

### Step 4: Add Entity Normalization

Handle variations:
- "market commentary" → "market_commentary"
- "kobeissi" → "KobeissiLetter" (fuzzy match against known accounts?)
- "high priority" → 1
- "nigeria" / "Nigerian" / "NGN" → "nigeria"

This can be done in the intent parser prompt or as post-processing.

### Step 5: Add Confirmation for Destructive Actions

Before executing:
- `remove_account`
- Any action with low-medium confidence (0.5-0.8)

Ask: "Just to confirm, you want me to [action]? Reply 'yes' to confirm."

This requires tracking pending confirmations (in-memory dict keyed by user_id).

---

## File Changes Summary

| File | Changes |
|------|---------|
| `src/services/intent_parser.py` | **NEW** - Intent parsing service |
| `src/integrations/slack_bot.py` | Add natural language handler, call intent parser |
| `src/agent/prompts.py` | Add intent parsing prompt (optional, could be in intent_parser.py) |

---

## Conversation Context (Future Enhancement)

For multi-turn conversations, we'd need to:

1. Track conversation state per user/channel
2. Store context like "we were just talking about adding a voice"
3. Handle follow-ups: "actually make it education instead"

This adds complexity - recommend starting without it and adding later if needed.

---

## Cost & Latency Considerations

**Per natural language message:**
- ~500ms latency for Haiku call
- ~$0.0001-0.0005 per message (very cheap)

**Mitigation:**
- Show typing indicator while parsing
- Cache common phrases (optional)
- Keep !commands for users who want speed

---

## Testing Plan

1. Unit test intent parser with various phrasings
2. Test edge cases:
   - Misspellings ("marekt commentary")
   - Partial info ("add a voice" without handle)
   - Ambiguous ("add kobeissi" - voice or monitor?)
3. Test confirmation flow
4. Test fallback to !help

---

## Rollout

1. Deploy behind a feature flag initially
2. Test in a dedicated channel
3. Monitor for misinterpretations
4. Tune prompt based on real usage
5. Roll out to main channel

---

## Example Conversations

**Simple:**
```
User: generate an education post about funding rates
Bot: ✨ Generating education post...
     [post content]
```

**With clarification:**
```
User: add kobeissi as a voice
Bot: Which pillars should @KobeissiLetter cover?
     Options: market_commentary, education, product, social_proof
User: market commentary and education
Bot: ✅ Added @KobeissiLetter as voice reference for market_commentary, education
```

**Ambiguous:**
```
User: add central bank of nigeria
Bot: Should I add @cenaborubank_ng as:
     1. A voice reference (to mimic their style)
     2. A monitored account (to watch for news)
User: monitor it
Bot: What priority? (1=high, 2=medium, 3=low)
User: high
Bot: ✅ Now monitoring @cenaborubank_ng (nigeria, high priority)
```

**Unknown:**
```
User: what's the weather like?
Bot: I'm not sure how to help with that. I can help you manage voice references,
     monitor accounts, and generate content. Try `!help` for available commands.
```

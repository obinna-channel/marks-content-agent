# Plan: Iterative Content Drafting with Learning Extraction

Enable back-and-forth refinement of generated content in Slack threads, then automatically extract and store learnings for future generations.

---

## Current State

1. User runs `!generate market_commentary`
2. Bot posts draft
3. User can reply with feedback → stored for future generations
4. No way to revise the current draft

**Problem:** If the draft isn't right, user has to manually edit or regenerate from scratch.

---

## Goal

1. User generates content
2. User can iterate on the draft via thread replies
3. When satisfied, user approves
4. Bot extracts generalizable learnings and asks to confirm
5. Confirmed learnings stored for future generations

---

## User Flow

### Basic Iteration

```
User: !generate market_commentary

Bot: 📝 Generated Market Commentary Post
     Topic: Naira volatility
     ─────────────────────
     Markets flying blind 🌫️📊
     Data feeds down = pure price action
     Support/resistance become everything
     ...
     ─────────────────────
     💬 Reply in thread to refine, react ✅ when done

User (in thread): less emojis, more professional tone

Bot (in thread): 📝 Revision 1
     ─────────────────────
     Markets flying blind.
     With data feeds down, price action rules.
     Support and resistance levels become critical.
     ...
     ─────────────────────
     💬 Reply to refine more, react ✅ when done

User (in thread): shorter, make it punchier

Bot (in thread): 📝 Revision 2
     ─────────────────────
     Data feeds down. Price action up.
     When the screens go dark, support and
     resistance are all that matter.
     ─────────────────────

User: reacts with ✅

Bot (in thread): ✅ Final version locked!

     Based on your edits, I noticed these preferences:
     • Minimal or no emojis
     • Professional tone
     • Concise, punchy style

     Should I remember these for future market_commentary posts?
     Reply: "yes" / "yes, except [x]" / "no"

User (in thread): yes

Bot (in thread): 📚 Got it! I'll apply these preferences to future
     market_commentary posts.
```

### Signals for "Done"

Detect approval via:
- ✅ reaction on a revision
- Text: "perfect", "done", "approved", "use this", "looks good", "👍"
- Explicit: "finalize", "lock it"

---

## Architecture

### Data Structures

**Draft Session** (in-memory, keyed by thread_ts):
```python
{
    "thread_ts": "1234567890.123456",
    "channel": "C0123456",
    "pillar": "market_commentary",
    "topic": "Naira volatility",
    "original_prompt": "Generate a market commentary post...",
    "drafts": [
        {"version": 0, "content": "Markets flying blind 🌫️📊...", "timestamp": "..."},
        {"version": 1, "content": "Markets flying blind...", "revision_request": "less emojis", "timestamp": "..."},
        {"version": 2, "content": "Data feeds down...", "revision_request": "shorter", "timestamp": "..."},
    ],
    "status": "iterating",  # iterating | approved | learnings_pending | complete
    "created_at": "...",
    "approved_at": null,
}
```

**Extracted Learning** (to be confirmed):
```python
{
    "pillar": "market_commentary",
    "learnings": [
        "Minimal or no emojis",
        "Professional tone",
        "Concise, punchy style"
    ],
    "thread_ts": "1234567890.123456",
}
```

### Flow Diagram

```
┌─────────────────────────────────┐
│  !generate <pillar>             │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│  Generate initial draft         │
│  Store in draft_sessions        │
│  Post to channel                │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│  User replies in thread         │◄────────┐
└───────────────┬─────────────────┘         │
                │                           │
                ▼                           │
┌─────────────────────────────────┐         │
│  Is it an approval signal?      │         │
└───────────────┬─────────────────┘         │
                │                           │
        no      │    yes                    │
        │       │                           │
        ▼       ▼                           │
┌───────────────────┐  ┌──────────────────┐ │
│ Send to Claude:   │  │ Extract learnings│ │
│ - Original prompt │  │ from revision    │ │
│ - All drafts      │  │ history          │ │
│ - New request     │  └────────┬─────────┘ │
└─────────┬─────────┘           │           │
          │                     ▼           │
          ▼           ┌──────────────────┐  │
┌─────────────────┐   │ Ask user to      │  │
│ Post revision   │   │ confirm learnings│  │
│ in thread       │   └────────┬─────────┘  │
└─────────┬───────┘            │            │
          │                    ▼            │
          │           ┌──────────────────┐  │
          │           │ User confirms?   │  │
          │           └────────┬─────────┘  │
          │                    │            │
          │            yes     │    no      │
          │             │      │            │
          │             ▼      ▼            │
          │    ┌─────────────────────────┐  │
          │    │ Store in voice_feedback │  │
          │    │ (or skip)               │  │
          │    └─────────────────────────┘  │
          │                                 │
          └─────────────────────────────────┘
```

---

## Implementation Steps

### Step 1: Update Draft Session Tracking

Modify `slack_bot.py`:

Currently we track `generated_posts` as:
```python
self.generated_posts[message_ts] = {
    "pillar": pillar,
    "content": content,
    "topic": topic,
}
```

Expand to:
```python
self.draft_sessions[thread_ts] = {
    "pillar": pillar,
    "topic": topic,
    "original_prompt": prompt,  # Need to capture this
    "drafts": [
        {"version": 0, "content": content, "revision_request": None}
    ],
    "status": "iterating",
    "created_at": datetime.utcnow(),
}
```

### Step 2: Create Revision Handler

New method in `slack_bot.py`:

```python
async def _handle_revision_request(self, say, thread_ts: str, request: str):
    """Handle a revision request in a draft thread."""
    session = self.draft_sessions.get(thread_ts)
    if not session:
        return

    # Build conversation history for Claude
    messages = self._build_revision_messages(session, request)

    # Get revision from Claude
    revised_content = await self.generator.revise_content(
        pillar=session["pillar"],
        messages=messages,
    )

    # Store new draft
    session["drafts"].append({
        "version": len(session["drafts"]),
        "content": revised_content,
        "revision_request": request,
    })

    # Post revision
    say(
        text=f"📝 Revision {len(session['drafts']) - 1}\n```{revised_content}```\n\n💬 Reply to refine more, react ✅ when done",
        thread_ts=thread_ts,
    )
```

### Step 3: Add Revision Method to Generator

New method in `generator.py`:

```python
async def revise_content(
    self,
    pillar: ContentPillar,
    messages: List[Dict],  # Conversation history
) -> str:
    """Revise content based on conversation history."""

    marks_context = self._get_marks_context()

    system_prompt = f"""You are revising social media content for Marks Exchange.

{marks_context}

The user will provide the original draft and revision requests.
Apply the requested changes while maintaining the core message.
Return ONLY the revised content, no explanation."""

    response = self.client.messages.create(
        model="claude-sonnet-4-20250514",  # Sonnet for speed on revisions
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )

    return response.content[0].text.strip()
```

### Step 4: Detect Approval Signals

```python
def _is_approval_signal(self, text: str, event: dict) -> bool:
    """Check if message/reaction signals approval."""

    # Check for ✅ reaction
    if event.get("reaction") == "white_check_mark":
        return True

    # Check for approval text
    approval_phrases = [
        "perfect", "done", "approved", "use this", "looks good",
        "that works", "love it", "great", "finalize", "lock it",
        "👍", "✅", "ship it"
    ]
    text_lower = text.lower().strip()
    return any(phrase in text_lower for phrase in approval_phrases)
```

### Step 5: Create Learning Extractor

New method in `generator.py`:

```python
async def extract_learnings(
    self,
    pillar: ContentPillar,
    drafts: List[Dict],
) -> List[str]:
    """Extract generalizable learnings from revision history."""

    # Build the revision history
    history = []
    for i, draft in enumerate(drafts):
        if i == 0:
            history.append(f"Original draft:\n{draft['content']}")
        else:
            history.append(f"User requested: {draft['revision_request']}")
            history.append(f"Revised to:\n{draft['content']}")

    prompt = f"""Analyze this content revision history and extract GENERALIZABLE style preferences.

{chr(10).join(history)}

Rules:
- Only extract preferences that should apply to ALL future {pillar.value.replace('_', ' ')} posts
- Ignore one-off requests (like "mention the naira" - too specific)
- Focus on tone, style, length, formatting preferences
- Be concise - each learning should be 3-6 words
- Return as JSON array of strings
- If no generalizable learnings, return empty array

Examples of good learnings:
- "Minimal or no emojis"
- "Professional, serious tone"
- "Keep under 200 characters"
- "Use bullet points"
- "Avoid hashtags"

Examples of BAD learnings (too specific):
- "Mention the naira" (one-off topic)
- "Talk about funding rates" (specific content)

Return JSON array only:"""

    response = self.client.messages.create(
        model="claude-haiku-3-5-20241022",  # Haiku is fine for extraction
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        return json.loads(response.content[0].text)
    except:
        return []
```

### Step 6: Handle Approval and Learning Confirmation

```python
async def _handle_approval(self, say, thread_ts: str):
    """Handle when user approves a draft."""
    session = self.draft_sessions.get(thread_ts)
    if not session:
        return

    session["status"] = "approved"
    session["approved_at"] = datetime.utcnow()

    # Only extract learnings if there were revisions
    if len(session["drafts"]) > 1:
        learnings = await self.generator.extract_learnings(
            pillar=ContentPillar(session["pillar"]),
            drafts=session["drafts"],
        )

        if learnings:
            session["pending_learnings"] = learnings
            session["status"] = "learnings_pending"

            pillar_name = session["pillar"].replace("_", " ")
            learnings_text = "\n".join(f"• {l}" for l in learnings)

            say(
                text=f"✅ Final version locked!\n\nBased on your edits, I noticed these preferences:\n{learnings_text}\n\nShould I remember these for future {pillar_name} posts?\nReply: \"yes\" / \"yes, except [x]\" / \"no\"",
                thread_ts=thread_ts,
            )
            return

    # No learnings to extract
    say(text="✅ Final version locked!", thread_ts=thread_ts)
    session["status"] = "complete"
```

### Step 7: Handle Learning Confirmation

```python
async def _handle_learning_confirmation(self, say, thread_ts: str, response: str):
    """Handle user's response to learning confirmation."""
    session = self.draft_sessions.get(thread_ts)
    if not session or session["status"] != "learnings_pending":
        return

    response_lower = response.lower().strip()
    learnings = session.get("pending_learnings", [])

    if response_lower == "no":
        say(text="👍 No problem, preferences not saved.", thread_ts=thread_ts)
        session["status"] = "complete"
        return

    # Handle "yes, except X"
    if "except" in response_lower:
        # Parse which to exclude
        # For now, simple approach - ask Claude to filter
        filtered = await self._filter_learnings(learnings, response)
        learnings = filtered

    # Store learnings
    pillar = ContentPillar(session["pillar"])
    for learning in learnings:
        await self.feedback_service.create(
            pillar=pillar,
            original_content=session["drafts"][-1]["content"],
            feedback_text=learning,
            slack_thread_ts=thread_ts,
        )

    say(
        text=f"📚 Got it! I'll apply these preferences to future {session['pillar'].replace('_', ' ')} posts.",
        thread_ts=thread_ts,
    )
    session["status"] = "complete"
```

### Step 8: Update Thread Reply Router

Update the existing thread reply handler to route appropriately:

```python
@self.app.event("message")
def handle_thread_reply(event, say):
    """Route thread replies to appropriate handler."""
    thread_ts = event.get("thread_ts")
    text = event.get("text", "")

    if not thread_ts or thread_ts == event.get("ts"):
        return
    if text.startswith("!"):
        return

    session = self.draft_sessions.get(thread_ts)

    if not session:
        # Not a draft thread - might be feedback on old post
        if thread_ts in self.generated_posts:
            asyncio.run(self._store_feedback(say, thread_ts, text))
        return

    # Handle based on session status
    if session["status"] == "iterating":
        if self._is_approval_signal(text, event):
            asyncio.run(self._handle_approval(say, thread_ts))
        else:
            asyncio.run(self._handle_revision_request(say, thread_ts, text))

    elif session["status"] == "learnings_pending":
        asyncio.run(self._handle_learning_confirmation(say, thread_ts, text))
```

### Step 9: Handle Reaction Events

```python
@self.app.event("reaction_added")
def handle_reaction(event, say):
    """Handle reactions - specifically ✅ for approval."""
    if event.get("reaction") != "white_check_mark":
        return

    item = event.get("item", {})
    thread_ts = item.get("ts")  # The message that was reacted to
    channel = item.get("channel")

    session = self.draft_sessions.get(thread_ts)
    if session and session["status"] == "iterating":
        asyncio.run(self._handle_approval(say, thread_ts))
```

---

## File Changes Summary

| File | Changes |
|------|---------|
| `src/integrations/slack_bot.py` | Add draft session tracking, revision handler, approval detection, learning confirmation flow, reaction handler |
| `src/agent/generator.py` | Add `revise_content()` and `extract_learnings()` methods |
| `src/services/feedback_service.py` | No changes needed - reuse existing |

---

## Session Cleanup

Draft sessions should be cleaned up to prevent memory leaks:

```python
async def _cleanup_old_sessions(self):
    """Remove sessions older than 24 hours."""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    expired = [
        ts for ts, session in self.draft_sessions.items()
        if session["created_at"] < cutoff
    ]
    for ts in expired:
        del self.draft_sessions[ts]
```

Run periodically or on each new message.

---

## Edge Cases

1. **User abandons thread** - Session times out after 24h, no learnings stored
2. **User says "no" to learnings** - Respect it, don't store
3. **Multiple people reply** - Only original requester can approve (check user_id)
4. **Very long revision chains** - Cap at 10 revisions, suggest starting fresh
5. **User wants to restart** - Detect "start over" / "from scratch" → regenerate

---

## Future Enhancements

1. **Show diff** - Highlight what changed between versions
2. **Undo** - "Go back to version 2"
3. **Branch** - "Try a different direction" → fork the draft
4. **A/B options** - "Give me two versions" → present both
5. **Save as template** - "Save this structure for reuse"

---

## Example: Full Conversation

```
User: !generate education funding rates

Bot: 📝 Generated Education Post
     Topic: Understanding Funding Rates
     ─────────────────────
     Funding rates decoded 📊

     🔵 Positive rate = longs pay shorts
     🔴 Negative rate = shorts pay longs
     📈 High positive = overcrowded longs (reversal risk)
     📉 Deep negative = extreme fear (bounce potential)

     Pro tip: When funding hits extremes, contrarian
     trades often pay.

     Trade smarter with real-time funding data on
     Marks Exchange.
     ─────────────────────
     💬 Reply in thread to refine, react ✅ when done

User (thread): too many emojis, make it cleaner

Bot (thread): 📝 Revision 1
     ─────────────────────
     Funding rates decoded

     • Positive rate = longs pay shorts
     • Negative rate = shorts pay longs
     • High positive = overcrowded longs (reversal risk)
     • Deep negative = extreme fear (bounce potential)

     Pro tip: When funding hits extremes, contrarian
     trades often pay.

     Trade smarter with real-time funding data on
     Marks Exchange.
     ─────────────────────
     💬 Reply to refine more, react ✅ when done

User (thread): remove the marks plug at the end, feels salesy

Bot (thread): 📝 Revision 2
     ─────────────────────
     Funding rates decoded

     • Positive rate = longs pay shorts
     • Negative rate = shorts pay longs
     • High positive = overcrowded longs (reversal risk)
     • Deep negative = extreme fear (bounce potential)

     Pro tip: When funding hits extremes, contrarian
     trades often pay.
     ─────────────────────

User (thread): ✅

Bot (thread): ✅ Final version locked!

     Based on your edits, I noticed these preferences:
     • Minimal or no emojis
     • Use bullet points for lists
     • Avoid promotional plugs

     Should I remember these for future education posts?
     Reply: "yes" / "yes, except [x]" / "no"

User (thread): yes except the bullet points thing, that was just for this one

Bot (thread): 📚 Got it! I'll remember for future education posts:
     • Minimal or no emojis
     • Avoid promotional plugs
```

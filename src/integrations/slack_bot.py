"""Slack bot for handling commands via messages."""
print("[SLACKBOT] Module loading...", flush=True)

import re
import asyncio
import sys
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict

print("[SLACKBOT] Importing slack_bolt...", flush=True)
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

print("[SLACKBOT] Importing local modules...", flush=True)
from src.config import get_settings
from src.services.account_service import AccountService
from src.services.tweet_service import TweetService
from src.services.voice_sampler import get_voice_sampler
from src.services.feedback_service import get_feedback_service
from src.services.intent_parser import get_intent_parser
from src.models.content import MonitoredAccountCreate, AccountCategory, ContentPillar
from src.integrations.twitter import get_twitter_client
from src.agent.generator import get_content_generator

print("[SLACKBOT] All imports complete", flush=True)


class SlackBot:
    """Slack bot that handles commands via messages."""

    def __init__(self):
        settings = get_settings()
        self.app = App(token=settings.slack_bot_token)
        self.app_token = settings.slack_app_token
        self.account_service = AccountService()
        self.tweet_service = TweetService()
        self.voice_sampler = get_voice_sampler()
        self.feedback_service = get_feedback_service()
        self.intent_parser = get_intent_parser()
        self.twitter = get_twitter_client()
        self.generator = get_content_generator()

        # Track generated posts for feedback (message_ts -> {pillar, content})
        self.generated_posts = {}

        # Track draft sessions for iterative refinement (thread_ts -> session)
        self.draft_sessions = {}

        # Track pending confirmations for ambiguous intents (user_id -> {intent, entities})
        self.pending_confirmations = {}

        # Track conversation history per user for context (user_id -> list of messages)
        self.conversation_history = {}

        # Register message handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register all message handlers."""

        @self.app.message(re.compile(r"^!add-voice\s+@?(\w+)(?:\s+(.+))?", re.IGNORECASE))
        def handle_add_voice(message, say, context):
            """Handle !add-voice @handle [pillar1,pillar2,...]"""
            matches = context["matches"]
            handle = matches[0]
            pillars_str = matches[1] if len(matches) > 1 and matches[1] else ""
            # Parse comma-separated pillars
            pillars = [p.strip().lower() for p in pillars_str.split(",") if p.strip()] if pillars_str else []

            asyncio.run(self._add_voice_reference(say, handle, pillars))

        @self.app.message(re.compile(r"^!add-monitor\s+@?(\w+)\s+(\w+)(?:\s+(\d))?", re.IGNORECASE))
        def handle_add_monitor(message, say, context):
            """Handle !add-monitor @handle category [priority]"""
            matches = context["matches"]
            handle = matches[0]
            category = matches[1]
            priority = int(matches[2]) if len(matches) > 2 and matches[2] else 2

            asyncio.run(self._add_monitored_account(say, handle, category, priority))

        @self.app.message(re.compile(r"^!remove\s+@?(\w+)", re.IGNORECASE))
        def handle_remove(message, say, context):
            """Handle !remove @handle"""
            handle = context["matches"][0]
            asyncio.run(self._remove_account(say, handle))

        @self.app.message(re.compile(r"^!list-voice", re.IGNORECASE))
        def handle_list_voice(message, say):
            """Handle !list-voice"""
            asyncio.run(self._list_voice_references(say))

        @self.app.message(re.compile(r"^!list-monitors(?:\s+(\w+))?", re.IGNORECASE))
        def handle_list_monitors(message, say, context):
            """Handle !list-monitors [category]"""
            matches = context.get("matches", [])
            category = matches[0] if matches and matches[0] else None
            asyncio.run(self._list_monitored_accounts(say, category))

        @self.app.message(re.compile(r"^!tag-voice\s+@?(\w+)\s+(.+)", re.IGNORECASE))
        def handle_tag_voice(message, say, context):
            """Handle !tag-voice @handle pillar1,pillar2,..."""
            matches = context["matches"]
            handle = matches[0]
            pillars_str = matches[1]
            pillars = [p.strip().lower() for p in pillars_str.split(",") if p.strip()]

            asyncio.run(self._tag_voice_reference(say, handle, pillars))

        @self.app.message(re.compile(r"^!refresh-voice", re.IGNORECASE))
        def handle_refresh_voice(message, say):
            """Handle !refresh-voice"""
            asyncio.run(self._refresh_voice_samples(say))

        @self.app.message(re.compile(r"^!generate\s+(\w+)(?:\s+(.+))?", re.IGNORECASE))
        def handle_generate(message, say, context):
            """Handle !generate pillar [topic]"""
            matches = context["matches"]
            pillar = matches[0].lower()
            topic = matches[1] if len(matches) > 1 and matches[1] else None
            asyncio.run(self._generate_post(say, pillar, topic))

        @self.app.message(re.compile(r"^!help", re.IGNORECASE))
        def handle_help(message, say):
            """Handle !help"""
            self._show_help(say)

        @self.app.event("message")
        def handle_message_event(event, say):
            """Handle all messages - thread replies, natural language, etc."""
            # Skip bot messages
            if event.get("bot_id") or event.get("subtype"):
                return

            thread_ts = event.get("thread_ts")
            message_ts = event.get("ts")
            text = event.get("text", "")
            user_id = event.get("user", "")

            # Skip empty messages
            if not text or not text.strip():
                return

            # Skip commands (handled by regex handlers above)
            if text.startswith("!"):
                return

            # Handle thread replies
            if thread_ts and thread_ts != message_ts:
                # Check if this is a draft session (iterative refinement)
                if thread_ts in self.draft_sessions:
                    asyncio.run(self._handle_draft_reply(say, thread_ts, text, user_id))
                    return
                # Check if this is a suggested tweet thread (from Twitter monitor)
                suggested_tweet = asyncio.run(self._check_suggested_tweet_thread(thread_ts))
                if suggested_tweet:
                    asyncio.run(self._handle_draft_reply(say, thread_ts, text, user_id))
                    return
                # Legacy: feedback on old-style generated posts
                if thread_ts in self.generated_posts:
                    asyncio.run(self._store_feedback(say, thread_ts, text))
                return

            # Handle natural language messages (not in thread, not a command)
            asyncio.run(self._handle_natural_language(say, text, user_id))

        @self.app.event("reaction_added")
        def handle_reaction(event, say):
            """Handle reactions - specifically ✅ for approval."""
            reaction = event.get("reaction", "")
            # Check for checkmark reactions
            if reaction not in ["white_check_mark", "heavy_check_mark", "+1", "thumbsup"]:
                return

            item = event.get("item", {})
            channel = item.get("channel")
            # The message_ts of the message that was reacted to
            reacted_ts = item.get("ts")

            if not reacted_ts or not channel:
                return

            # Check if any draft session contains this message
            for thread_ts, session in self.draft_sessions.items():
                if session.get("status") == "iterating":
                    # Check if reaction was on any draft in this session
                    drafts = session.get("drafts", [])
                    if drafts:
                        last_draft_ts = drafts[-1].get("message_ts")
                        if last_draft_ts == reacted_ts or thread_ts == reacted_ts:
                            asyncio.run(self._handle_approval(say, thread_ts, channel))
                            return

    def _add_to_history(self, user_id: str, role: str, content: str):
        """Add a message to conversation history."""
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []

        self.conversation_history[user_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc),
        })

        # Keep only last 10 messages per user
        if len(self.conversation_history[user_id]) > 10:
            self.conversation_history[user_id] = self.conversation_history[user_id][-10:]

    def _get_history(self, user_id: str) -> List[Dict[str, str]]:
        """Get recent conversation history for a user."""
        if user_id not in self.conversation_history:
            return []

        # Filter to messages from last 10 minutes for relevance
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        recent = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.conversation_history[user_id]
            if msg.get("timestamp", datetime.now(timezone.utc)) > cutoff
        ]
        return recent

    async def _handle_natural_language(self, say, text: str, user_id: str):
        """Parse and handle natural language messages."""
        try:
            # Add user message to history
            self._add_to_history(user_id, "user", text)

            # Check if user is responding to a pending confirmation
            if user_id in self.pending_confirmations:
                await self._handle_confirmation_response(say, text, user_id)
                return

            # Get conversation history for context
            history = self._get_history(user_id)

            # Parse the intent with conversation context
            result = await self.intent_parser.parse(text, conversation_history=history)

            # If clarification is needed, ask and store pending state
            if result.clarification_needed:
                say(result.clarification_needed)
                self._add_to_history(user_id, "assistant", result.clarification_needed)
                self.pending_confirmations[user_id] = {
                    "intent": result.intent,
                    "entities": result.entities,
                    "awaiting": "clarification",
                }
                return

            # If confidence is too low, suggest using !help
            if result.confidence < 0.5:
                # Don't respond to every random message - only if it seems bot-directed
                if any(word in text.lower() for word in ["bot", "help", "generate", "voice", "monitor", "add", "list", "create", "make", "write"]):
                    response = "I'm not sure what you mean. Try `!help` to see available commands, or just ask me naturally like:\n• \"generate a market commentary post\"\n• \"add kobeissi as a voice\"\n• \"what voices do we have?\""
                    say(response)
                    self._add_to_history(user_id, "assistant", response)
                return

            # Execute the intent
            await self._execute_intent(say, result.intent, result.entities, user_id)

        except Exception as e:
            print(f"[SLACKBOT] Error handling natural language: {e}", flush=True)

    async def _handle_confirmation_response(self, say, text: str, user_id: str):
        """Handle user's response to a clarification or confirmation request."""
        pending = self.pending_confirmations.pop(user_id, None)
        if not pending:
            return

        text_lower = text.lower().strip()

        # Check for cancellation
        if text_lower in ["cancel", "nevermind", "never mind", "no", "nope", "stop"]:
            say("Okay, cancelled.")
            return

        # If awaiting clarification, re-parse with the new info
        if pending.get("awaiting") == "clarification":
            # Try to extract the missing info from the response
            # For now, just re-parse the new message and merge
            new_result = await self.intent_parser.parse(text)

            # Merge entities - prefer new values but keep old ones if new is empty
            merged_entities = {**pending["entities"]}
            for key, value in new_result.entities.items():
                if value:  # Only update if new value is non-empty
                    merged_entities[key] = value

            # If still missing required info, ask again
            if new_result.clarification_needed:
                say(new_result.clarification_needed)
                self.pending_confirmations[user_id] = {
                    "intent": pending["intent"],
                    "entities": merged_entities,
                    "awaiting": "clarification",
                }
                return

            # Execute with merged entities
            await self._execute_intent(say, pending["intent"], merged_entities, user_id)

    async def _execute_intent(self, say, intent: str, entities: dict, user_id: str):
        """Execute a parsed intent."""
        try:
            if intent == "add_voice":
                handle = entities.get("handle")
                pillars = entities.get("pillars", [])
                if not handle:
                    msg = "Which Twitter account should I add as a voice reference?"
                    say(msg)
                    self._add_to_history(user_id, "assistant", msg)
                    self.pending_confirmations[user_id] = {
                        "intent": intent,
                        "entities": entities,
                        "awaiting": "clarification",
                    }
                    return
                await self._add_voice_reference(say, handle, pillars)
                # Track action for context
                pillar_str = ", ".join(pillars) if pillars else "all pillars"
                self._add_to_history(user_id, "assistant", f"Added @{handle} as voice reference for {pillar_str}")

            elif intent == "add_monitor":
                handle = entities.get("handle")
                category = entities.get("category")
                priority = entities.get("priority") or 2
                if not handle:
                    msg = "Which Twitter account should I monitor?"
                    say(msg)
                    self._add_to_history(user_id, "assistant", msg)
                    self.pending_confirmations[user_id] = {
                        "intent": intent,
                        "entities": entities,
                        "awaiting": "clarification",
                    }
                    return
                if not category:
                    msg = f"What category is @{handle}? Options: nigeria, argentina, colombia, global_macro, crypto_defi, reply_target"
                    say(msg)
                    self._add_to_history(user_id, "assistant", msg)
                    self.pending_confirmations[user_id] = {
                        "intent": intent,
                        "entities": {**entities, "handle": handle},
                        "awaiting": "clarification",
                    }
                    return
                await self._add_monitored_account(say, handle, category, priority)
                # Track action for context
                self._add_to_history(user_id, "assistant", f"Added @{handle} to monitor for {category}")

            elif intent == "remove_account":
                handle = entities.get("handle")
                if not handle:
                    msg = "Which account should I remove?"
                    say(msg)
                    self._add_to_history(user_id, "assistant", msg)
                    self.pending_confirmations[user_id] = {
                        "intent": intent,
                        "entities": entities,
                        "awaiting": "clarification",
                    }
                    return
                await self._remove_account(say, handle)
                self._add_to_history(user_id, "assistant", f"Removed @{handle}")

            elif intent == "list_voices":
                await self._list_voice_references(say)
                self._add_to_history(user_id, "assistant", "Listed voice references")

            elif intent == "list_monitors":
                category = entities.get("category")
                await self._list_monitored_accounts(say, category)
                self._add_to_history(user_id, "assistant", f"Listed monitors{' for ' + category if category else ''}")

            elif intent == "tag_voice":
                handle = entities.get("handle")
                pillars = entities.get("pillars", [])
                if not handle:
                    msg = "Which voice account should I update?"
                    say(msg)
                    self._add_to_history(user_id, "assistant", msg)
                    self.pending_confirmations[user_id] = {
                        "intent": intent,
                        "entities": entities,
                        "awaiting": "clarification",
                    }
                    return
                if not pillars:
                    msg = f"What pillars should @{handle} cover? Options: market_commentary, education, product, social_proof"
                    say(msg)
                    self._add_to_history(user_id, "assistant", msg)
                    self.pending_confirmations[user_id] = {
                        "intent": intent,
                        "entities": {**entities, "handle": handle},
                        "awaiting": "clarification",
                    }
                    return
                await self._tag_voice_reference(say, handle, pillars)
                self._add_to_history(user_id, "assistant", f"Updated @{handle} pillars to {', '.join(pillars)}")

            elif intent == "refresh_voices":
                await self._refresh_voice_samples(say)
                self._add_to_history(user_id, "assistant", "Refreshed voice samples")

            elif intent == "generate_post":
                pillars = entities.get("pillars", [])
                topic = entities.get("topic")
                if not pillars:
                    msg = "What type of post? Options: market_commentary, education, product, social_proof"
                    say(msg)
                    self._add_to_history(user_id, "assistant", msg)
                    self.pending_confirmations[user_id] = {
                        "intent": intent,
                        "entities": entities,
                        "awaiting": "clarification",
                    }
                    return
                pillar = pillars[0]  # Use first pillar
                await self._generate_post(say, pillar, topic)
                self._add_to_history(user_id, "assistant", f"Generated {pillar} post")

            elif intent == "help":
                self._show_help(say)
                self._add_to_history(user_id, "assistant", "Showed help")

            else:
                # Unknown intent - don't respond to avoid being noisy
                pass

        except Exception as e:
            print(f"[SLACKBOT] Error executing intent {intent}: {e}", flush=True)
            say(f"Sorry, something went wrong: {str(e)}")

    async def _add_voice_reference(self, say, handle: str, pillars: list):
        """Add a voice reference account with optional pillar tags."""
        try:
            pillar_str = ", ".join(pillars) if pillars else "all pillars"
            say(f"Adding @{handle} as voice reference for {pillar_str}...")

            # Validate pillars
            valid_pillars = ["market_commentary", "education", "product", "social_proof"]
            invalid = [p for p in pillars if p not in valid_pillars]
            if invalid:
                say(f"⚠️ Invalid pillars ignored: {', '.join(invalid)}")
                pillars = [p for p in pillars if p in valid_pillars]

            # Check if account already exists
            existing = await self.account_service.get_by_handle(handle)

            if existing:
                # Mark as voice reference with pillars
                await self.account_service.set_voice_reference(
                    existing.id, True, voice_pillars=pillars
                )
                say(f"✅ Marked existing account @{handle} as voice reference")
            else:
                # Fetch from Twitter and create
                user_info = await self.twitter.get_user_by_username(handle)
                if not user_info:
                    say(f"❌ Could not find Twitter user @{handle}")
                    return

                account = await self.account_service.create(MonitoredAccountCreate(
                    twitter_handle=handle,
                    twitter_id=user_info["id"],
                    category=AccountCategory.GLOBAL_MACRO,  # Default category
                    follower_count=user_info.get("followers_count"),
                    is_voice_reference=True,
                    voice_pillars=pillars,
                ))
                say(f"✅ Added @{handle} as voice reference ({user_info['followers_count']:,} followers)")

            # Fetch samples
            account = await self.account_service.get_by_handle(handle)
            samples = await self.voice_sampler.fetch_samples_for_account(account)
            say(f"📝 Fetched {len(samples)} sample tweets")

        except Exception as e:
            say(f"❌ Error: {str(e)}")

    async def _tag_voice_reference(self, say, handle: str, pillars: list):
        """Update pillar tags for a voice reference account."""
        try:
            # Validate pillars
            valid_pillars = ["market_commentary", "education", "product", "social_proof"]
            invalid = [p for p in pillars if p not in valid_pillars]
            if invalid:
                say(f"⚠️ Invalid pillars: {', '.join(invalid)}")
                say(f"Valid pillars: {', '.join(valid_pillars)}")
                return

            account = await self.account_service.get_by_handle(handle)
            if not account:
                say(f"❌ Account @{handle} not found")
                return

            if not account.is_voice_reference:
                say(f"❌ @{handle} is not a voice reference. Add it first with `!add-voice @{handle}`")
                return

            await self.account_service.update_voice_pillars(account.id, pillars)
            pillar_str = ", ".join(pillars) if pillars else "all pillars"
            say(f"✅ Updated @{handle} voice pillars: {pillar_str}")

        except Exception as e:
            say(f"❌ Error: {str(e)}")

    async def _add_monitored_account(self, say, handle: str, category: str, priority: int):
        """Add a monitored account."""
        try:
            # Validate category
            valid_categories = ["nigeria", "argentina", "colombia", "global_macro", "crypto_defi", "reply_target"]
            if category.lower() not in valid_categories:
                say(f"❌ Invalid category. Use: {', '.join(valid_categories)}")
                return

            say(f"Adding @{handle} to monitor...")

            # Check if exists
            existing = await self.account_service.get_by_handle(handle)
            if existing:
                say(f"⚠️ @{handle} is already being monitored")
                return

            # Fetch from Twitter
            user_info = await self.twitter.get_user_by_username(handle)
            if not user_info:
                say(f"❌ Could not find Twitter user @{handle}")
                return

            account = await self.account_service.create(MonitoredAccountCreate(
                twitter_handle=handle,
                twitter_id=user_info["id"],
                category=AccountCategory(category.lower()),
                priority=priority,
                follower_count=user_info.get("followers_count"),
            ))

            priority_label = {1: "high", 2: "medium", 3: "low"}[priority]
            say(f"✅ Now monitoring @{handle} ({category}, {priority_label} priority, {user_info['followers_count']:,} followers)")

        except Exception as e:
            say(f"❌ Error: {str(e)}")

    async def _remove_account(self, say, handle: str):
        """Remove/deactivate an account."""
        try:
            account = await self.account_service.get_by_handle(handle)
            if not account:
                say(f"❌ Account @{handle} not found")
                return

            await self.account_service.deactivate(account.id)
            say(f"✅ Removed @{handle} from monitoring")

        except Exception as e:
            say(f"❌ Error: {str(e)}")

    async def _list_voice_references(self, say):
        """List all voice reference accounts."""
        try:
            accounts = await self.account_service.get_voice_references()

            if not accounts:
                say("No voice reference accounts yet.\n\nAdd one with: `!add-voice @handle [pillars]`")
                return

            lines = ["*Voice Reference Accounts:*\n"]
            for acc in accounts:
                followers = f"{acc.follower_count:,}" if acc.follower_count else "?"
                pillars = ", ".join(acc.voice_pillars) if acc.voice_pillars else "all"
                lines.append(f"• @{acc.twitter_handle} ({followers} followers) → {pillars}")

            say("\n".join(lines))

        except Exception as e:
            say(f"❌ Error: {str(e)}")

    async def _list_monitored_accounts(self, say, category: Optional[str]):
        """List monitored accounts."""
        try:
            cat = AccountCategory(category.lower()) if category else None
            accounts = await self.account_service.get_active(category=cat)

            # Filter out voice-only accounts
            accounts = [a for a in accounts if not a.is_voice_reference or category]

            if not accounts:
                msg = f"No accounts monitored"
                if category:
                    msg += f" in {category}"
                say(msg + ".\n\nAdd one with: `!add-monitor @handle category`")
                return

            lines = ["*Monitored Accounts:*\n"]

            # Group by category
            by_category = {}
            for acc in accounts:
                cat_name = acc.category.value
                if cat_name not in by_category:
                    by_category[cat_name] = []
                by_category[cat_name].append(acc)

            for cat_name, accs in by_category.items():
                lines.append(f"\n*{cat_name.replace('_', ' ').title()}:*")
                for acc in accs[:10]:  # Limit per category
                    priority_emoji = {1: "🔴", 2: "🟡", 3: "🟢"}[acc.priority]
                    voice = " 🎤" if acc.is_voice_reference else ""
                    lines.append(f"  {priority_emoji} @{acc.twitter_handle}{voice}")
                if len(accs) > 10:
                    lines.append(f"  ... and {len(accs) - 10} more")

            say("\n".join(lines))

        except Exception as e:
            say(f"❌ Error: {str(e)}")

    async def _refresh_voice_samples(self, say):
        """Refresh voice samples from all reference accounts."""
        try:
            say("Refreshing voice samples...")
            results = await self.voice_sampler.refresh_all_samples()

            if not results:
                say("No voice reference accounts to refresh")
                return

            lines = ["*Voice Samples Refreshed:*\n"]
            total = 0
            for handle, count in results.items():
                lines.append(f"• @{handle}: {count} new samples")
                total += count

            lines.append(f"\n*Total:* {total} new samples")
            say("\n".join(lines))

        except Exception as e:
            say(f"❌ Error: {str(e)}")

    async def _generate_post(self, say, pillar: str, topic: str = None, user_id: str = None):
        """Generate a post for a given pillar."""
        try:
            # Validate pillar
            valid_pillars = ["market_commentary", "education", "product", "social_proof"]
            if pillar not in valid_pillars:
                say(f"❌ Invalid pillar. Use: {', '.join(valid_pillars)}")
                return

            say(f"✨ Generating {pillar.replace('_', ' ')} post...")

            # Generate the post
            content_pillar = ContentPillar(pillar)
            result = await self.generator.generate_single_post(
                pillar=content_pillar,
                topic_hint=topic,
            )

            content = result.get("content", "No content generated")
            topic_result = result.get("topic", "N/A")

            # Format and send the result
            blocks = [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"📝 Generated {pillar.replace('_', ' ').title()} Post"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Topic:* {topic_result}"}
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"```{content}```"}
                },
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": "💬 _Reply in thread to refine, react ✅ when done_"}]
                },
            ]

            response = say(blocks=blocks, text=f"Generated post: {topic_result}")

            # Create draft session for iterative refinement
            if response and response.get("ts"):
                thread_ts = response["ts"]
                self.draft_sessions[thread_ts] = {
                    "pillar": pillar,
                    "topic": topic_result,
                    "user_id": user_id,
                    "drafts": [
                        {
                            "version": 0,
                            "content": content,
                            "revision_request": None,
                            "message_ts": thread_ts,
                        }
                    ],
                    "status": "iterating",
                    "created_at": datetime.now(timezone.utc),
                }

                # Cleanup old sessions
                await self._cleanup_old_sessions()

        except Exception as e:
            say(f"❌ Error generating post: {str(e)}")

    async def _store_feedback(self, say, thread_ts: str, feedback_text: str):
        """Store feedback from a thread reply."""
        try:
            post_info = self.generated_posts.get(thread_ts)
            if not post_info:
                return

            pillar = ContentPillar(post_info["pillar"])
            original_content = post_info["content"]

            await self.feedback_service.create(
                pillar=pillar,
                original_content=original_content,
                feedback_text=feedback_text,
                slack_thread_ts=thread_ts,
            )

            # Reply in thread to confirm
            say(
                text="✅ Feedback recorded! This will be used to improve future content generation.",
                thread_ts=thread_ts,
            )

        except Exception as e:
            print(f"[SLACKBOT] Error storing feedback: {e}", flush=True)

    async def _check_suggested_tweet_thread(self, thread_ts: str) -> bool:
        """Check if thread_ts is a suggested tweet and create draft session if so."""
        try:
            tweet = await self.tweet_service.get_by_slack_message_ts(thread_ts)
            if not tweet or not tweet.suggested_content:
                return False

            # Determine pillar based on relevance type
            pillar = "market_commentary"  # Default
            if tweet.relevance_type:
                if tweet.relevance_type.value == "reply_opportunity":
                    pillar = "social_proof"  # Replies are social proof

            # Create draft session on-the-fly
            self.draft_sessions[thread_ts] = {
                "pillar": pillar,
                "topic": f"Reply to @{tweet.account_handle}",
                "source_tweet_id": str(tweet.id),
                "source_tweet_content": tweet.content,
                "source_tweet_handle": tweet.account_handle,
                "drafts": [
                    {
                        "version": 0,
                        "content": tweet.suggested_content,
                        "revision_request": None,
                        "message_ts": thread_ts,
                    }
                ],
                "status": "iterating",
                "created_at": datetime.now(timezone.utc),
            }
            return True

        except Exception as e:
            print(f"[SLACKBOT] Error checking suggested tweet: {e}", flush=True)
            return False

    async def _handle_draft_reply(self, say, thread_ts: str, text: str, user_id: str):
        """Handle replies in a draft session thread."""
        session = self.draft_sessions.get(thread_ts)
        if not session:
            return

        try:
            # Route based on session status
            if session["status"] == "iterating":
                # Quick check for obvious approval signals first
                if self._is_approval_signal(text):
                    await self._handle_approval(say, thread_ts)
                    return

                # Classify intent using Claude for more nuanced understanding
                intent = await self._classify_draft_reply_intent(text, session)

                if intent == "approval":
                    await self._handle_approval(say, thread_ts)
                elif intent == "question":
                    await self._handle_context_question(say, thread_ts, text, session)
                else:  # "revision"
                    await self._handle_revision_request(say, thread_ts, text)

            elif session["status"] == "learnings_pending":
                await self._handle_learning_confirmation(say, thread_ts, text)

        except Exception as e:
            print(f"[SLACKBOT] Error handling draft reply: {e}", flush=True)

    async def _classify_draft_reply_intent(self, text: str, session: dict) -> str:
        """Classify the intent of a draft thread reply using Claude."""
        import anthropic

        try:
            client = anthropic.Anthropic()

            prompt = f"""Classify this message in a content drafting thread. The user is reviewing a suggested social media post.

Message: "{text}"

Context: This is a reply to a suggested {'tweet reply' if session.get('source_tweet_content') else 'post'}.

Classify as exactly one of:
- "approval" - User is approving/accepting the draft (e.g., "looks good", "perfect", "use this")
- "question" - User is asking for information/clarification about the source content, context, or what something means (e.g., "what is this about?", "who is this person?", "can you explain the context?")
- "revision" - User wants to change/edit the draft, INCLUDING voice/style requests (e.g., "make it shorter", "add more detail", "change the tone", "how would X write this", "write it like X", "in X's voice/style")

IMPORTANT: Requests about writing style or voice (e.g., "how would X write this?", "what would X say?", "make it sound like X") are REVISION requests, not questions.

Return ONLY one word: approval, question, or revision"""

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}],
            )

            intent = response.content[0].text.strip().lower()
            if intent in ["approval", "question", "revision"]:
                return intent
            return "revision"  # Default to revision if unclear

        except Exception as e:
            print(f"[SLACKBOT] Error classifying intent: {e}", flush=True)
            return "revision"  # Default to revision on error

    async def _handle_context_question(self, say, thread_ts: str, question: str, session: dict):
        """Answer a question about the source content/context."""
        import anthropic

        try:
            # Build context about what we're replying to
            context_parts = []

            if session.get("source_tweet_content"):
                handle = session.get("source_tweet_handle", "unknown")
                context_parts.append(f"Source tweet from @{handle}:\n\"{session['source_tweet_content']}\"")

            if session.get("topic"):
                context_parts.append(f"Topic: {session['topic']}")

            current_draft = session["drafts"][-1]["content"]
            context_parts.append(f"Current draft:\n\"{current_draft}\"")

            context = "\n\n".join(context_parts)

            client = anthropic.Anthropic()

            prompt = f"""The user is drafting a social media response and has a question. Answer their question based on the context provided.

{context}

User's question: {question}

Provide a helpful, concise answer. If you don't have enough information to answer, say so."""

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )

            answer = response.content[0].text.strip()

            say(
                text=f"{answer}\n\n_Reply with revision requests or ✅ when ready to finalize._",
                thread_ts=thread_ts,
            )

        except Exception as e:
            print(f"[SLACKBOT] Error answering question: {e}", flush=True)
            say(
                text="Sorry, I couldn't process that question. Try rephrasing or continue with revision requests.",
                thread_ts=thread_ts,
            )

    async def _detect_voice_request(self, text: str) -> Optional[str]:
        """Detect if revision request is asking for voice matching, return voice hint."""
        import anthropic

        try:
            client = anthropic.Anthropic()

            prompt = f"""Analyze this revision request for a social media post.

Request: "{text}"

Is the user asking to rewrite in someone's voice/style? Look for phrases like:
- "sound like X", "write like X", "in X's style"
- "more like X", "make it like X"
- "use X's voice", "match X's tone"
- References to specific accounts or people

If YES, extract who they're referring to (the voice/style reference).
If NO, they just want a regular revision.

Return ONLY valid JSON:
{{"is_voice_request": true/false, "voice_hint": "extracted name/handle or null"}}

Examples:
- "make it shorter" -> {{"is_voice_request": false, "voice_hint": null}}
- "sound more like kobeissi" -> {{"is_voice_request": true, "voice_hint": "kobeissi"}}
- "write this in the style of @KobeissiLetter" -> {{"is_voice_request": true, "voice_hint": "KobeissiLetter"}}
- "more punchy like that market guy" -> {{"is_voice_request": true, "voice_hint": "market guy"}}"""

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text.strip()

            # Handle markdown code blocks
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            import json
            result = json.loads(response_text)

            if result.get("is_voice_request") and result.get("voice_hint"):
                return result["voice_hint"]
            return None

        except Exception as e:
            print(f"[SLACKBOT] Error detecting voice request: {e}", flush=True)
            return None

    async def _find_voice_reference(self, hint: str) -> Optional[dict]:
        """Fuzzy search for a voice reference by hint. Returns account and samples."""
        try:
            # Get all voice references
            voice_accounts = await self.account_service.get_voice_references()

            if not voice_accounts:
                return None

            hint_lower = hint.lower().strip().lstrip("@")

            # Try exact handle match first
            for acc in voice_accounts:
                if acc.twitter_handle.lower() == hint_lower:
                    samples = await self.voice_sampler.get_samples_for_account(acc.id)
                    return {"account": acc, "samples": samples}

            # Try partial handle match
            for acc in voice_accounts:
                if hint_lower in acc.twitter_handle.lower():
                    samples = await self.voice_sampler.get_samples_for_account(acc.id)
                    return {"account": acc, "samples": samples}

            # Try matching by pillar keywords
            pillar_keywords = {
                "market": "market_commentary",
                "commentary": "market_commentary",
                "education": "education",
                "educational": "education",
                "product": "product",
                "social": "social_proof",
                "proof": "social_proof",
            }

            for keyword, pillar in pillar_keywords.items():
                if keyword in hint_lower:
                    for acc in voice_accounts:
                        if acc.voice_pillars and pillar in acc.voice_pillars:
                            samples = await self.voice_sampler.get_samples_for_account(acc.id)
                            return {"account": acc, "samples": samples}

            # If still no match, use Claude to find best match
            account_list = ", ".join([f"@{a.twitter_handle}" for a in voice_accounts])
            import anthropic
            client = anthropic.Anthropic()

            prompt = f"""The user wants to match a voice style. They said: "{hint}"

Available voice reference accounts: {account_list}

Which account best matches what they're looking for? Return ONLY the handle (without @), or "none" if no good match."""

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}],
            )

            matched_handle = response.content[0].text.strip().lower().lstrip("@")

            for acc in voice_accounts:
                if acc.twitter_handle.lower() == matched_handle:
                    samples = await self.voice_sampler.get_samples_for_account(acc.id)
                    return {"account": acc, "samples": samples}

            return None

        except Exception as e:
            print(f"[SLACKBOT] Error finding voice reference: {e}", flush=True)
            return None

    def _is_approval_signal(self, text: str) -> bool:
        """Check if message signals approval."""
        text_lower = text.lower().strip()

        # Exact matches for short phrases (avoid false positives)
        exact_matches = ["good", "nice", "yes", "yep", "ok", "okay", "👍", "✅"]
        if text_lower in exact_matches:
            return True

        # Phrase matches (can be part of longer text)
        approval_phrases = [
            "this is good", "that's good", "thats good", "looks good", "is good",
            "perfect", "done", "approved", "use this", "use it",
            "that works", "this works", "love it", "love this",
            "great", "finalize", "lock it", "ship it", "good to go",
            "lgtm", "let's go", "lets go", "all good", "we're good",
        ]
        return any(phrase in text_lower for phrase in approval_phrases)

    async def _handle_revision_request(self, say, thread_ts: str, request: str):
        """Handle a revision request in a draft thread."""
        session = self.draft_sessions.get(thread_ts)
        if not session:
            return

        try:
            # Check if this is a voice matching request
            voice_hint = await self._detect_voice_request(request)

            if voice_hint:
                # Find the voice reference
                voice_match = await self._find_voice_reference(voice_hint)

                if voice_match:
                    account = voice_match["account"]
                    samples = voice_match["samples"]

                    # Get sample content texts
                    sample_texts = [s.content for s in samples] if samples else []

                    if sample_texts:
                        current_content = session["drafts"][-1]["content"]

                        # Revise with voice
                        revised_content = await self.generator.revise_with_voice(
                            pillar=ContentPillar(session["pillar"]),
                            current_content=current_content,
                            voice_samples=sample_texts,
                            voice_handle=account.twitter_handle,
                        )

                        version = len(session["drafts"])

                        # Post the revision with voice attribution
                        response = say(
                            text=f"📝 *Revision {version}* (styled like @{account.twitter_handle})\n```{revised_content}```\n\n_Reply to refine more, react ✅ when done_",
                            thread_ts=thread_ts,
                        )

                        # Store new draft
                        session["drafts"].append({
                            "version": version,
                            "content": revised_content,
                            "revision_request": request,
                            "voice_reference": account.twitter_handle,
                            "message_ts": response.get("ts") if response else None,
                        })
                        return
                    else:
                        say(
                            text=f"Found @{account.twitter_handle} but no voice samples yet. Try `!refresh-voice` first.",
                            thread_ts=thread_ts,
                        )
                        return
                else:
                    say(
                        text=f"Couldn't find a voice reference matching \"{voice_hint}\". Use `!list-voice` to see available voices.",
                        thread_ts=thread_ts,
                    )
                    return

            # Regular revision (not voice matching)
            messages = self._build_revision_messages(session, request)

            # Get revision from Claude
            revised_content = await self.generator.revise_content(
                pillar=ContentPillar(session["pillar"]),
                messages=messages,
            )

            version = len(session["drafts"])

            # Post the revision
            response = say(
                text=f"📝 *Revision {version}*\n```{revised_content}```\n\n_Reply to refine more, react ✅ when done_",
                thread_ts=thread_ts,
            )

            # Store new draft
            session["drafts"].append({
                "version": version,
                "content": revised_content,
                "revision_request": request,
                "message_ts": response.get("ts") if response else None,
            })

        except Exception as e:
            print(f"[SLACKBOT] Error handling revision: {e}", flush=True)
            say(
                text=f"Sorry, I couldn't generate a revision: {str(e)}",
                thread_ts=thread_ts,
            )

    def _build_revision_messages(self, session: dict, new_request: str) -> List[Dict]:
        """Build conversation history for revision request."""
        messages = []

        # If this is a reply to a tweet, include context about the original tweet
        if session.get("source_tweet_content"):
            handle = session.get("source_tweet_handle", "unknown")
            messages.append({
                "role": "user",
                "content": f"I'm writing a reply to this tweet from @{handle}:\n\n\"{session['source_tweet_content']}\"\n\nPlease help me refine my reply."
            })

        # Add original draft
        drafts = session.get("drafts", [])
        if drafts:
            messages.append({
                "role": "assistant",
                "content": f"Here's the original draft:\n\n{drafts[0]['content']}"
            })

        # Add revision history
        for draft in drafts[1:]:
            if draft.get("revision_request"):
                messages.append({
                    "role": "user",
                    "content": draft["revision_request"]
                })
            messages.append({
                "role": "assistant",
                "content": draft["content"]
            })

        # Add new request
        messages.append({
            "role": "user",
            "content": new_request
        })

        return messages

    async def _handle_approval(self, say, thread_ts: str, channel: str = None):
        """Handle when user approves a draft."""
        session = self.draft_sessions.get(thread_ts)
        if not session or session["status"] != "iterating":
            return

        session["status"] = "approved"
        session["approved_at"] = datetime.now(timezone.utc)

        # Only extract learnings if there were revisions
        if len(session["drafts"]) > 1:
            try:
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
                        text=f"✅ Final version locked!\n\nBased on your edits, I noticed these preferences:\n{learnings_text}\n\nShould I remember these for future {pillar_name} posts?\nReply: *yes* / *yes, except [x]* / *no*",
                        thread_ts=thread_ts,
                    )
                    return
            except Exception as e:
                print(f"[SLACKBOT] Error extracting learnings: {e}", flush=True)

        # No learnings to extract
        say(text="✅ Final version locked!", thread_ts=thread_ts)
        session["status"] = "complete"

    async def _handle_learning_confirmation(self, say, thread_ts: str, response: str):
        """Handle user's response to learning confirmation."""
        session = self.draft_sessions.get(thread_ts)
        if not session or session["status"] != "learnings_pending":
            return

        response_lower = response.lower().strip()
        learnings = session.get("pending_learnings", [])

        if response_lower == "no" or response_lower.startswith("no"):
            say(text="👍 No problem, preferences not saved.", thread_ts=thread_ts)
            session["status"] = "complete"
            return

        # Handle "yes, except X"
        if "except" in response_lower and learnings:
            # Filter out mentioned exceptions
            filtered = []
            for learning in learnings:
                learning_lower = learning.lower()
                # Check if this learning is mentioned in the exception
                if not any(word in response_lower for word in learning_lower.split()[:3]):
                    filtered.append(learning)
            learnings = filtered

        # Store learnings as feedback (one record with all learnings)
        if learnings:
            pillar = ContentPillar(session["pillar"])
            original_content = session["drafts"][0]["content"]
            final_content = session["drafts"][-1]["content"]

            try:
                await self.feedback_service.create(
                    pillar=pillar,
                    original_content=original_content,
                    final_content=final_content,
                    learnings=learnings,
                    slack_thread_ts=thread_ts,
                )

                pillar_name = session["pillar"].replace("_", " ")
                saved_text = "\n".join(f"• {l}" for l in learnings)
                say(
                    text=f"📚 Got it! I'll remember for future {pillar_name} posts:\n{saved_text}",
                    thread_ts=thread_ts,
                )
            except Exception as e:
                print(f"[SLACKBOT] Error storing learnings: {e}", flush=True)
                say(text="⚠️ Couldn't save preferences, but your content is ready!", thread_ts=thread_ts)
        else:
            say(text="👍 No preferences saved.", thread_ts=thread_ts)

        session["status"] = "complete"

    async def _cleanup_old_sessions(self):
        """Remove draft sessions older than 24 hours."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        expired = [
            ts for ts, session in self.draft_sessions.items()
            if session.get("created_at", datetime.now(timezone.utc)) < cutoff
        ]
        for ts in expired:
            del self.draft_sessions[ts]

    def _show_help(self, say):
        """Show help message."""
        help_text = """*Content Agent*

You can talk to me naturally or use commands!

*Natural Language Examples:*
• "generate a market commentary post about the naira"
• "add kobeissi as a voice for market commentary"
• "what voices do we have?"
• "show me the nigeria monitors"
• "refresh the voice samples"

*Commands* (for power users):

*Content Generation:*
• `!generate pillar [topic]` — Generate a post for a pillar

*Voice References* (accounts to mimic style):
• `!add-voice @handle [pillars]` — Add voice reference
• `!tag-voice @handle pillars` — Update pillars for existing voice
• `!list-voice` — List voice references
• `!refresh-voice` — Refresh voice samples

*Monitored Accounts* (accounts to watch for news):
• `!add-monitor @handle category [priority]` — Add account
• `!list-monitors [category]` — List monitored accounts
• `!remove @handle` — Remove account

*Pillars:* market_commentary, education, product, social_proof
*Categories:* nigeria, argentina, colombia, global_macro, crypto_defi, reply_target
*Priority:* 1 (high), 2 (medium), 3 (low)

*Command Examples:*
```
!generate market_commentary
!generate education how perpetuals work
!add-voice @KobeissiLetter market_commentary
!add-voice @productaccount product, education
!tag-voice @KobeissiLetter market_commentary, social_proof
!add-monitor @cenbank_ng nigeria 1
!list-monitors nigeria
!remove @noisyaccount
```"""
        say(help_text)

    def start(self):
        """Start the Slack bot."""
        handler = SocketModeHandler(self.app, self.app_token)
        print("Starting Slack bot via Socket Mode...", flush=True)
        handler.start()


def run_slack_bot():
    """Run the Slack bot."""
    try:
        print("[SLACKBOT] Initializing Slack bot...", flush=True)
        bot = SlackBot()
        print("[SLACKBOT] Bot initialized, starting Socket Mode...", flush=True)
        bot.start()
    except Exception as e:
        print(f"[SLACKBOT] ERROR: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print("[SLACKBOT] Running as main module", flush=True)
    run_slack_bot()

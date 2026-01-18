"""Slack bot for handling commands via messages."""

import re
import asyncio
from typing import Optional

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.config import get_settings
from src.services.account_service import AccountService
from src.services.voice_sampler import get_voice_sampler
from src.models.content import MonitoredAccountCreate, AccountCategory
from src.integrations.twitter import get_twitter_client


class SlackBot:
    """Slack bot that handles commands via messages."""

    def __init__(self):
        settings = get_settings()
        self.app = App(token=settings.slack_bot_token)
        self.app_token = settings.slack_app_token
        self.account_service = AccountService()
        self.voice_sampler = get_voice_sampler()
        self.twitter = get_twitter_client()

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

        @self.app.message(re.compile(r"^!help", re.IGNORECASE))
        def handle_help(message, say):
            """Handle !help"""
            self._show_help(say)

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

    def _show_help(self, say):
        """Show help message."""
        help_text = """*Content Agent Commands:*

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

*Examples:*
```
!add-voice @KobeissiLetter market_commentary
!add-voice @productaccount product, education
!tag-voice @KobeissiLetter market_commentary, social_proof
!add-monitor @cenbank_ng nigeria 1
!list-monitors nigeria
```"""
        say(help_text)

    def start(self):
        """Start the Slack bot."""
        handler = SocketModeHandler(self.app, self.app_token)
        print("Starting Slack bot via Socket Mode...", flush=True)
        handler.start()


def run_slack_bot():
    """Run the Slack bot."""
    print("Initializing Slack bot...", flush=True)
    bot = SlackBot()
    print("Slack bot initialized, starting Socket Mode...", flush=True)
    bot.start()

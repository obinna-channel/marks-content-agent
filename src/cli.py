"""CLI commands for the Content Agent."""

import asyncio
from datetime import datetime, timedelta

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()


def run_async(coro):
    """Helper to run async functions in sync CLI context."""
    return asyncio.get_event_loop().run_until_complete(coro)


@click.group()
def cli():
    """Content Agent CLI for Marks Exchange."""
    pass


# =============================================================================
# CONTENT GENERATION COMMANDS
# =============================================================================

@cli.command()
@click.option("--news", default="", help="Recent news headlines for context")
@click.option("--dry-run", is_flag=True, help="Generate but don't save to DB or send to Slack")
def generate_batch(news: str, dry_run: bool):
    """Generate weekly content batch and send to Slack."""
    from src.agent.generator import get_content_generator
    from src.integrations.slack import get_slack_client

    console.print("[bold blue]Generating weekly content batch...[/bold blue]")

    async def _generate():
        generator = get_content_generator()
        batch = await generator.generate_weekly_batch(recent_news=news)
        return batch

    try:
        batch = run_async(_generate())

        # Display generated content
        console.print(f"\n[green]Generated {len(batch.items)} posts for {batch.week_start.strftime('%b %d')} - {batch.week_end.strftime('%b %d')}[/green]\n")

        for item in batch.items:
            panel = Panel(
                item.content,
                title=f"[bold]{item.day.title()}[/bold] - {item.pillar.value.replace('_', ' ').title()}",
                subtitle=item.topic,
            )
            console.print(panel)
            console.print()

        if not dry_run:
            # Send to Slack
            async def _send_slack():
                slack = get_slack_client()
                await slack.send_weekly_batch(batch)

            console.print("[yellow]Sending to Slack...[/yellow]")
            run_async(_send_slack())
            console.print("[green]Sent to Slack successfully![/green]")
        else:
            console.print("[yellow]Dry run - not sent to Slack[/yellow]")

    except Exception as e:
        console.print(f"[red]Error generating batch: {e}[/red]")
        raise click.Abort()


@cli.command()
@click.argument("pillar", type=click.Choice(["market_commentary", "education", "product", "social_proof"]))
@click.option("--topic", default=None, help="Topic hint for generation")
def generate_single(pillar: str, topic: str):
    """Generate a single post for a specific pillar."""
    from src.agent.generator import get_content_generator
    from src.models.content import ContentPillar

    console.print(f"[bold blue]Generating {pillar} post...[/bold blue]")

    async def _generate():
        generator = get_content_generator()
        return await generator.generate_single_post(
            pillar=ContentPillar(pillar),
            topic_hint=topic,
        )

    try:
        result = run_async(_generate())

        panel = Panel(
            result["content"],
            title=f"[bold]{pillar.replace('_', ' ').title()}[/bold]",
            subtitle=result["topic"],
        )
        console.print(panel)

    except Exception as e:
        console.print(f"[red]Error generating post: {e}[/red]")
        raise click.Abort()


# =============================================================================
# MONITORING COMMANDS
# =============================================================================

@cli.command()
@click.option("--all", "check_all", is_flag=True, help="Check all accounts regardless of schedule")
def check_twitter(check_all: bool):
    """Check Twitter accounts for new tweets."""
    from src.monitors.twitter_monitor import TwitterMonitor
    from src.agent.relevance import get_relevance_scorer

    console.print("[bold blue]Checking Twitter accounts...[/bold blue]")

    async def _check():
        monitor = TwitterMonitor()
        scorer = get_relevance_scorer()
        return await monitor.run_check_cycle(scorer)

    try:
        summary = run_async(_check())

        table = Table(title="Twitter Check Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Accounts checked", str(summary["accounts_checked"]))
        table.add_row("Tweets found", str(summary["tweets_found"]))
        table.add_row("Relevant tweets", str(summary["tweets_relevant"]))
        table.add_row("Notifications sent", str(summary["notifications_sent"]))

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error checking Twitter: {e}[/red]")
        raise click.Abort()


@cli.command()
@click.option("--all", "check_all", is_flag=True, help="Check all feeds regardless of schedule")
def check_rss(check_all: bool):
    """Check RSS feeds for new articles."""
    from src.monitors.rss_monitor import get_rss_monitor

    console.print("[bold blue]Checking RSS feeds...[/bold blue]")

    async def _check():
        monitor = get_rss_monitor()
        if check_all:
            items = await monitor.check_all_sources()
            # Process items
            relevant = 0
            for item_data in items:
                if await monitor.process_item(item_data):
                    relevant += 1
            return {
                "sources_checked": len(await monitor.rss_service.get_active_sources()),
                "items_found": len(items),
                "items_relevant": relevant,
                "notifications_sent": relevant,
            }
        else:
            return await monitor.run_check_cycle()

    try:
        summary = run_async(_check())

        table = Table(title="RSS Check Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Sources checked", str(summary["sources_checked"]))
        table.add_row("Items found", str(summary["items_found"]))
        table.add_row("Relevant items", str(summary["items_relevant"]))
        table.add_row("Notifications sent", str(summary["notifications_sent"]))

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error checking RSS: {e}[/red]")
        raise click.Abort()


# =============================================================================
# HISTORY COMMANDS
# =============================================================================

@cli.command()
@click.option("--days", default=30, help="Number of days to look back")
@click.option("--type", "content_type", default=None, help="Filter by content type")
def history(days: int, content_type: str):
    """View content history."""
    from src.services.history_service import HistoryService
    from src.models.content import ContentType

    console.print(f"[bold blue]Content history (last {days} days)...[/bold blue]")

    async def _get_history():
        service = HistoryService()
        ct = ContentType(content_type) if content_type else None
        return await service.get_recent(days=days, content_type=ct)

    try:
        items = run_async(_get_history())

        if not items:
            console.print("[yellow]No content found in this period[/yellow]")
            return

        table = Table(title=f"Content History ({len(items)} items)")
        table.add_column("Date", style="cyan", width=12)
        table.add_column("Type", style="magenta", width=15)
        table.add_column("Pillar", style="blue", width=18)
        table.add_column("Topic", style="green")
        table.add_column("Posted", style="yellow", width=8)

        for item in items[:20]:  # Limit display
            posted = "Yes" if item.posted_at else "No"
            pillar = item.pillar.value.replace("_", " ").title() if item.pillar else "-"
            table.add_row(
                item.created_at.strftime("%Y-%m-%d"),
                item.type.value,
                pillar,
                (item.topic or "-")[:30],
                posted,
            )

        console.print(table)

        if len(items) > 20:
            console.print(f"[dim]Showing 20 of {len(items)} items[/dim]")

    except Exception as e:
        console.print(f"[red]Error fetching history: {e}[/red]")
        raise click.Abort()


@cli.command()
def variety_check():
    """Check content variety health."""
    from src.agent.variety import get_variety_manager

    console.print("[bold blue]Checking content variety...[/bold blue]")

    async def _check():
        manager = get_variety_manager()
        return await manager.check_variety_health()

    try:
        health = run_async(_check())

        table = Table(title="Variety Health Check")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total posts (30d)", str(health["total_posts"]))
        table.add_row("Unique topics", str(health["unique_topics"]))
        table.add_row("Unique angles", str(health["unique_angles"]))
        table.add_row("Health status", health["health"])

        console.print(table)

        # Pillar distribution
        if health["pillar_distribution"]:
            dist_table = Table(title="Pillar Distribution")
            dist_table.add_column("Pillar", style="cyan")
            dist_table.add_column("Count", style="green")

            for pillar, count in health["pillar_distribution"].items():
                dist_table.add_row(pillar.replace("_", " ").title(), str(count))

            console.print(dist_table)

        # Warnings
        if health["warnings"]:
            console.print("\n[bold yellow]Warnings:[/bold yellow]")
            for warning in health["warnings"]:
                console.print(f"  - {warning}")

    except Exception as e:
        console.print(f"[red]Error checking variety: {e}[/red]")
        raise click.Abort()


# =============================================================================
# ACCOUNT MANAGEMENT COMMANDS
# =============================================================================

@cli.command()
@click.option("--category", default=None, help="Filter by category")
def list_accounts(category: str):
    """List monitored Twitter accounts."""
    from src.services.account_service import AccountService
    from src.models.content import AccountCategory

    console.print("[bold blue]Monitored accounts...[/bold blue]")

    async def _list():
        service = AccountService()
        cat = AccountCategory(category) if category else None
        return await service.get_active(category=cat)

    try:
        accounts = run_async(_list())

        if not accounts:
            console.print("[yellow]No accounts found[/yellow]")
            return

        table = Table(title=f"Monitored Accounts ({len(accounts)})")
        table.add_column("Handle", style="cyan")
        table.add_column("Category", style="magenta")
        table.add_column("Priority", style="yellow")
        table.add_column("Followers", style="green")
        table.add_column("Last Checked", style="dim")

        for acc in accounts:
            last_checked = acc.last_checked_at.strftime("%Y-%m-%d %H:%M") if acc.last_checked_at else "Never"
            followers = f"{acc.follower_count:,}" if acc.follower_count else "-"
            table.add_row(
                f"@{acc.twitter_handle}",
                acc.category.value.replace("_", " ").title(),
                str(acc.priority),
                followers,
                last_checked,
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error listing accounts: {e}[/red]")
        raise click.Abort()


@cli.command()
@click.argument("handle")
@click.argument("category", type=click.Choice(["nigeria", "argentina", "global_macro", "crypto_defi", "reply_target"]))
@click.option("--priority", default=2, type=int, help="Priority level (1=high, 2=medium, 3=low)")
def add_account(handle: str, category: str, priority: int):
    """Add a Twitter account to monitor."""
    from src.services.account_service import AccountService
    from src.models.content import MonitoredAccountCreate, AccountCategory
    from src.integrations.twitter import get_twitter_client

    handle = handle.lstrip("@")
    console.print(f"[bold blue]Adding @{handle}...[/bold blue]")

    async def _add():
        # Fetch user info from Twitter
        twitter = get_twitter_client()
        user_info = await twitter.get_user_by_username(handle)

        if not user_info:
            raise ValueError(f"Could not find Twitter user @{handle}")

        service = AccountService()
        account = MonitoredAccountCreate(
            twitter_handle=handle,
            twitter_id=user_info["id"],
            category=AccountCategory(category),
            priority=priority,
            follower_count=user_info.get("followers_count"),
        )
        return await service.create(account)

    try:
        account = run_async(_add())
        console.print(f"[green]Added @{account.twitter_handle} ({account.category.value})[/green]")

    except Exception as e:
        console.print(f"[red]Error adding account: {e}[/red]")
        raise click.Abort()


# =============================================================================
# RSS SOURCE COMMANDS
# =============================================================================

@cli.command()
def list_rss():
    """List RSS sources."""
    from src.services.rss_service import RSSService

    console.print("[bold blue]RSS sources...[/bold blue]")

    async def _list():
        service = RSSService()
        return await service.get_active_sources()

    try:
        sources = run_async(_list())

        if not sources:
            console.print("[yellow]No RSS sources found[/yellow]")
            return

        table = Table(title=f"RSS Sources ({len(sources)})")
        table.add_column("Name", style="cyan")
        table.add_column("Category", style="magenta")
        table.add_column("Interval", style="yellow")
        table.add_column("Last Checked", style="dim")

        for src in sources:
            last_checked = src.last_checked_at.strftime("%Y-%m-%d %H:%M") if src.last_checked_at else "Never"
            table.add_row(
                src.name,
                src.category.value.replace("_", " ").title(),
                f"{src.poll_interval_minutes}m",
                last_checked,
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error listing RSS sources: {e}[/red]")
        raise click.Abort()


@cli.command()
@click.argument("name")
@click.argument("url")
@click.argument("category", type=click.Choice(["nigeria", "argentina", "global_macro", "crypto_defi"]))
@click.option("--interval", default=15, help="Poll interval in minutes")
@click.option("--keywords", default=None, help="Comma-separated filter keywords")
def add_rss(name: str, url: str, category: str, interval: int, keywords: str):
    """Add an RSS source to monitor."""
    from src.services.rss_service import RSSService
    from src.models.content import RSSSourceCreate, AccountCategory

    console.print(f"[bold blue]Adding RSS source: {name}...[/bold blue]")

    async def _add():
        service = RSSService()
        kw_list = [k.strip() for k in keywords.split(",")] if keywords else None

        source = RSSSourceCreate(
            name=name,
            url=url,
            category=AccountCategory(category),
            poll_interval_minutes=interval,
            keywords=kw_list,
        )
        return await service.create_source(source)

    try:
        source = run_async(_add())
        console.print(f"[green]Added RSS source: {source.name}[/green]")

    except Exception as e:
        console.print(f"[red]Error adding RSS source: {e}[/red]")
        raise click.Abort()


# =============================================================================
# VOICE REFERENCE COMMANDS
# =============================================================================

@cli.command()
def list_voice_references():
    """List voice reference accounts."""
    from src.services.account_service import AccountService

    console.print("[bold blue]Voice reference accounts...[/bold blue]")

    async def _list():
        service = AccountService()
        return await service.get_voice_references()

    try:
        accounts = run_async(_list())

        if not accounts:
            console.print("[yellow]No voice reference accounts found[/yellow]")
            console.print("[dim]Add one with: content-agent add-voice-reference @handle[/dim]")
            return

        table = Table(title=f"Voice Reference Accounts ({len(accounts)})")
        table.add_column("Handle", style="cyan")
        table.add_column("Followers", style="green")
        table.add_column("Category", style="magenta")

        for acc in accounts:
            followers = f"{acc.follower_count:,}" if acc.follower_count else "-"
            table.add_row(
                f"@{acc.twitter_handle}",
                followers,
                acc.category.value.replace("_", " ").title(),
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error listing voice references: {e}[/red]")
        raise click.Abort()


@cli.command()
@click.argument("handle")
@click.option("--category", default="global_macro", type=click.Choice(["nigeria", "argentina", "global_macro", "crypto_defi", "reply_target"]))
def add_voice_reference(handle: str, category: str):
    """Add a Twitter account as a voice reference (to mimic their style)."""
    from src.services.account_service import AccountService
    from src.services.voice_sampler import get_voice_sampler
    from src.models.content import MonitoredAccountCreate, AccountCategory
    from src.integrations.twitter import get_twitter_client

    handle = handle.lstrip("@")
    console.print(f"[bold blue]Adding @{handle} as voice reference...[/bold blue]")

    async def _add():
        service = AccountService()
        twitter = get_twitter_client()
        sampler = get_voice_sampler()

        # Check if account already exists
        existing = await service.get_by_handle(handle)
        if existing:
            # Just mark as voice reference
            account = await service.set_voice_reference(existing.id, True)
            console.print(f"[green]Marked existing account @{handle} as voice reference[/green]")
        else:
            # Fetch user info and create
            user_info = await twitter.get_user_by_username(handle)
            if not user_info:
                raise ValueError(f"Could not find Twitter user @{handle}")

            account = await service.create(MonitoredAccountCreate(
                twitter_handle=handle,
                twitter_id=user_info["id"],
                category=AccountCategory(category),
                follower_count=user_info.get("followers_count"),
                is_voice_reference=True,
            ))
            console.print(f"[green]Added @{handle} as voice reference[/green]")

        # Fetch initial samples
        console.print("[yellow]Fetching sample tweets...[/yellow]")
        samples = await sampler.fetch_samples_for_account(account)
        console.print(f"[green]Fetched {len(samples)} sample tweets[/green]")

        return account

    try:
        run_async(_add())

    except Exception as e:
        console.print(f"[red]Error adding voice reference: {e}[/red]")
        raise click.Abort()


@cli.command()
@click.argument("handle")
def remove_voice_reference(handle: str):
    """Remove a Twitter account as a voice reference."""
    from src.services.account_service import AccountService

    handle = handle.lstrip("@")
    console.print(f"[bold blue]Removing @{handle} as voice reference...[/bold blue]")

    async def _remove():
        service = AccountService()
        account = await service.get_by_handle(handle)
        if not account:
            raise ValueError(f"Account @{handle} not found")

        return await service.set_voice_reference(account.id, False)

    try:
        run_async(_remove())
        console.print(f"[green]Removed @{handle} as voice reference[/green]")

    except Exception as e:
        console.print(f"[red]Error removing voice reference: {e}[/red]")
        raise click.Abort()


@cli.command()
def refresh_voice_samples():
    """Refresh voice samples from all reference accounts."""
    from src.services.voice_sampler import get_voice_sampler

    console.print("[bold blue]Refreshing voice samples...[/bold blue]")

    async def _refresh():
        sampler = get_voice_sampler()
        return await sampler.refresh_all_samples()

    try:
        results = run_async(_refresh())

        if not results:
            console.print("[yellow]No voice reference accounts found[/yellow]")
            return

        table = Table(title="Voice Samples Refreshed")
        table.add_column("Account", style="cyan")
        table.add_column("New Samples", style="green")

        total = 0
        for handle, count in results.items():
            table.add_row(f"@{handle}", str(count))
            total += count

        console.print(table)
        console.print(f"\n[green]Total new samples: {total}[/green]")

    except Exception as e:
        console.print(f"[red]Error refreshing samples: {e}[/red]")
        raise click.Abort()


@cli.command()
def voice_sample_stats():
    """Show statistics about voice samples."""
    from src.services.voice_sampler import get_voice_sampler

    console.print("[bold blue]Voice sample statistics...[/bold blue]")

    async def _stats():
        sampler = get_voice_sampler()
        return await sampler.get_sample_stats()

    try:
        stats = run_async(_stats())

        console.print(f"\n[bold]Reference accounts:[/bold] {stats['total_reference_accounts']}")
        console.print(f"[bold]Total samples:[/bold] {stats['total_samples']}")

        if stats["accounts"]:
            console.print("\n[bold]Samples per account:[/bold]")
            for handle, count in stats["accounts"].items():
                console.print(f"  @{handle}: {count}")

    except Exception as e:
        console.print(f"[red]Error getting stats: {e}[/red]")
        raise click.Abort()


# =============================================================================
# UTILITY COMMANDS
# =============================================================================

@cli.command()
def test_slack():
    """Send a test message to Slack."""
    from src.integrations.slack import get_slack_client

    console.print("[bold blue]Sending test message to Slack...[/bold blue]")

    async def _test():
        slack = get_slack_client()
        return await slack.send_message("Test message from Content Agent CLI")

    try:
        success = run_async(_test())
        if success:
            console.print("[green]Test message sent successfully![/green]")
        else:
            console.print("[red]Failed to send test message[/red]")

    except Exception as e:
        console.print(f"[red]Error sending test message: {e}[/red]")
        raise click.Abort()


@cli.command()
def test_twitter():
    """Test Twitter API connection."""
    from src.integrations.twitter import get_twitter_client

    console.print("[bold blue]Testing Twitter API...[/bold blue]")

    async def _test():
        twitter = get_twitter_client()
        # Try to fetch a known account
        return await twitter.get_user_by_username("marksx_io")

    try:
        user = run_async(_test())
        if user:
            console.print(f"[green]Twitter API working! Found: @{user['username']} ({user['followers_count']:,} followers)[/green]")
        else:
            console.print("[yellow]Twitter API connected but could not find test account[/yellow]")

    except Exception as e:
        console.print(f"[red]Error testing Twitter API: {e}[/red]")
        raise click.Abort()


if __name__ == "__main__":
    cli()

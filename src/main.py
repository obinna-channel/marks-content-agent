"""Main entry point for Content Agent background workers."""

import asyncio
import signal
import sys
from datetime import datetime
from typing import Optional

from src.config import get_settings
from src.monitors.twitter_monitor import TwitterMonitor
from src.monitors.rss_monitor import get_rss_monitor
from src.agent.relevance import get_relevance_scorer


class ContentAgentWorker:
    """Background worker that runs monitoring loops."""

    def __init__(self):
        self.settings = get_settings()
        self.twitter_monitor = TwitterMonitor()
        self.rss_monitor = get_rss_monitor()
        self.relevance_scorer = get_relevance_scorer()
        self._running = False
        self._twitter_task: Optional[asyncio.Task] = None
        self._rss_task: Optional[asyncio.Task] = None

    async def twitter_loop(self):
        """Continuously poll Twitter accounts."""
        print(f"[{datetime.utcnow().isoformat()}] Starting Twitter monitor (interval: {self.settings.twitter_poll_interval}s)")

        while self._running:
            try:
                print(f"[{datetime.utcnow().isoformat()}] Running Twitter check cycle...")
                summary = await self.twitter_monitor.run_check_cycle(self.relevance_scorer)
                print(
                    f"[{datetime.utcnow().isoformat()}] Twitter check complete: "
                    f"{summary['accounts_checked']} accounts, "
                    f"{summary['tweets_found']} tweets, "
                    f"{summary['notifications_sent']} notifications"
                )
            except Exception as e:
                print(f"[{datetime.utcnow().isoformat()}] Twitter loop error: {e}")

            # Wait for next cycle
            await asyncio.sleep(self.settings.twitter_poll_interval)

    async def rss_loop(self):
        """Continuously poll RSS feeds."""
        print(f"[{datetime.utcnow().isoformat()}] Starting RSS monitor (interval: {self.settings.rss_poll_interval}s)")

        while self._running:
            try:
                print(f"[{datetime.utcnow().isoformat()}] Running RSS check cycle...")
                summary = await self.rss_monitor.run_check_cycle()
                print(
                    f"[{datetime.utcnow().isoformat()}] RSS check complete: "
                    f"{summary['sources_checked']} sources, "
                    f"{summary['items_found']} items, "
                    f"{summary['notifications_sent']} notifications"
                )
            except Exception as e:
                print(f"[{datetime.utcnow().isoformat()}] RSS loop error: {e}")

            # Wait for next cycle
            await asyncio.sleep(self.settings.rss_poll_interval)

    async def start(self):
        """Start all monitoring loops."""
        if not self.settings.content_agent_enabled:
            print("Content Agent is disabled. Set CONTENT_AGENT_ENABLED=true to enable.")
            return

        print(f"[{datetime.utcnow().isoformat()}] Content Agent starting...")
        self._running = True

        # Start both loops concurrently
        self._twitter_task = asyncio.create_task(self.twitter_loop())
        self._rss_task = asyncio.create_task(self.rss_loop())

        # Wait for both tasks
        try:
            await asyncio.gather(self._twitter_task, self._rss_task)
        except asyncio.CancelledError:
            print(f"[{datetime.utcnow().isoformat()}] Content Agent shutting down...")

    async def stop(self):
        """Stop all monitoring loops gracefully."""
        print(f"[{datetime.utcnow().isoformat()}] Stopping Content Agent...")
        self._running = False

        # Cancel tasks
        if self._twitter_task:
            self._twitter_task.cancel()
        if self._rss_task:
            self._rss_task.cancel()

        # Wait for cancellation
        tasks = [t for t in [self._twitter_task, self._rss_task] if t]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        print(f"[{datetime.utcnow().isoformat()}] Content Agent stopped.")


async def run_twitter_only():
    """Run only the Twitter monitor (useful for testing)."""
    settings = get_settings()
    twitter_monitor = TwitterMonitor()
    relevance_scorer = get_relevance_scorer()

    print(f"[{datetime.utcnow().isoformat()}] Running single Twitter check...")
    summary = await twitter_monitor.run_check_cycle(relevance_scorer)
    print(f"Results: {summary}")


async def run_rss_only():
    """Run only the RSS monitor (useful for testing)."""
    rss_monitor = get_rss_monitor()

    print(f"[{datetime.utcnow().isoformat()}] Running single RSS check...")
    summary = await rss_monitor.run_check_cycle()
    print(f"Results: {summary}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Content Agent Worker")
    parser.add_argument(
        "--mode",
        choices=["full", "twitter", "rss"],
        default="full",
        help="Which monitors to run",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (instead of continuous loop)",
    )
    args = parser.parse_args()

    # Set up signal handlers
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    worker = ContentAgentWorker()

    def signal_handler(sig, frame):
        print(f"\nReceived signal {sig}, shutting down...")
        loop.create_task(worker.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        if args.once:
            # Single run mode
            if args.mode == "twitter":
                loop.run_until_complete(run_twitter_only())
            elif args.mode == "rss":
                loop.run_until_complete(run_rss_only())
            else:
                # Run both once
                loop.run_until_complete(run_twitter_only())
                loop.run_until_complete(run_rss_only())
        else:
            # Continuous mode
            if args.mode == "twitter":
                worker._running = True
                loop.run_until_complete(worker.twitter_loop())
            elif args.mode == "rss":
                worker._running = True
                loop.run_until_complete(worker.rss_loop())
            else:
                loop.run_until_complete(worker.start())
    except KeyboardInterrupt:
        print("\nShutdown requested...")
    finally:
        # Cleanup
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
        print("Goodbye!")


if __name__ == "__main__":
    main()

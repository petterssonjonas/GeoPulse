"""Smart tiered scraping scheduler with escalation."""
import logging
import subprocess
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from storage.config import Config, load_sources
from storage.database import (
    insert_article, article_exists, get_recent_articles, mark_articles_used,
    insert_briefing, get_user_topics, run_retention_cleanup,
    get_source_check_time, set_source_check_time,
)
from scraping.fetchers import (
    fetch_sources_by_tier, fetch_all_sources, search_google_news,
    extract_article_text,
)
from analysis.triage import score_severity, match_topics, enrich_article
from analysis.briefing import generate_briefing
from providers import create_provider

logger = logging.getLogger(__name__)

SEVERITY_LABELS = {1: "Routine", 2: "Low", 3: "Moderate", 4: "High", 5: "CRITICAL"}


class SmartScheduler:
    """
    Tiered news ingestion scheduler.

    Tier 1 (sentinel) checked on interval. If notable activity detected,
    tier 2 (context) sources are fetched immediately. If breaking-level
    severity is found, tier 3 (official) sources are also fetched and
    a breaking briefing is generated on the spot.
    """

    def __init__(self,
                 on_status: Callable[[str], None] = None,
                 on_briefing: Callable[[int], None] = None,
                 on_refresh: Callable[[], None] = None):
        self.on_status = on_status or (lambda s: None)
        self.on_briefing = on_briefing or (lambda bid: None)
        self.on_refresh = on_refresh or (lambda: None)
        self._running = False
        self._sentinel_timer: Optional[threading.Timer] = None
        self._briefing_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def start(self):
        self._running = True
        logger.info("Scheduler started")
        schedule = Config.schedule()
        s_int = schedule.get("sentinel_interval_minutes", 15)
        b_int = schedule.get("briefing_interval_minutes", 60)
        logger.info(f"  Sentinel every {s_int}m, briefings every {b_int}m")

        # Do not run sentinel immediately on start — respect min interval from last run (persisted)
        delay = self._seconds_until_tier_allowed(1)
        if delay is not None and delay > 0:
            logger.info(f"  First sentinel in {delay}s (min interval)")
            self._sentinel_timer = threading.Timer(delay, self._tick_sentinel)
            self._sentinel_timer.daemon = True
            self._sentinel_timer.start()
        else:
            threading.Thread(target=self._sentinel_cycle, daemon=True).start()
        self._schedule_briefing()

    def stop(self):
        self._running = False
        for t in (self._sentinel_timer, self._briefing_timer):
            if t:
                t.cancel()
        logger.info("Scheduler stopped")

    # ── Sentinel cycle ────────────────────────────────────────────────────────

    def _min_interval_seconds(self, tier: int) -> int:
        schedule = Config.schedule()
        if tier == 1:
            return schedule.get("sentinel_min_interval_minutes", 5) * 60
        return schedule.get("other_sources_min_interval_minutes", 20) * 60

    def _can_run_tier(self, tier: int) -> bool:
        """True if enough time has passed since last check for this tier."""
        last = get_source_check_time(tier)
        if last is None:
            return True
        try:
            dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - dt).total_seconds()
            return elapsed >= self._min_interval_seconds(tier)
        except Exception:
            return True

    def _seconds_until_tier_allowed(self, tier: int) -> Optional[int]:
        """Seconds until we're allowed to run this tier again, or 0/None if allowed now."""
        last = get_source_check_time(tier)
        if last is None:
            return 0
        try:
            dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - dt).total_seconds()
            min_sec = self._min_interval_seconds(tier)
            if elapsed >= min_sec:
                return 0
            return int(min_sec - elapsed)
        except Exception:
            return 0

    def _sentinel_cycle(self):
        if not self._running:
            return
        if not self._can_run_tier(1):
            sec = self._seconds_until_tier_allowed(1)
            if sec is not None and sec > 0:
                mins = (sec + 59) // 60
                self.on_status(f"Next check in {mins} min")
                self._schedule_sentinel(delay_seconds=sec)
            return
        set_source_check_time(1)
        self.on_status("Checking news sources…")
        try:
            new_articles = self._fetch_and_store_tier(1)
            if not new_articles:
                self.on_status("All quiet · no new articles")
                self._schedule_sentinel()
                return

            max_sev = max(a.get("severity", 1) for a in new_articles)
            threshold = Config.schedule().get("breaking_threshold", 4)

            if max_sev >= threshold:
                self._escalate_breaking()
            elif max_sev >= 3:
                self._escalate_context()
            else:
                self.on_status(f"{len(new_articles)} new articles · routine")
                self.on_refresh()
            self._schedule_sentinel()
        except Exception as e:
            logger.error(f"Sentinel cycle error: {e}", exc_info=True)
            self.on_status(f"Error: {e}")
            self._schedule_sentinel()

    def _escalate_context(self):
        self.on_status("Notable activity · checking analysis sources…")
        if self._can_run_tier(2):
            set_source_check_time(2)
            self._fetch_and_store_tier(2)
        self.on_refresh()

    def _escalate_breaking(self):
        self.on_status("⚠ Breaking activity · full source check…")
        if self._can_run_tier(2):
            set_source_check_time(2)
            self._fetch_and_store_tier(2)
        if self._can_run_tier(3):
            set_source_check_time(3)
            self._fetch_and_store_tier(3)
        self._do_generate_briefing("breaking")

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def _fetch_and_store_tier(self, tier: int) -> list:
        logger.info(f"Fetching tier {tier} sources…")
        articles = fetch_sources_by_tier(tier)
        return self._store_articles(articles, tier)

    def _store_articles(self, raw_articles: list, tier: int = 1) -> list:
        topics = get_user_topics()
        topic_names = [t["name"] for t in topics]
        topic_keywords = {t["name"]: t.get("keywords", []) for t in topics}
        stored = []
        for article in raw_articles:
            if article_exists(article["url"]):
                continue
            article["severity"] = score_severity(article["title"], article.get("summary", ""))
            article["topics"] = match_topics(article["title"], article.get("summary", ""), topic_keywords)
            if article["severity"] >= 3:
                article = enrich_article(article)
            result = insert_article(article)
            if result:
                article["id"] = result
                stored.append(article)
        if stored:
            logger.info(f"Stored {len(stored)} new articles (tier {tier})")
        return stored

    # ── Briefing generation ───────────────────────────────────────────────────

    def _do_generate_briefing(self, briefing_type: str = "scheduled"):
        schedule = Config.schedule()
        max_articles = schedule.get("max_articles_per_briefing", 20)
        articles = get_recent_articles(hours=24, limit=max_articles)
        if not articles:
            self.on_status("No articles for briefing")
            return

        relevant = [a for a in articles if a.get("topics") or a.get("severity", 1) >= 3]
        if len(relevant) < 2:
            self.on_status("Too few relevant articles for briefing")
            return

        self.on_status("Generating briefing via AI…")
        try:
            provider = create_provider()
            topics = [t["name"] for t in get_user_topics()]
            depth = Config.briefing_depth()
            briefing = generate_briefing(relevant[:max_articles], topics, provider, depth=depth)
            briefing["briefing_type"] = briefing_type
            briefing["source_count"] = len(set(a.get("source_name", "") for a in relevant))
            all_topics = []
            for a in relevant[:max_articles]:
                all_topics.extend(a.get("topics") or [])
            briefing["topics"] = list(dict.fromkeys(all_topics))[:5]

            briefing_id = insert_briefing(briefing)
            mark_articles_used(briefing.get("article_ids", []))
            run_retention_cleanup()

            sev = briefing.get("severity", 1)
            headline = briefing.get("headline", "New Briefing")
            logger.info(f"Briefing #{briefing_id}: [{SEVERITY_LABELS.get(sev, '?')}] {headline}")

            self.on_briefing(briefing_id)
            self.on_refresh()
            self._send_notification(briefing, briefing_id)
            self.on_status(f"Briefing ready · {headline}")
        except Exception as e:
            logger.error(f"Briefing generation failed: {e}", exc_info=True)
            self.on_status(f"Briefing error: {e}")

    def _send_notification(self, briefing: dict, briefing_id: int):
        notifications = Config.notifications()
        if not notifications.get("enabled", True):
            return
        sev = briefing.get("severity", 1)
        if sev < notifications.get("min_severity", 3):
            return

        headline = briefing.get("headline", "New Briefing")
        summary = briefing.get("summary", "")[:120]
        urgency = "critical" if sev >= 5 else ("normal" if sev >= 4 else "low")
        icon = "dialog-warning" if sev >= 4 else "dialog-information"
        prefix = "🚨 BREAKING:" if briefing.get("briefing_type") == "breaking" else "📡 GeoPulse:"

        try:
            subprocess.run([
                "notify-send",
                "--app-name=GeoPulse",
                f"--urgency={urgency}",
                f"--icon={icon}",
                "--expire-time=10000",
                f"{prefix} {headline}",
                summary,
            ], capture_output=True, timeout=5)
        except Exception:
            pass

    # ── Manual refresh ────────────────────────────────────────────────────────

    def refresh_now(self):
        """Run sentinel + briefing only if min interval since last sentinel check has passed."""
        if not self._can_run_tier(1):
            sec = self._seconds_until_tier_allowed(1)
            if sec is not None and sec > 0:
                mins = (sec + 59) // 60
                self.on_status(f"Next check allowed in {mins} min")
            return
        threading.Thread(target=self._manual_refresh, daemon=True).start()

    def _manual_refresh(self):
        self._sentinel_cycle()
        self._do_generate_briefing("on_demand")

    # ── On-demand search ──────────────────────────────────────────────────────

    def search_now(self, query: str = None):
        threading.Thread(target=self._run_search, args=(query,), daemon=True).start()

    def _run_search(self, query: str = None):
        self.on_status(f"Searching: {query or 'your topics'}…")
        try:
            if not query:
                topics = get_user_topics()
                query = " OR ".join(t["name"] for t in topics[:5])

            search_articles = search_google_news(query, limit=25)
            self.on_status(f"Fetching all configured sources…")
            all_source_articles = fetch_all_sources()
            combined = search_articles + all_source_articles

            stored = self._store_articles(combined, tier=0)

            if len(stored) < 2:
                self.on_status("Nothing much happening right now")
                self.on_refresh()
                return

            self._do_generate_briefing("on_demand")
        except Exception as e:
            logger.error(f"On-demand search error: {e}", exc_info=True)
            self.on_status(f"Search error: {e}")

    # ── Timers ────────────────────────────────────────────────────────────────

    def _schedule_sentinel(self, delay_seconds: int = None):
        if not self._running:
            return
        if delay_seconds is None:
            interval = Config.schedule().get("sentinel_interval_minutes", 15) * 60
        else:
            interval = max(1, delay_seconds)
        self._sentinel_timer = threading.Timer(interval, self._tick_sentinel)
        self._sentinel_timer.daemon = True
        self._sentinel_timer.start()

    def _tick_sentinel(self):
        self._sentinel_cycle()

    def _schedule_briefing(self):
        if not self._running:
            return
        interval = Config.schedule().get("briefing_interval_minutes", 60) * 60
        self._briefing_timer = threading.Timer(interval, self._tick_briefing)
        self._briefing_timer.daemon = True
        self._briefing_timer.start()

    def _tick_briefing(self):
        if self._running:
            self._do_generate_briefing("scheduled")
        self._schedule_briefing()


def run_one_ingestion() -> int:
    """One-shot ingestion for CLI use."""
    from storage.config import Config
    topics_db = get_user_topics()
    topic_keywords = {t["name"]: t.get("keywords", []) for t in topics_db}
    articles = fetch_all_sources()
    count = 0
    for article in articles:
        if article_exists(article["url"]):
            continue
        article["severity"] = score_severity(article["title"], article.get("summary", ""))
        article["topics"] = match_topics(article["title"], article.get("summary", ""), topic_keywords)
        if article["severity"] >= 3:
            article = enrich_article(article)
        result = insert_article(article)
        if result:
            count += 1
    return count

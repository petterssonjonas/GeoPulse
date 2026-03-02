#!/usr/bin/env python3
"""
GeoPulse - Geopolitical Intelligence Assistant
Local AI-powered news monitoring and analysis.

Usage:
  python main.py                  # Launch the GUI
  python main.py --briefing 42    # Open a specific briefing
  python main.py --fetch           # Run one ingestion cycle (CLI)
  python main.py --generate        # Generate one briefing (CLI)
  python main.py --list            # List recent briefings (CLI)
"""
import argparse
import sys
import os
import logging

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def main():
    parser = argparse.ArgumentParser(prog="geopulse", description="GeoPulse - Geopolitical Intelligence Assistant")
    parser.add_argument("--briefing", "-b", type=int, metavar="ID", help="Open a specific briefing")
    parser.add_argument("--fetch", action="store_true", help="Run one ingestion cycle and exit")
    parser.add_argument("--generate", action="store_true", help="Generate one briefing and exit")
    parser.add_argument("--list", action="store_true", help="List recent briefings")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.fetch:
        from storage.config import ensure_dirs, load_default_topics
        from storage.database import init_db, seed_default_topics
        from scraping.scheduler import run_one_ingestion
        ensure_dirs()
        init_db()
        seed_default_topics(load_default_topics())
        count = run_one_ingestion()
        print(f"Ingestion complete: {count} new articles stored")
        return

    if args.generate:
        from storage.config import ensure_dirs, load_default_topics, Config
        from storage.database import (
            init_db, seed_default_topics, get_recent_articles,
            insert_briefing, mark_articles_used,
        )
        from providers import create_provider
        from analysis.briefing import generate_briefing
        ensure_dirs()
        init_db()
        seed_default_topics(load_default_topics())
        articles = get_recent_articles(hours=24, limit=20)
        if not articles:
            print("No recent articles. Run --fetch first.")
            sys.exit(1)
        provider = create_provider()
        print(f"Generating briefing from {len(articles)} articles…")
        from storage.database import get_user_topics
        topics = [t["name"] for t in get_user_topics()]
        briefing = generate_briefing(articles, topics, provider)
        bid = insert_briefing(briefing)
        mark_articles_used(briefing.get("article_ids", []))
        sev = briefing.get("severity", 1)
        print(f"\n[{sev}/5] {briefing.get('headline', '?')}")
        print(f"\n{briefing.get('summary', '')}")
        print(f"\nBriefing #{bid} saved")
        return

    if args.list:
        from storage.config import ensure_dirs
        from storage.database import init_db, get_briefings
        ensure_dirs()
        init_db()
        briefings = get_briefings(limit=15)
        if not briefings:
            print("No briefings yet.")
            return
        print(f"\n{'#':<5} {'SEV':<4} {'TYPE':<10} {'TIME':<20} HEADLINE")
        print("─" * 80)
        for b in briefings:
            mark = " " if b.get("is_read") else "*"
            print(
                f"{mark}{b['id']:<4} "
                f"{b.get('severity', 1):<4} "
                f"{b.get('briefing_type', 'scheduled'):<10} "
                f"{b.get('created_at', '')[:16]:<20} "
                f"{b.get('headline', '')[:50]}"
            )
        return

    # ── Launch GTK UI ─────────────────────────────────────────────────────────
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
    except (ImportError, ValueError) as e:
        print(f"Error: GTK4/Libadwaita not available: {e}")
        print("Install: sudo dnf install python3-gobject gtk4 libadwaita")
        sys.exit(1)

    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    from ui.app import GeoPulseApp
    app = GeoPulseApp(open_briefing_id=args.briefing)
    sys.exit(app.run(sys.argv[:1]))


if __name__ == "__main__":
    main()

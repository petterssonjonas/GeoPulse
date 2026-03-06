#!/usr/bin/env python3
"""Test all sources in data/sources.yaml. Reports working/broken and article count.
Run from repo root: python scripts/test_sources.py
"""
import sys
from pathlib import Path

# Allow importing from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import feedparser
import requests
from bs4 import BeautifulSoup

from scraping.fetchers import HEADERS, REQUEST_TIMEOUT

# Slightly shorter timeout for quick script runs
TEST_TIMEOUT = min(15, REQUEST_TIMEOUT)


def test_rss(url: str) -> tuple:
    """Returns (ok, count, message)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TEST_TIMEOUT)
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        if getattr(feed, "bozo", False) and not getattr(feed, "entries", None):
            exc = getattr(feed, "bozo_exception", None)
            return False, 0, str(exc) if exc else "parse error (bozo)"
        entries = feed.get("entries", [])
        count = sum(1 for e in entries[:50] if e.get("link") and e.get("title"))
        return True, count, "" if count else "no entries with link+title"
    except Exception as e:
        return False, 0, str(e)


def test_atom(url: str) -> tuple:
    return test_rss(url)


def test_scrape(url: str, selector: str, base_url: str = "") -> tuple:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.select(selector)[:30]
        count = sum(1 for ln in links if ln.get("href") and ln.get_text(strip=True))
        return True, count, "" if count else "no matching links"
    except Exception as e:
        return False, 0, str(e)


def main():
    from storage.config import load_sources

    sources = load_sources()
    if not sources:
        print("No sources loaded from data/sources.yaml")
        return 1

    print("Testing sources from data/sources.yaml\n")
    results = []
    for s in sources:
        name = s.get("name", "?")
        url = s.get("url", "")
        stype = (s.get("type") or "rss").lower()
        tier = s.get("tier", "?")
        if stype == "rss":
            ok, count, msg = test_rss(url)
        elif stype == "atom":
            ok, count, msg = test_atom(url)
        elif stype == "scrape":
            cfg = s.get("scrape_config", {})
            sel = cfg.get("article_selector", "a")
            base = cfg.get("base_url", "")
            ok, count, msg = test_scrape(url, sel, base)
        else:
            ok, count, msg = False, 0, "unknown type"
        status = "working" if ok and count else ("broken" if not ok else "empty")
        results.append((name, tier, status, count, msg))
        badge = "OK" if ok and count else "FAIL"
        print(f"  [{badge}] Tier {tier} {name}: {count} items" + (f" — {msg}" if msg else ""))

    print("\n--- Summary ---")
    working = [r for r in results if r[2] == "working"]
    broken = [r for r in results if r[2] == "broken"]
    empty = [r for r in results if r[2] == "empty"]
    print(f"Working: {len(working)}")
    print(f"Broken:  {len(broken)}")
    print(f"Empty:   {len(empty)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

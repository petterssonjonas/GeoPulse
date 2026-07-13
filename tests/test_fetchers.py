"""Unit tests for source fetch/parsing helpers."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from scraping import fetchers


class _FeedEntry(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e


class _FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def _feed(entries, bozo=False):
    return SimpleNamespace(
        bozo=bozo,
        bozo_exception=Exception("bad feed") if bozo else None,
        entries=entries,
    )


class TestFetchers(unittest.TestCase):
    def test_parse_feed_date_prefers_published(self):
        entry = _FeedEntry(published_parsed=(2026, 7, 13, 12, 34, 56, 0, 0, 0))
        self.assertEqual(fetchers._parse_feed_date(entry), "2026-07-13T12:34:56+00:00")

    def test_fetch_rss_source_parses_html_summary_and_skips_bad_items(self):
        source = {"name": "World Feed", "url": "https://example.com/world.rss"}
        entries = [
            _FeedEntry({
                "title": "  Stable update in the region  ",
                "link": "https://example.com/1",
                "summary": "<p>Good <b>story</b>.</p>",
            }),
            _FeedEntry({"title": "  ", "link": "https://example.com/no-title", "summary": "bad"}),
            _FeedEntry({"title": "No link", "link": "", "summary": "bad"}),
        ]

        with patch.object(fetchers.feedparser, "parse", return_value=_feed(entries)):
            articles = fetchers.fetch_rss_source(source)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Stable update in the region")
        self.assertEqual(articles[0]["summary"], "Good story .")

    def test_fetch_rss_source_returns_empty_for_bad_feed(self):
        source = {"name": "Bad Feed", "url": "https://example.com/bad.rss"}
        with patch.object(fetchers.feedparser, "parse", return_value=_feed([], bozo=True)):
            articles = fetchers.fetch_rss_source(source)
        self.assertEqual(articles, [])

    def test_fetch_scrape_source_builds_absolute_urls(self):
        source = {
            "name": "Scrape Source",
            "url": "https://example.com/news/",
            "scrape_config": {
                "article_selector": "a",
                "base_url": "https://example.com",
            },
            "tier": 3,
            "region": "global",
        }
        html = "<html><a href=\"/item/1\">A long enough article headline</a></html>"
        with patch("scraping.fetchers.requests.get", return_value=_FakeResponse(html)):
            articles = fetchers.fetch_scrape_source(source)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["url"], "https://example.com/item/1")
        self.assertEqual(articles[0]["source_name"], "Scrape Source")

    def test_search_google_news_splits_source_from_title(self):
        query_feed = _feed([
            _FeedEntry({
                "title": "Headline from test site - Reuters",
                "link": "https://example.com/1",
                "summary": "<p>Test summary</p>",
            }),
        ])
        with patch.object(fetchers.feedparser, "parse", return_value=query_feed):
            articles = fetchers.search_google_news("whatever", limit=5)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Headline from test site")
        self.assertEqual(articles[0]["source_name"], "Reuters")

    def test_fetch_rss_source_includes_browser_headers_when_fetching_scrape_pages(self):
        source = {
            "name": "Scrape Source",
            "url": "https://example.com/news/",
            "scrape_config": {"article_selector": "a"},
        }
        html = "<html><a href=\"/item/1\">A long enough article headline</a></html>"
        with patch("scraping.fetchers.requests.get", return_value=_FakeResponse(html)) as req_get:
            fetchers.fetch_scrape_source(source)
        req_get.assert_called_once_with(
            source["url"],
            headers=fetchers.HEADERS,
            timeout=fetchers.REQUEST_TIMEOUT,
        )

    def test_fetch_sources_by_tier_deduplicates_duplicate_urls(self):
        first = {"name": "Source A"}
        second = {"name": "Source B"}

        with patch.object(fetchers, "load_sources", return_value=[first, second]):
            with patch.object(
                fetchers,
                "fetch_source",
                side_effect=[
                    [{"url": "https://example.com/article", "title": "A1"}],
                    [{"url": "https://example.com/article", "title": "A2"},
                     {"url": "https://example.com/other", "title": "B1"}],
                ],
            ):
                articles = fetchers.fetch_sources_by_tier(1)

        self.assertEqual(len(articles), 2)
        self.assertEqual([a["url"] for a in articles], [
            "https://example.com/article",
            "https://example.com/other",
        ])


if __name__ == "__main__":
    unittest.main()

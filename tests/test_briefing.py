"""Unit tests for briefing prompt parsing and helper extraction."""
import unittest

from analysis import briefing


class _DummyProvider:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    def chat(self, messages, stream: bool = False):
        self.calls += 1
        return self.reply

    def stream_chat(self, messages):
        raise NotImplementedError


class TestNovelty(unittest.TestCase):
    def test_check_novelty_returns_skip(self):
        provider = _DummyProvider("SKIP, not new")
        article = {"title": "X", "url": "https://example.com/x"}
        out = briefing.check_novelty([article], [{"id": 7, "headline": "old"}], provider)
        self.assertEqual(out, "skip")
        self.assertEqual(provider.calls, 1)

    def test_check_novelty_returns_update_tuple(self):
        provider = _DummyProvider("UPDATE 12 requested")
        article = {"title": "X", "url": "https://example.com/x"}
        out = briefing.check_novelty([article], [{"id": 2, "headline": "old"}], provider)
        self.assertEqual(out, ("update", 12))

    def test_check_novelty_defaults_to_full(self):
        provider = _DummyProvider("NEW: this is a full item")
        article = {"title": "X", "url": "https://example.com/x"}
        out = briefing.check_novelty([article], [{"id": 2, "headline": "old"}], provider)
        self.assertEqual(out, "full")

    def test_check_novelty_no_recent_briefings(self):
        provider = _DummyProvider("SKIP")
        article = {"title": "X", "url": "https://example.com/x"}
        out = briefing.check_novelty([article], [], provider)
        self.assertEqual(out, "full")
        self.assertEqual(provider.calls, 0)

    def test_check_novelty_non_string_response(self):
        provider = _DummyProvider(None)
        article = {"title": "X", "url": "https://example.com/x"}
        out = briefing.check_novelty([article], [{"id": 2, "headline": "old"}], provider)
        self.assertEqual(out, "full")


class TestParsingHelpers(unittest.TestCase):
    def test_parse_json_list_supports_json_array_and_bullets(self):
        self.assertEqual(
            briefing._parse_json_list('["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"]')[:10],
            ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
        )
        self.assertEqual(
            briefing._parse_json_list("- a\n* b\n1. c"),
            ["a", "b", "c"],
        )

    def test_parse_json_list_supports_quoted_lines(self):
        self.assertEqual(
            briefing._parse_json_list("'a'\n'b'\n'c'"),
            ["a", "b", "c"],
        )

    def test_parse_topics_line_deduplicates_and_limits(self):
        parsed = briefing._parse_topics_line("World, Politics, World, Security")
        self.assertEqual(parsed, ["World", "Politics", "Security"])

    def test_extract_section_respects_markers(self):
        text = """
<<<SEVERITY>>>
4
<<<CONFIDENCE>>>
medium
<<<HEADLINE>>>
Signal heads
<<<SUMMARY>>>
something
<<<END>>>
"""
        self.assertEqual(briefing._extract_section(text, "HEADLINE"), "Signal heads")
        self.assertEqual(briefing._extract_section(text, "SUMMARY"), "something")

    def test_first_line_like_headline_skips_metadata_lines(self):
        text = """
<<<CONFIDENCE>>>
""" + "x" * 201 + """
Real headline line
"""
        self.assertEqual(briefing._first_line_like_headline(text), "Real headline line")


class TestParseBriefingResponse(unittest.TestCase):
    def test_parse_briefing_response_extracts_fields(self):
        raw = """
<<<SEVERITY>>>
5
<<<CONFIDENCE>>>
high
<<<HEADLINE>>>
Clear headline
<<<SUMMARY>>>
Short summary
<<<DEVELOPMENTS>>>
Developments body
<<<CONTEXT>>>
Context body
<<<ACTORS>>>
Actors body
<<<OUTLOOK>>>
Outlook body
<<<WATCH>>>
["Monitor sanctions", "Oil prices", "A", "B", "C", "D", "E", "F"]
<<<QUESTIONS>>>
1) What changed?
2) Who is accountable?
<<<TOPICS>>>
World, Energy, World
<<<END>>>
"""
        parsed = briefing.parse_briefing_response(raw)
        self.assertEqual(parsed["severity"], 5)
        self.assertEqual(parsed["confidence"], "high")
        self.assertEqual(parsed["headline"], "Clear headline")
        self.assertEqual(parsed["watch_indicators"], ["Monitor sanctions", "Oil prices", "A", "B", "C"])
        self.assertEqual(parsed["suggested_questions"], ["What changed?", "Who is accountable?"])
        self.assertEqual(parsed["topics"], ["World", "Energy"])


class TestFallbackParsing(unittest.TestCase):
    def test_apply_parsing_fallbacks_fills_required_fields(self):
        parsed = {
            "severity": 3,
            "confidence": "medium",
            "headline": "",
            "summary": "",
            "developments": "",
            "context": "",
            "actors": "",
            "outlook": "",
            "watch_indicators": [],
            "suggested_questions": [],
            "topics": [],
            "topics_raw": "World, Economy",
        }
        articles = [
            {
                "title": "Fallback article title",
                "summary": "Fallback article summary line",
                "full_text": "",
            }
        ]
        briefing.apply_parsing_fallbacks(parsed, "", articles)
        self.assertEqual(parsed["headline"], "Fallback article title")
        self.assertEqual(parsed["summary"], "Fallback article summary line")
        self.assertIn("Fallback article title", parsed["developments"])


class TestFormatArticlesForPrompt(unittest.TestCase):
    def test_format_articles_for_prompt_truncates_timestamps(self):
        articles = [
            {
                "title": "A",
                "url": "https://example.com/a",
                "source_name": "Source",
                "published_at": "2026-07-13T12:34:56+00:00",
                "summary": "x" * 700,
            },
            {
                "title": "B",
                "url": "https://example.com/b",
                "source_name": "Source",
                "published_at": "",
                "full_text": "full body",
                "summary": "y",
            },
        ]
        out = briefing.format_articles_for_prompt(articles)
        self.assertIn("[1] Source | 2026-07-13T12:34", out)
        self.assertIn("TITLE: A", out)
        self.assertIn("TITLE: B", out)
        self.assertIn("full body", out)

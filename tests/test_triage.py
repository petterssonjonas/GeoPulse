"""Unit tests for triage scoring, topic matching, and enrichment."""
from unittest import TestCase
from unittest.mock import patch

from analysis import triage


class TestScoreSeverity(TestCase):
    def test_score_severity_follows_priority(self):
        self.assertEqual(triage.score_severity("Routine diplomatic update"), 1)
        self.assertEqual(
            triage.score_severity("Negotiations continue after election protests"),
            3,
        )
        self.assertEqual(
            triage.score_severity("Military operation confirmed near border"),
            4,
        )
        self.assertEqual(
            triage.score_severity("Nuclear weapon launch suspected after missile attack"),
            5,
        )

    def test_score_severity_ignores_case(self):
        self.assertEqual(
            triage.score_severity("MILITARY OPERATION in region"),
            4,
        )


class TestMatchTopics(TestCase):
    def test_match_topics_keyword_matching(self):
        topic_keywords = {
            "Tech": ["GPU", "kernel", "OpenAI"],
            "Conflict": ["summit", "threat"],
        }
        result = triage.match_topics(
            "EU summit discusses AI chips",
            "OpenAI announced a new model",
            topic_keywords,
        )
        self.assertIn("Tech", result)
        self.assertIn("Conflict", result)
        self.assertEqual(len(result), 2)

    def test_match_topics_from_empty_keyword_list(self):
        topic_keywords = {
            "Open Source Movement": [],
            "United States": [],
            "AI": [],
        }
        result = triage.match_topics(
            "Policy report from the United States cabinet cites open-source software spending",
            "",
            topic_keywords,
        )
        self.assertIn("Open Source Movement", result)
        self.assertIn("United States", result)
        self.assertNotIn("AI", result)

    def test_match_topics_empty_input(self):
        self.assertEqual(triage.match_topics("Any title", "Any summary", {}), [])


class TestEnrichArticle(TestCase):
    @patch("analysis.triage.extract_article_text")
    def test_enrich_article_reuses_long_full_text(self, extract_mock):
        article = {
            "url": "https://example.com/a",
            "summary": "x" * 600,
            "full_text": "y" * 250,
        }
        out = triage.enrich_article(article)
        self.assertEqual(out["full_text"], "y" * 250)
        extract_mock.assert_not_called()

    @patch("analysis.triage.extract_article_text")
    def test_enrich_article_promotes_summary(self, extract_mock):
        article = {
            "url": "https://example.com/b",
            "summary": "x" * 320,
            "full_text": "",
        }
        out = triage.enrich_article(article)
        self.assertEqual(out["full_text"], "x" * 320)
        extract_mock.assert_not_called()

    @patch("analysis.triage.extract_article_text")
    def test_enrich_article_fetches_when_needed(self, extract_mock):
        extract_mock.return_value = "extracted text"
        article = {
            "url": "https://example.com/c",
            "summary": "short",
            "full_text": "",
        }
        out = triage.enrich_article(article)
        self.assertEqual(out["full_text"], "extracted text")
        extract_mock.assert_called_once_with("https://example.com/c")

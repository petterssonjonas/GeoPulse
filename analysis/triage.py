"""Fast severity scoring and topic matching for article triage."""
import logging
from storage.config import SEVERITY_KEYWORDS
from scraping.fetchers import extract_article_text

logger = logging.getLogger(__name__)


def score_severity(title: str, summary: str = "") -> int:
    """Keyword-based severity score (1-5). Fast pre-LLM triage."""
    text = (title + " " + summary).lower()

    for word in SEVERITY_KEYWORDS.get("critical", []):
        if word.lower() in text:
            return 5
    for word in SEVERITY_KEYWORDS.get("high", []):
        if word.lower() in text:
            return 4
    for word in SEVERITY_KEYWORDS.get("medium", []):
        if word.lower() in text:
            return 3
    return 1


def match_topics(title: str, summary: str = "", topic_keywords: dict = None) -> list:
    """Match article text against user topics via keywords."""
    if not topic_keywords:
        return []
    text = (title + " " + summary).lower()
    matched = []
    for topic_name, keywords in topic_keywords.items():
        if not keywords:
            words = [w.lower() for w in topic_name.split() if len(w) > 3]
            if sum(1 for w in words if w in text) >= max(1, len(words) - 1):
                matched.append(topic_name)
        else:
            if any(kw.lower() in text for kw in keywords):
                matched.append(topic_name)
    return matched


def enrich_article(article: dict) -> dict:
    """Fetch full text for high-severity articles."""
    if len(article.get("full_text", "")) > 200:
        return article
    if len(article.get("summary", "")) > 300:
        article["full_text"] = article["summary"]
        return article
    text = extract_article_text(article["url"])
    if text:
        article["full_text"] = text
    return article

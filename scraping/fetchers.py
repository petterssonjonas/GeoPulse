"""RSS/Atom feed parsing, HTML scraping, and on-demand search."""
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, quote

import feedparser
import requests
from bs4 import BeautifulSoup

from storage.config import load_sources

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_TIMEOUT = 20


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _parse_feed_date(entry) -> str:
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        val = getattr(entry, field, None)
        if val:
            try:
                dt = datetime(*val[:6], tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception:
                pass
    return _now_iso()


# ─── RSS / ATOM ───────────────────────────────────────────────────────────────

def fetch_rss_source(source: dict) -> list:
    articles = []
    try:
        feed = feedparser.parse(source["url"])
        if feed.bozo and not feed.entries:
            logger.warning(f"Feed error: {source['name']}: {feed.bozo_exception}")
            return []

        for entry in feed.entries[:30]:
            url = entry.get("link", "")
            title = entry.get("title", "").strip()
            if not url or not title:
                continue

            summary = ""
            for field in ("summary", "description", "content"):
                val = entry.get(field, "")
                if isinstance(val, list):
                    val = val[0].get("value", "") if val else ""
                if val:
                    summary = BeautifulSoup(val, "html.parser").get_text(separator=" ", strip=True)[:500]
                    break

            articles.append({
                "url": url,
                "title": title,
                "summary": summary,
                "full_text": "",
                "source_name": source["name"],
                "source_tier": source.get("tier", 1),
                "source_region": source.get("region", ""),
                "published_at": _parse_feed_date(entry),
            })
    except Exception as e:
        logger.error(f"RSS fetch failed: {source['name']}: {e}")
    return articles


# ─── HTML SCRAPING ────────────────────────────────────────────────────────────

def fetch_scrape_source(source: dict) -> list:
    articles = []
    cfg = source.get("scrape_config", {})
    selector = cfg.get("article_selector", "a")
    base_url = cfg.get("base_url", "")
    try:
        resp = requests.get(source["url"], headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.select(selector)[:20]:
            href = link.get("href", "")
            if not href:
                continue
            url = urljoin(base_url or source["url"], href)
            title = link.get_text(strip=True)
            if not title or len(title) < 10:
                continue
            articles.append({
                "url": url,
                "title": title,
                "summary": "",
                "full_text": "",
                "source_name": source["name"],
                "source_tier": source.get("tier", 3),
                "source_region": source.get("region", ""),
                "published_at": _now_iso(),
            })
    except Exception as e:
        logger.error(f"Scrape failed: {source['name']}: {e}")
    return articles


# ─── GOOGLE NEWS SEARCH ──────────────────────────────────────────────────────

def search_google_news(query: str, limit: int = 20) -> list:
    """Search Google News RSS for a topic. No API key needed."""
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
    articles = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:limit]:
            link = entry.get("link", "")
            title = entry.get("title", "").strip()
            if not link or not title:
                continue
            # Google News titles often end with " - Source Name"
            source_name = "Google News"
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                title = parts[0].strip()
                source_name = parts[1].strip()

            articles.append({
                "url": link,
                "title": title,
                "summary": entry.get("summary", ""),
                "full_text": "",
                "source_name": source_name,
                "source_tier": 0,
                "source_region": "global",
                "published_at": _parse_feed_date(entry),
            })
    except Exception as e:
        logger.error(f"Google News search failed for '{query}': {e}")
    return articles


# ─── TEXT EXTRACTION ──────────────────────────────────────────────────────────

def extract_article_text(url: str) -> str:
    try:
        try:
            import trafilatura
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded, favor_recall=True)
                if text and len(text) > 200:
                    return text[:3000]
        except ImportError:
            pass
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "figure"]):
            tag.decompose()
        for sel in ["article", ".article-body", ".story-body", ".post-content", "main", "#content"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 200:
                    return text[:3000]
        return soup.get_text(separator=" ", strip=True)[:2000]
    except Exception as e:
        logger.debug(f"Text extraction failed for {url}: {e}")
        return ""


# ─── ROUTING ──────────────────────────────────────────────────────────────────

def fetch_source(source: dict) -> list:
    src_type = source.get("type", "rss")
    if src_type in ("rss", "atom"):
        return fetch_rss_source(source)
    elif src_type == "scrape":
        return fetch_scrape_source(source)
    else:
        logger.warning(f"Unknown source type: {src_type} for {source['name']}")
        return []


def fetch_sources_by_tier(tier: int) -> list:
    all_articles = []
    for source in load_sources(tier=tier):
        try:
            articles = fetch_source(source)
            logger.info(f"  [{source['name']}] {len(articles)} articles")
            all_articles.extend(articles)
        except Exception as e:
            logger.error(f"  [{source['name']}] error: {e}")
    return all_articles


def fetch_all_sources() -> list:
    all_articles = []
    for source in load_sources():
        try:
            all_articles.extend(fetch_source(source))
        except Exception as e:
            logger.error(f"  [{source['name']}] error: {e}")
    return all_articles

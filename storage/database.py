"""SQLite storage for articles, briefings, conversations, and user topics."""
import sqlite3
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict
from storage.config import get_db_path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_db_path()), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            url             TEXT    UNIQUE NOT NULL,
            title           TEXT    NOT NULL,
            summary         TEXT,
            full_text       TEXT,
            source_name     TEXT,
            source_tier     INTEGER DEFAULT 1,
            source_region   TEXT,
            published_at    TEXT,
            fetched_at      TEXT    NOT NULL,
            severity        INTEGER DEFAULT 1,
            topics          TEXT,
            used_in_briefing INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS briefings (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at          TEXT    NOT NULL,
            headline            TEXT    NOT NULL,
            summary             TEXT    NOT NULL,
            developments        TEXT    NOT NULL,
            context             TEXT,
            actors              TEXT,
            outlook             TEXT,
            watch_indicators    TEXT,
            severity            INTEGER DEFAULT 1,
            confidence          TEXT    DEFAULT 'medium',
            article_ids         TEXT,
            suggested_questions TEXT,
            source_count        INTEGER DEFAULT 0,
            is_read             INTEGER DEFAULT 0,
            briefing_type       TEXT    DEFAULT 'scheduled'
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            briefing_id INTEGER REFERENCES briefings(id),
            created_at  TEXT    NOT NULL,
            messages    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_topics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    UNIQUE NOT NULL,
            keywords    TEXT,
            pinned      INTEGER DEFAULT 0,
            enabled     INTEGER DEFAULT 1,
            created_at  TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_articles_fetched ON articles(fetched_at DESC);
        CREATE INDEX IF NOT EXISTS idx_articles_severity ON articles(severity DESC);
        CREATE INDEX IF NOT EXISTS idx_briefings_created ON briefings(created_at DESC);
    """)
    conn.commit()
    _migrate(conn)
    conn.close()


def _migrate(conn):
    """Add columns that may be missing from an older schema version."""
    migrations = [
        ("articles", "source_tier", "INTEGER DEFAULT 1"),
        ("briefings", "developments", "TEXT"),
        ("briefings", "context", "TEXT"),
        ("briefings", "actors", "TEXT"),
        ("briefings", "outlook", "TEXT"),
        ("briefings", "watch_indicators", "TEXT"),
        ("briefings", "confidence", "TEXT DEFAULT 'medium'"),
        ("briefings", "source_count", "INTEGER DEFAULT 0"),
        ("briefings", "topics", "TEXT"),
    ]
    for table, column, coltype in migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        except sqlite3.OperationalError:
            pass

    # Prevent SQLite 3.25+ from rewriting FK references in other tables
    conn.execute("PRAGMA legacy_alter_table = ON")

    # If the old schema has a 'body NOT NULL' column, rebuild the table
    cols = {r[1] for r in conn.execute("PRAGMA table_info(briefings)").fetchall()}
    if "body" in cols:
        try:
            conn.execute("""
                UPDATE briefings SET developments = body
                WHERE developments IS NULL AND body IS NOT NULL
            """)
        except sqlite3.OperationalError:
            pass
        conn.execute("ALTER TABLE briefings RENAME TO _briefings_old")
        conn.execute("""
            CREATE TABLE briefings (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at          TEXT    NOT NULL,
                headline            TEXT    NOT NULL,
                summary             TEXT    NOT NULL,
                developments        TEXT    NOT NULL DEFAULT '',
                context             TEXT,
                actors              TEXT,
                outlook             TEXT,
                watch_indicators    TEXT,
                severity            INTEGER DEFAULT 1,
                confidence          TEXT    DEFAULT 'medium',
                article_ids         TEXT,
                suggested_questions TEXT,
                source_count        INTEGER DEFAULT 0,
                is_read             INTEGER DEFAULT 0,
                briefing_type       TEXT    DEFAULT 'scheduled',
                topics              TEXT
            )
        """)
        conn.execute("""
            INSERT INTO briefings
                (id, created_at, headline, summary, developments, context, actors,
                 outlook, watch_indicators, severity, confidence, article_ids,
                 suggested_questions, source_count, is_read, briefing_type, topics)
            SELECT
                id, created_at, headline, summary,
                COALESCE(developments, body, ''),
                context, actors, outlook, watch_indicators, severity, confidence,
                article_ids, suggested_questions, source_count, is_read,
                briefing_type, topics
            FROM _briefings_old
        """)
        conn.execute("DROP TABLE _briefings_old")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_briefings_created ON briefings(created_at DESC)")

    # Repair conversations table if a previous migration corrupted its FK reference
    conv_schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='conversations'"
    ).fetchone()
    if conv_schema and "_briefings_old" in (conv_schema[0] or ""):
        conn.execute("ALTER TABLE conversations RENAME TO _conversations_old")
        conn.execute("""
            CREATE TABLE conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                briefing_id INTEGER REFERENCES briefings(id),
                created_at  TEXT    NOT NULL,
                messages    TEXT    NOT NULL
            )
        """)
        conn.execute("INSERT INTO conversations SELECT * FROM _conversations_old")
        conn.execute("DROP TABLE _conversations_old")

    conn.execute("PRAGMA legacy_alter_table = OFF")
    conn.commit()


# ─── ARTICLES ─────────────────────────────────────────────────────────────────

def insert_article(article: dict) -> Optional[int]:
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT OR IGNORE INTO articles
                (url, title, summary, full_text, source_name, source_tier,
                 source_region, published_at, fetched_at, severity, topics)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            article["url"], article["title"],
            article.get("summary", ""), article.get("full_text", ""),
            article.get("source_name", ""), article.get("source_tier", 1),
            article.get("source_region", ""), article.get("published_at", ""),
            _now(), article.get("severity", 1),
            json.dumps(article.get("topics", [])),
        ))
        conn.commit()
        return cur.lastrowid if cur.rowcount > 0 else None
    finally:
        conn.close()


def article_exists(url: str) -> bool:
    conn = get_connection()
    try:
        return conn.execute("SELECT 1 FROM articles WHERE url = ?", (url,)).fetchone() is not None
    finally:
        conn.close()


def get_recent_articles(hours: int = 24, min_severity: int = 1,
                        unused_only: bool = False, limit: int = 50) -> List[Dict]:
    conn = get_connection()
    try:
        query = """
            SELECT * FROM articles
            WHERE fetched_at > datetime('now', ? || ' hours') AND severity >= ?
        """
        params: list = [f"-{hours}", min_severity]
        if unused_only:
            query += " AND used_in_briefing = 0"
        query += " ORDER BY severity DESC, published_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["topics"] = json.loads(d["topics"] or "[]")
            result.append(d)
        return result
    finally:
        conn.close()


def get_breaking_articles(hours: int = 1) -> List[Dict]:
    return get_recent_articles(hours=hours, min_severity=4, unused_only=True)


def mark_articles_used(article_ids: List[int]):
    if not article_ids:
        return
    conn = get_connection()
    try:
        ph = ",".join("?" * len(article_ids))
        conn.execute(f"UPDATE articles SET used_in_briefing = 1 WHERE id IN ({ph})", article_ids)
        conn.commit()
    finally:
        conn.close()


def get_articles_for_briefing(briefing_id: int) -> List[Dict]:
    briefing = get_briefing(briefing_id)
    if not briefing or not briefing.get("article_ids"):
        return []
    ids = briefing["article_ids"]
    conn = get_connection()
    try:
        ph = ",".join("?" * len(ids))
        rows = conn.execute(f"SELECT * FROM articles WHERE id IN ({ph})", ids).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─── BRIEFINGS ────────────────────────────────────────────────────────────────

def insert_briefing(briefing: dict) -> int:
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO briefings
                (created_at, headline, summary, developments, context, actors,
                 outlook, watch_indicators, severity, confidence, article_ids,
                 suggested_questions, source_count, briefing_type, topics)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            _now(), briefing["headline"], briefing["summary"],
            briefing.get("developments", ""),
            briefing.get("context", ""),
            briefing.get("actors", ""),
            briefing.get("outlook", ""),
            json.dumps(briefing.get("watch_indicators", [])),
            briefing.get("severity", 1),
            briefing.get("confidence", "medium"),
            json.dumps(briefing.get("article_ids", [])),
            json.dumps(briefing.get("suggested_questions", [])),
            briefing.get("source_count", 0),
            briefing.get("briefing_type", "scheduled"),
            json.dumps(briefing.get("topics", [])),
        ))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _parse_briefing_row(row) -> dict:
    d = dict(row)
    d["article_ids"] = json.loads(d.get("article_ids") or "[]")
    d["suggested_questions"] = json.loads(d.get("suggested_questions") or "[]")
    d["watch_indicators"] = json.loads(d.get("watch_indicators") or "[]")
    d["topics"] = json.loads(d.get("topics") or "[]")
    d.setdefault("developments", d.get("body", ""))
    d.setdefault("context", "")
    d.setdefault("actors", "")
    d.setdefault("outlook", "")
    d.setdefault("confidence", "medium")
    d.setdefault("source_count", 0)
    return d


def get_briefings(limit: int = 50, unread_only: bool = False) -> List[Dict]:
    conn = get_connection()
    try:
        query = "SELECT * FROM briefings"
        params: list = []
        if unread_only:
            query += " WHERE is_read = 0"
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [_parse_briefing_row(r) for r in rows]
    finally:
        conn.close()


def get_briefing(briefing_id: int) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM briefings WHERE id = ?", (briefing_id,)).fetchone()
        return _parse_briefing_row(row) if row else None
    finally:
        conn.close()


def mark_briefing_read(briefing_id: int):
    conn = get_connection()
    try:
        conn.execute("UPDATE briefings SET is_read = 1 WHERE id = ?", (briefing_id,))
        conn.commit()
    finally:
        conn.close()


def get_unread_count() -> int:
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM briefings WHERE is_read = 0").fetchone()[0]
    finally:
        conn.close()


# ─── CONVERSATIONS ────────────────────────────────────────────────────────────

def create_conversation(briefing_id: int) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO conversations (briefing_id, created_at, messages) VALUES (?, ?, ?)",
            (briefing_id, _now(), "[]"),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_conversation(conv_id: int) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["messages"] = json.loads(d["messages"])
        return d
    finally:
        conn.close()


def append_message(conv_id: int, role: str, content: str):
    conn = get_connection()
    try:
        row = conn.execute("SELECT messages FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if not row:
            return
        messages = json.loads(row[0])
        messages.append({"role": role, "content": content})
        conn.execute("UPDATE conversations SET messages = ? WHERE id = ?", (json.dumps(messages), conv_id))
        conn.commit()
    finally:
        conn.close()


# ─── USER TOPICS ──────────────────────────────────────────────────────────────

def get_user_topics(enabled_only: bool = True) -> List[Dict]:
    conn = get_connection()
    try:
        query = "SELECT * FROM user_topics"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY pinned DESC, name ASC"
        rows = conn.execute(query).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["keywords"] = json.loads(d["keywords"] or "[]")
            result.append(d)
        return result
    finally:
        conn.close()


def add_user_topic(name: str, keywords: list = None, pinned: bool = False) -> Optional[int]:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO user_topics (name, keywords, pinned, created_at) VALUES (?, ?, ?, ?)",
            (name, json.dumps(keywords or []), int(pinned), _now()),
        )
        conn.commit()
        return cur.lastrowid if cur.rowcount > 0 else None
    finally:
        conn.close()


def remove_user_topic(topic_id: int):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM user_topics WHERE id = ?", (topic_id,))
        conn.commit()
    finally:
        conn.close()


def seed_default_topics(topics: list):
    """Insert default topics if the table is empty."""
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM user_topics").fetchone()[0]
        if count > 0:
            return
        for t in topics:
            conn.execute(
                "INSERT OR IGNORE INTO user_topics (name, keywords, pinned, enabled, created_at) VALUES (?, ?, ?, 1, ?)",
                (t["name"], json.dumps(t.get("keywords", [])), int(t.get("pinned", False)), _now()),
            )
        conn.commit()
    finally:
        conn.close()

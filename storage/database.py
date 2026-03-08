"""SQLite storage for articles, briefings, conversations, and user topics."""
import sqlite3
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Callable
from storage.config import get_db_path, Config

# Current schema version after all migrations. Bump when adding a new migration.
CURRENT_SCHEMA_VERSION = 4


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
            briefing_type       TEXT    DEFAULT 'scheduled',
            parent_briefing_id  INTEGER REFERENCES briefings(id)
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
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_info (key TEXT PRIMARY KEY, value INTEGER);
        INSERT OR IGNORE INTO schema_info (key, value) VALUES ('schema_version', 0);
    """)
    conn.commit()
    _run_migrations(conn)
    conn.close()


def _get_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM schema_info WHERE key = 'schema_version'").fetchone()
    return int(row[0]) if row is not None else 0


def get_schema_version() -> int:
    """Return current schema version (for tests and debugging)."""
    conn = get_connection()
    try:
        try:
            return _get_schema_version(conn)
        except sqlite3.OperationalError:
            return 0
    finally:
        conn.close()


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run all pending migrations in order. Uses schema_info.schema_version."""
    for version, migrate_fn in _MIGRATIONS:
        if version <= _get_schema_version(conn):
            continue
        migrate_fn(conn)
        conn.execute("UPDATE schema_info SET value = ? WHERE key = 'schema_version'", (version,))
        conn.commit()


def _migration_1(conn: sqlite3.Connection) -> None:
    """Add missing columns; migrate briefings.body -> developments; repair conversations FK."""
    add_columns = [
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
    for table, column, coltype in add_columns:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        except sqlite3.OperationalError:
            pass

    conn.execute("PRAGMA legacy_alter_table = ON")

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


def _migration_2(conn: sqlite3.Connection) -> None:
    """Persist last source-check time per tier for throttle (sentinel 5 min, other 20 min)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS source_check_log (
            tier INTEGER PRIMARY KEY,
            checked_at TEXT NOT NULL
        )
    """)


def _migration_3(conn: sqlite3.Connection) -> None:
    """Add parent_briefing_id for update sub-cards that attach to an earlier briefing."""
    try:
        conn.execute("ALTER TABLE briefings ADD COLUMN parent_briefing_id INTEGER REFERENCES briefings(id)")
    except sqlite3.OperationalError:
        pass


def _migration_4(conn: sqlite3.Connection) -> None:
    """Scheduler state (e.g. last_morning_briefing_date) for once-per-day morning briefings."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)


_MIGRATIONS: List[tuple[int, Callable[[sqlite3.Connection], None]]] = [
    (1, _migration_1),
    (2, _migration_2),
    (3, _migration_3),
    (4, _migration_4),
]


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


# ─── SOURCE CHECK LOG (throttle: persist last check time per tier) ─────────────

def get_source_check_time(tier: int) -> Optional[str]:
    """Return ISO timestamp of last check for this tier, or None."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT checked_at FROM source_check_log WHERE tier = ?", (tier,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def set_source_check_time(tier: int, checked_at: str = None) -> None:
    """Record that we checked this tier at the given time (default now)."""
    if checked_at is None:
        checked_at = _now()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO source_check_log (tier, checked_at) VALUES (?, ?)",
            (tier, checked_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_scheduler_state(key: str) -> Optional[str]:
    """Return value for a scheduler state key (e.g. last_morning_briefing_date), or None."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM scheduler_state WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def set_scheduler_state(key: str, value: str) -> None:
    """Set a scheduler state key (e.g. last_morning_briefing_date = YYYY-MM-DD)."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO scheduler_state (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


# ─── BRIEFINGS ────────────────────────────────────────────────────────────────

def insert_briefing(briefing: dict) -> int:
    conn = get_connection()
    try:
        parent_id = briefing.get("parent_briefing_id")
        cur = conn.execute("""
            INSERT INTO briefings
                (created_at, headline, summary, developments, context, actors,
                 outlook, watch_indicators, severity, confidence, article_ids,
                 suggested_questions, source_count, briefing_type, topics, parent_briefing_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            parent_id,
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


def get_recent_briefings_for_novelty(limit: int = 5) -> List[Dict]:
    """Return the most recent main briefings (no update sub-cards) for novelty check. Includes id, headline, summary."""
    conn = get_connection()
    try:
        # SQLite: parent_briefing_id may not exist before migration 3
        try:
            rows = conn.execute(
                "SELECT id, created_at, headline, summary FROM briefings WHERE parent_briefing_id IS NULL ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = conn.execute(
                "SELECT id, created_at, headline, summary FROM briefings ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
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


def mark_briefing_unread(briefing_id: int):
    conn = get_connection()
    try:
        conn.execute("UPDATE briefings SET is_read = 0 WHERE id = ?", (briefing_id,))
        conn.commit()
    finally:
        conn.close()


def delete_briefing(briefing_id: int) -> None:
    """Remove a briefing and its conversations."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM conversations WHERE briefing_id = ?", (briefing_id,))
        conn.execute("DELETE FROM briefings WHERE id = ?", (briefing_id,))
        conn.commit()
    finally:
        conn.close()


def update_briefing(briefing_id: int, briefing: dict) -> None:
    """Update an existing briefing's content (e.g. after Go deeper regeneration)."""
    conn = get_connection()
    try:
        conn.execute("""
            UPDATE briefings SET
                headline = ?, summary = ?, developments = ?, context = ?, actors = ?,
                outlook = ?, watch_indicators = ?, severity = ?, confidence = ?,
                article_ids = ?, suggested_questions = ?, source_count = ?, topics = ?
            WHERE id = ?
        """, (
            briefing.get("headline", ""),
            briefing.get("summary", ""),
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
            json.dumps(briefing.get("topics", [])),
            briefing_id,
        ))
        conn.commit()
    finally:
        conn.close()


def get_unread_count() -> int:
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM briefings WHERE is_read = 0").fetchone()[0]
    finally:
        conn.close()


def run_retention_cleanup() -> None:
    """Keep at most max_briefings (newest), drop older briefings and their conversations; drop articles older than article_retention_days."""
    cfg = Config.retention()
    max_briefings = max(1, int(cfg.get("max_briefings", 30)))
    article_days = max(0, int(cfg.get("article_retention_days", 14)))
    conn = get_connection()
    try:
        # Briefings to remove: all but the newest max_briefings (by created_at DESC, so we want ids beyond the first max_briefings)
        rows = conn.execute(
            "SELECT id FROM briefings ORDER BY created_at DESC LIMIT 9999 OFFSET ?",
            (max_briefings,),
        ).fetchall()
        ids_to_remove = [r[0] for r in rows]
        if ids_to_remove:
            placeholders = ",".join("?" * len(ids_to_remove))
            conn.execute(f"DELETE FROM conversations WHERE briefing_id IN ({placeholders})", ids_to_remove)
            conn.execute(f"DELETE FROM briefings WHERE id IN ({placeholders})", ids_to_remove)
        # Articles older than article_retention_days (by fetched_at)
        if article_days > 0:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=article_days)).strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute("DELETE FROM articles WHERE fetched_at < ?", (cutoff,))
        conn.commit()
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


def get_conversation_by_briefing(briefing_id: int) -> Optional[Dict]:
    """Return the most recent conversation for this briefing, or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM conversations WHERE briefing_id = ? ORDER BY id DESC LIMIT 1",
            (briefing_id,),
        ).fetchone()
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

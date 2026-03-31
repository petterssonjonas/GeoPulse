# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

GeoPulse is a local, privacy-first geopolitical intelligence desktop app (GTK4/Libadwaita, Python). A tiered background scheduler ingests curated RSS/web news sources, scores article severity, runs a novelty check, and generates structured briefings via a local or cloud LLM (Ollama, OpenAI, Anthropic). The native GNOME app shows severity-ranked briefings with inline Q&A streaming.

## Running the app

```bash
# Activate venv first
source .venv/bin/activate

# GUI (primary mode)
python main.py

# CLI modes (no GUI)
python main.py --fetch        # run one ingestion cycle
python main.py --generate     # generate one briefing from recent articles
python main.py --list         # list recent briefings
python main.py --briefing 5   # open GUI to briefing #5
python main.py --verbose      # enable DEBUG logging
```

No test suite exists yet (see TODO.md item #3). When tests are added, they go in `tests/` and use pytest with in-memory SQLite.

## Versioning

After changing `__version__` in `version.py`, run:

```bash
python scripts/sync-version.py
```

This updates `packaging/geopulse.spec`, `packaging/AppImageBuilder.yml`, and `README.md`.

## Architecture

```
main.py                   Entry point; CLI flags or launches GTK app
storage/config.py         Config singleton (Config class), path constants, SEVERITY_KEYWORDS
storage/database.py       SQLite via get_connection(); schema versioned (CURRENT_SCHEMA_VERSION)
scraping/fetchers.py      RSS/web fetching (feedparser, requests, trafilatura)
scraping/scheduler.py     SmartScheduler: tiered ingestion, briefing + morning timers
analysis/triage.py        Keyword-based severity scoring (1-5) and topic matching — pre-LLM
analysis/briefing.py      LLM briefing generation, novelty check, prompt management
providers/__init__.py     LLMProvider abstract base + create_provider() factory
providers/ollama.py       Ollama HTTP provider
providers/openai_compat.py OpenAI-compatible provider (also used for custom base_url)
providers/anthropic.py    Anthropic API provider
ui/app.py                 Adw.Application subclass; CSS/theme loading
ui/window.py              Main window; sidebar, stack, scheduler wiring
ui/briefing_view.py       Briefing detail panel
ui/chat_view.py           Inline Q&A with LLM streaming
ui/settings_dialog.py     Settings dialog (LLM, schedule, notifications, prompts, email)
email_briefing.py         mailto / SMTP sending
gpu_stats.py              GPU/VRAM or CPU/RAM stats for header bar
ollama_manager.py         Auto-start/stop Ollama subprocess
data/sources.yaml         News sources by tier (edit and restart to take effect)
data/topics.yaml          Default topics seeded on first run
```

### Data flow

1. `SmartScheduler` polls tier-1 (sentinel) sources on interval.
2. If notable severity detected, tier-2 (context) sources are fetched immediately.
3. If severity ≥ breaking threshold (default 4), tier-3 (official) sources are fetched and a breaking briefing is generated.
4. Articles are stored in SQLite; severity scored by `analysis/triage.py` keyword rules before LLM.
5. `analysis/briefing.py` runs a novelty check (LLM call) to decide SKIP / NEW / UPDATE, then generates the briefing.
6. Scheduler callbacks reach the GTK main thread only via `GLib.idle_add()`.

### Key runtime paths

- Config: `~/.config/geopulse/config.yaml` (deep-merged with `DEFAULT_CONFIG` on load)
- DB: `~/.local/share/geopulse/geopulse.db` (WAL mode, foreign keys on, schema migration on `init_db()`)
- Sources: `data/sources.yaml` — tiers 1/2/3; edit and restart
- Prompts: overridable per-ID in config `prompts:` section; IDs and metadata are in `analysis/briefing.PROMPTS_META`

## Project principles (from TODO.md)

- **Resource-effective and light**: minimal dependencies, process one item at a time, no Electron/web frontend.
- **Stability is critical**: defensive parsing, `try/except` around all external I/O, schema migrations that never leave the DB broken.
- When in doubt, choose the simpler, more predictable approach.

## Config class usage

`Config` is a lazy-loaded in-process singleton. After saving changes call `Config.reload()` to pick them up. Access sections via typed class methods: `Config.llm()`, `Config.schedule()`, `Config.morning_briefing()`, etc.

## Database schema

Schema is versioned (`CURRENT_SCHEMA_VERSION` in `storage/database.py`). Always add a new numbered migration rather than altering `init_db()`'s `CREATE TABLE` statements. Tables: `articles`, `briefings`, `conversations`, `user_topics`, `scheduler_state`, `schema_version`.

## LLM API coding conventions

### Caching strategy

Two cache layers serve different purposes:

**`@lru_cache` (in-session)** — for work that repeats within a single scheduler run: article cleaning passes, triage calls on the same text. Lives in `analysis/` call sites.

```python
import functools

@functools.lru_cache(maxsize=256)
def clean_article_text(raw_text: str) -> str:
    # one LLM cleaning pass per unique raw text per session
    ...
```

**`diskcache` (persistent)** — for slow-changing, expensive-to-fetch content that survives restarts: long-form article full text, YouTube transcripts, podcast transcripts, background context documents. Cache at the fetch layer, not the LLM layer.

```python
import diskcache
from storage.config import DATA_DIR

_content_cache = diskcache.Cache(str(DATA_DIR / "content_cache"))

def fetch_transcript(url: str, ttl: int = 60 * 60 * 72) -> str:  # 72h default
    if url in _content_cache:
        return _content_cache[url]
    text = _expensive_fetch(url)
    _content_cache.set(url, text, expire=ttl)
    return text
```

### Structured output

Use Pydantic models to parse LLM responses instead of raw string manipulation. Parsing belongs in `analysis/briefing.py` call sites, not inside `LLMProvider` implementations (which return raw strings).

```python
from pydantic import BaseModel, Field

class BriefingResponse(BaseModel):
    severity: int = Field(ge=1, le=5)
    headline: str
    summary: str
    developments: str
```

### Cloud API providers only (Anthropic, OpenAI)

Apply `tenacity` and `ratelimit` exclusively inside `providers/anthropic.py` and `providers/openai_compat.py`. Do not add these to the Ollama provider.

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ratelimit import limits, sleep_and_retry

@sleep_and_retry
@limits(calls=50, period=60)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
)
def chat(self, messages, stream=False):
    ...
```

## Adding a new LLM provider

Subclass `LLMProvider` from `providers/__init__.py`, implement `chat()` and `stream_chat()`, add a branch in `create_provider()`.

## Packaging

Flatpak, .deb, .rpm, AppImage are built via GitHub Actions. Local release script: `scripts/make-release.sh`. Flatpak manifest: `packaging/io.geopulse.app.json`. App ID: `io.geopulse.app`.

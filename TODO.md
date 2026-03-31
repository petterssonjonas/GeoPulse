# GeoPulse Roadmap


### Implement
## Brave news search API
https://api-dashboard.search.brave.com/documentation/services/news-search
I have a key, rate limited to 50 requests per second and 1000 per month. Shared with my OpenClaw and Open-webui, and Other keys. After 1000 requests starts costing money.
It costs $5 per 1000 requests, but the first 1000 each month is free. I've set a limit at $6 per month.



### For AI:

Each item includes implementation notes ("note to self") for context continuity across sessions.
Items marked **ASK USER** need a decision before implementation.

---

**Prompting work is tracked separately** → see [`PROMPTING_TODO.md`](PROMPTING_TODO.md). Prompt design and programming are different intellectual challenges; keep them in their own tracks.

---

**Note to self (project principle):** Keep the codebase **resource-effective and light**. Prefer
minimal dependencies, bounded memory (process one item at a time where possible), and no
heavy runtimes (no Electron/web frontend). **Stability is critical** — the app must not crash;
defensive parsing, try/except around external I/O, schema migrations that don't leave the DB
broken, and tests for hot paths. When in doubt, choose the simpler, more predictable approach.

---

## Reliability & Hardening

**Order of operations (reasoning):** Do **foundation** first (migration, parsing — both done; then tests so we don’t regress). Then **data path**: fix source reliability and scraping efficiency so we have good data; add parallel fetch + rate limiting + anti-spam. Then **bounds**: data retention so storage doesn’t grow unbounded. Then **visibility**: source health dashboard (depends on retry/health data). Then **dedup** (ingest-time, per your decision). **UX** last: window/sidebar resize (fix unusable resize, then lag), tags visible, settings reorg, card context menu. Within UX, fix blocking issues (resize) before polish (tags, menus).

- **1. Database migration framework** *(done)*
  Schema changes were fragile; migrations have broken twice.
  *Implementation:* Add `schema_version` table, numbered migrations, run on startup. Use `PRAGMA legacy_alter_table = ON` for renames.
  *Files:* `storage/database.py`
- **2. Robust LLM prompt parsing** *(done)*
  If the model doesn’t produce exact `<<<MARKERS>>>`, all fields come back empty (e.g. StarCoder2:15B).
  *Implementation:* Fallback chain in `parse_briefing_response()`; validate and don’t save empty briefings. See IMPLEMENTATION_ORDER Step 2.
  *Files:* `analysis/briefing.py`
- **3. Automated tests**
  No tests exist. Migrations, parser, and scraping have all had bugs.
  *Implementation:* Use pytest. Priority: migrations (fresh + old DB), `parse_briefing_response()` good/bad/empty, insert round-trip, `score_severity`. In-memory SQLite.
  *Files:* new `tests/` directory
- **4. Fix source reliability**
  Reuters DNS fails, AP feed won’t parse. Only BBC and Al Jazeera work out of 4 tier-1 sources.
  *Implementation:* Add more sources to `data/sources.yaml`. Retry (3 attempts, backoff) in `scraping/fetchers.py`. Per-source error count in DB; skip after 5 consecutive failures until next cycle.
  *Files:* `data/sources.yaml`, `scraping/fetchers.py`, `storage/database.py`
- **5. Parsing and scraping efficiency (light, one-at-a-time, tiered pull)**
  Keep memory and CPU low: pull one article at a time, clean, store, then next. Tiered: sentinel → escalate to context/official on severity.
  *Files:* `scraping/fetchers.py`, `scraping/scheduler.py`, `storage/database.py`
- **6. Parallel scraping with rate limiting**
  Sources fetched serially; with 15+ sources too slow.
  *Implementation:* `ThreadPoolExecutor(max_workers=4)` in fetchers; per-domain rate limiter (e.g. 2s between same domain).
  *Files:* `scraping/fetchers.py`
- **7. Make sure a user can’t spam update**
  Don’t put too much pressure on sites; figure out how much scraping is OK (intervals, max runs).
- **8. Data retention: prevent app data from overflowing**
  Briefings: keep last N (default 30). Articles: keep X days (e.g. 90), optional max MB. Conversations: delete with briefing. Config + cleanup after cycle; VACUUM periodically.
  *Files:* `storage/config.py`, `storage/database.py`, `ui/settings_dialog.py`, `scraping/scheduler.py`
- **9. Source health dashboard in settings**
  Users can’t see which sources work or are broken.
  *Implementation:* `source_health` table; update on each fetch; settings tab with green/yellow/red per source.
  *Files:* `storage/database.py`, `scraping/fetchers.py`, `ui/settings_dialog.py`
- **10. Article deduplication**
  BBC and Al Jazeera cover same stories; LLM gets duplicates. *Decision:* Ingest-time: clean first, then dedup; differing facts/opinions → note in brief and affect Reliability.
  *Implementation:* Dedup at ingest after cleaning; same facts/opinions → keep one; if differ, keep/note both.
  *Files:* `scraping/scheduler.py`, possibly `analysis/dedup.py`
- **11. Window not resizable by corner/edge drag**
  App can’t be resized by dragging corner/edge; resizing via shortcut lags heavily.
  *Implementation:* Ensure window `resizable`; no child consuming resize handle; throttle relayout/redraw during resize.
  *Files:* `ui/window.py`, `ui/app.py`
- **12. Sidebar resize lags heavily**
  Dragging the pane divider causes severe lag.
  *Implementation:* Min/max sidebar width; defer/throttle list updates during drag; no heavy work in resize path.
  *Files:* `ui/window.py`
- **13. Tags fully visible in briefing cards**
  Tags get clipped by sidebar width; cards need dynamic height. *Decision:* Config option — show all tags or 1 row + mouseover.
  *Files:* `ui/window.py`, `ui/style.css`
- **14. Move model selector to settings only**
  Remove model dropdown from header; model choice lives in Settings > AI Engine only. **Also to figure out:** what to do when a model is already loaded in Ollama (e.g. user's coding assistant); consider adopting a suitable smaller model as the default so GeoPulse doesn't conflict with other workloads.
  *Files:* `ui/window.py`, `ui/settings_dialog.py`
- **15. Briefing font and font size** *(done)*
  Let the user change the font and font size of briefing text (headline, body, sections). At least a few presets including **OpenDyslexic** for readability. GNOME/libadwaita typically ships with a set of standard fonts (e.g. Cantarell, Inter, system UI font); we can offer those plus OpenDyslexic if installed. Store choice in config; apply via CSS (e.g. `.body-text`, `.briefing-headline` use the selected font/size).
  *Done:* Settings > Appearance: Theme (Follow system / Light / Dark), Font family (system default + all Pango families, recommended first), Font size (90–130%). Config `appearance.theme`, `briefing_font`, `briefing_font_size`. Optional sound when briefing is ready (default off); `notifications.sound_on_briefing`.
  *Files:* `storage/config.py`, `ui/settings_dialog.py`, `ui/app.py`, `ui/style.css`, `scraping/scheduler.py`
- **16. Briefing card right-click / action menu**
  Options: regenerate, add depth, find more, delete, mark unread.
  *Implementation:* `Gtk.PopoverMenu` on BriefingRow; actions call scheduler/DB as needed.
  *Files:* `ui/window.py`, `scraping/scheduler.py`

- **17. Model selection when another model is already loaded**
  When Ollama already has a model loaded (e.g. user's coding assistant), GeoPulse should not force-switch or conflict. Options: (a) use whatever is loaded for this run and document it, (b) recommend a smaller default model (e.g. qwen3:4b, gemma3:4b) that can coexist or load on demand, (c) show a clear indicator in Settings when the active model differs from the configured default. Decide behavior and document in MODELS.md.
  *Files:* `ollama_manager.py`, `ui/settings_dialog.py`, `MODELS.md`

---

## V2 scope

After v1 is stable and shipped, v2 focuses on: **app-flow and scheduler transparency**, **backend API** (enabler for cross-platform), **Windows and macOS desktop apps**, and **deferred features** from the main roadmap.

### App flow and scheduler (early v2)

- **App-flow optimizations**  
  Review `docs/app-flow.md` and actual code paths; optimize hot paths and avoid redundant work.  
  *Implementation:* Defer non-critical work on window init so first paint is fast; avoid duplicate/heavy work on briefing selection; keep scheduler ticks bounded; reschedule only what’s needed when config changes (morning is done; add sentinel/briefing interval reschedule). Optional: simple “flow” or health view showing which step is running.  
  *Files:* `docs/app-flow.md`, `ui/window.py`, `scraping/scheduler.py`, `storage/database.py`

- **Background / scraping timers: when what runs**  
  Make it clear when each background action runs and reschedule on config change.  
  *Implementation:* Show “Next sentinel: in X min · Next briefing: in Y min · Morning: HH:MM” in status bar or Settings. Reschedule sentinel and briefing timers when user changes intervals in Settings (not just morning). Single place for next-run calculation to avoid drift/double-fire. Optional: per-source or per-tier schedule view when more source types exist (e.g. X every 30 min).  
  *Files:* `scraping/scheduler.py`, `storage/config.py`, `ui/settings_dialog.py`, `ui/window.py`

### Backend API (prerequisite for Windows / Mac / mobile)

- **Extract Python backend into a local REST API** (FastAPI)  
  GTK app talks to API instead of importing storage/scraping directly; enables headless `--serve` and remote/multi-client use.  
  *Implementation:* New `api/` package. Endpoints: briefings, articles, chat, config, status (scheduler state, model, GPU), models. WebSocket for real-time push (new briefing, status). Backwards compat: GTK can still use direct imports if API not running.  
  *Files:* new `api/` package, `main.py`, refactor `ui/window.py` to API client.  
  *See:* “Architecture — Backend API Extraction” below for full detail.

- **Authentication for remote access**  
  Token-based auth when API is exposed beyond localhost; token in config, copy from Settings.  
  *Files:* `api/auth.py`, `storage/config.py`

### Windows and macOS desktop versions

- **Tauri desktop app (Windows + macOS)**  
  Native desktop apps for Windows and Mac, sharing the same Python backend.  
  *Implementation:* Tauri (Rust shell) + Svelte or React front end. Single codebase for both platforms. App talks to Python backend API (bundled as sidecar via PyInstaller/Nuitka, or remote). Native window chrome, system tray, auto-updates. Distribute via website and optionally Microsoft Store / Mac App Store.  
  *Prerequisite:* Backend API extraction complete.  
  *Strategy:* Linux stays free (GTK, open source); Windows/macOS can be paid (one-time or subscription).  
  *See:* “Platform Expansion (Paid)” below for pricing and distribution.

- **Licensing and repo usage for paid versions** *(decided: see **Licensing** section below)*  
  Single repo, all GPLv3; Windows/macOS builds are the same code, packaged and sold. No dual-license or closed repo. Document in README or CONTRIBUTING that binaries may be sold and source remains at the repo; ensure LICENSE and any store listings comply.
  *Files:* `LICENSE`, `README.md`, optional `docs/COMMERCIAL.md` or CONTRIBUTING note

### Other v2 features (from roadmap)

These remain in the main “New Features” list; v2 is the right time to implement them once core and cross-platform are in place.

- **News category tabs** (Geopolitics, Tech, Local, Markets, Custom) — per-tab sources, topics, and briefing schedule.
- **Markets watcher** — currencies, commodities, indices; feed into briefs; own tab/schedule.
- **Context window max** — cap prompt size for brief generation when mixing articles, markets, cross-tab data.
- **Story update tracking** (threaded updates) — append updates to existing briefings instead of new cards; delta summary, “UPDATED” badge.
- **Resource-aware deferral** — skip local LLM when GPU busy; defer generation until idle.
- **Event-based briefing** (if not done in v1) — one card per event; cluster articles by event; cap per cycle.
- **Scheduled brief at set times** — multiple times per day (e.g. 08:00, 13:00) in addition to morning.
- **Do Not Disturb** — time ranges; no notifications and optionally no generation during DND.
- **Source manager in settings** — full source browser, tier assignment, health, add custom sources.
- **Expert commentary** (on demand) — YouTube transcripts, think tanks, podcasts, historical context.
- **Other:** Political leaning, map visualization, confidence calibration, JavaScript-rendered scraping (Playwright optional), briefing history search (FTS5), desktop notifications with actions (open briefing from notification). AI-powered triage, “What did I miss” digest, “Where can I follow this closely?” suggested question, export (markdown/PDF).

---

## New Features

- **X (Twitter) sources via Twikit**
  Add tweets as a **separate source stream** (not part of RSS/sentinel). Use **[Twikit](https://github.com/d60/twikit)** (Python, no API key, login-based scraping; good for small scale).
  *Account:* Create a dedicated X account for the app; use it only for Twikit login (username/email + password). Store credentials in config (or env) securely.
  *Conservative usage:* **Max once every 30 minutes.** Follow a **select few accounts** only: OSINT accounts, world leaders, key official handles. No search spam, no trending abuse.
  *Integration:*
  - **Pull separately** from the main sentinel (don’t mix tweet fetch with RSS tier cycle). Run tweet fetch on its own timer (e.g. every 30 min).
  - **Latest tweets** from the watched accounts are **integrated into the next briefing generation run** — i.e. when we run `_do_generate_briefing`, include the most recent tweet batch (e.g. last N tweets per account, or last 30 min window) alongside recent articles so the LLM can cite “X user @… said …” where relevant.
  - Tweets are **not** sentinel in v1 (they don’t trigger escalation or breaking pull). Optionally later: treat high-signal accounts as sentinel (e.g. if @POTUS or @OSINT_handle posts, could trigger an earlier brief).
  *Implementation:* New `scraping/x_fetcher.py` or `scraping/twikit_client.py`: Twikit client login (once or on demand), fetch user tweets for a list of screen names from config (`data/sources_x.yaml` or `config.x_accounts`). Normalize to article-like records (url, title=text snippet, source_name=@handle, published_at). Store in `articles` with a `source_type: x` or separate `tweets` table; scheduler merges recent tweets into article set passed to `generate_briefing`. Config: `x_enabled`, `x_interval_minutes` (30), `x_accounts` (list of @handles), credentials.
  *Files:* New `scraping/x_fetcher.py` (or twikit_client), `data/sources_x.yaml` (or config section), `storage/config.py`, `storage/database.py` (if tweets table), `scraping/scheduler.py` (30 min timer + merge into briefing input).

- **Event-based briefing generation (one card per event, not one card per roundup)**
  **Problem:** Currently one briefing card = one LLM call that aggregates ALL relevant
  recent articles into a single "news roundup". Result: Ukraine + Iran + Pakistan–Afghanistan
  mixed in one card. User wants **source aggregation per event** — each distinct event gets
  its own card, with all sources covering that event aggregated into that card only.

  *Pipeline change:*
  1. **Event clustering (new step before briefing gen):** From the pool of recent articles,
     group them into distinct events. E.g. cluster A = Ukraine escalation, cluster B = Iran
     regional conflict, cluster C = Pakistan–Afghanistan. Each cluster = one event = one
     future briefing card.
  2. **One briefing per event:** For each cluster, call `generate_briefing(articles_in_cluster, ...)`.
     No mixing of events in a single card.
  3. **Cap new cards per cycle:** Max 6 new briefing cards per update run (or per hour —
     see below). Prevents UI flood and limits LLM/GPU load. Pick the 6 events by e.g.
     highest severity, or most sources, or both (score = severity × log(source_count)).

  *Clustering approaches (choose one or combine):*
  - **A. LLM-based:** One lightweight LLM call: "Given these article titles/summaries,
    group them into distinct news events. Return event labels and article IDs per event."
    Accurate but adds latency and token cost per cycle.
  - **B. Entity/region keywords:** Extract primary region or entity from each article
    (country names, conflict names in title/summary). Cluster by (primary_region, primary_entity).
    E.g. Ukraine+Russia → one cluster, Iran+Israel → another, Pakistan+Afghanistan → another.
    Can use a simple keyword list or NER if available.
  - **C. Embedding similarity:** Embed title+summary, cluster by cosine similarity
    (e.g. sklearn or sentence-transformers). Events = clusters. No LLM for clustering;
    needs local embedding model or API.
  - **D. Topic + geography hybrid:** Use existing topic tags plus a small "region" tag
    (e.g. from keywords: Ukraine, Middle East, South Asia). Cluster by (primary_topic,
    region). Fewer clusters than raw topics, cleaner than geography alone.

  *Recommendation:* Start with B or D for no extra LLM cost; add A or C later for
  better separation of closely related events (e.g. two different Iran stories).

  *Config:* Add `max_briefings_per_cycle` (default 6). Optionally `max_briefings_per_hour`
  (e.g. 6) to cap total new cards per hour across multiple runs — requires counting
  briefings created in the last 60 minutes.

  **ASK USER:** Prefer cap per run (6 per scheduler cycle) or per hour (6 per hour total)?
  Per run is simpler; per hour avoids burst after downtime.

  *Interaction with threaded updates:* When we add story-update tracking, "update"
  detection is per-event: new articles that cluster into an existing event get appended
  as an update to that event’s card; only articles that form a NEW cluster create a
  new card (subject to the same cap).

  *Files:* `analysis/event_clustering.py` (new), `scraping/scheduler.py` (replace
  single `_do_generate_briefing` call with: cluster → for each cluster up to cap,
  generate one briefing), `storage/config.py` (max_briefings_per_cycle, optional
  max_briefings_per_hour), `storage/database.py` (optional: store event_id or
  cluster fingerprint on briefing for update matching).

- **Resource-aware deferral (skip local model when system is busy; generate later)**
  When the user is gaming, using the GPU heavily, or doing resource-heavy work, don’t
  load/use the local Ollama model for the current news run. Still run the scrape and
  save/aggregate articles; defer briefing generation until the system is idle again.
  **Only when provider is local (Ollama).** If provider is cloud API, ignore — no
  local resource impact.

  *Detection (local Ollama only):*
  - **GPU:** We already have `gpu_stats` (compute %, VRAM used). Thresholds: e.g. if
    compute > 70% for 2+ minutes, or VRAM used > 80% of total, treat as "busy".
  - **Optional:** Fullscreen app (game) detection via X11/Wayland (e.g. check active
    window or fullscreen state). More invasive; make it optional in settings.
  - **Optional:** CPU load or "idle time" from system (e.g. `/proc/loadavg`, or
    DBus/LoginManager idle). High load or low idle = defer.

  *Behavior:*
  1. Each scheduler cycle: run scrape + ingest as now (no GPU needed).
  2. Before calling the LLM for briefing generation: if local Ollama and "system busy"
     → skip generation this cycle. Store nothing extra; articles are already in DB.
  3. "Generate later": either (a) next cycle re-checks and runs generation if not busy,
     or (b) a separate idle check (e.g. every 5 min) that runs pending generation when
     busy flag clears. Option (a) is simpler (next cycle will pick up the same articles
     via get_recent_articles); no need for a "pending generation" queue unless we want
     to avoid re-clustering. Option (b) needs a "deferred_run" flag or queue so we don’t
     double-generate. Prefer (a) for v1: just skip this cycle; next cycle will see
     the same articles and generate then (possibly with more articles).
  4. Config: `defer_when_busy` (default true), optional thresholds in settings.

  *Model lifecycle — load on demand vs keep warm:*
  User asked: should the local model be loaded only when a briefing is being generated,
  then unloaded until next time?
  - **Load on demand:** Don’t preload the GeoPulse model at app startup. When we’re
    about to run briefing generation, we call the API; Ollama loads the model on first
    request. So model is only in VRAM during/after generation until something else
    evicts it or the user switches model.
  - **Unload after generation:** Ollama doesn’t have a formal "unload model" API; models
    stay in VRAM until replaced. To "free" VRAM we could: (1) do nothing — model stays
    loaded (current behavior), (2) trigger load of a tiny model to evict the big one
    (hacky), (3) if Ollama adds an unload endpoint, use it. For now, document: "load on
    demand" = we never explicitly preload; we just run generation when the scheduler
    says so, and Ollama loads as needed. After generation we don’t actively unload;
    the model may stay warm. That’s fine for "don’t load when user is gaming" because
    we’re not running generation when busy anyway.
  - **Verdict:** Yes, load-on-demand (no preload, run generation only when we’re about
    to create cards) is a good idea. It pairs with defer-when-busy: we only run
    generation when not busy, and we don’t load the model until that moment. No need
    to implement explicit "unload" unless Ollama gains support; the main win is
    deferring generation when the system is under load.

  *Files:* `gpu_stats.py` (already exists; add or use for busy check), new
  `analysis/system_load.py` or inline in scheduler (busy detection), `scraping/scheduler.py`
  (check busy before _do_generate_briefing; skip and continue if local + busy),
  `storage/config.py` (defer_when_busy, gpu_busy_threshold_pct, gpu_vram_busy_threshold_pct).

- **Story update tracking (threaded updates) — Option C**
When new articles arrive about a story that already has a briefing, DON'T create a new
briefing. Instead, append a timestamped update to the existing one.
*How it works:*

1. **Detection:** After ingesting new articles, compare each against existing briefings
  from the last 24h using fuzzy title matching (difflib, threshold ~0.6) and overlapping
   topic tags. If >60% match, it's an update to an existing story.
2. **DB schema:** Add `updates` column (JSON array) to briefings table. Each entry:
  `{"timestamp": "...", "new_articles": [...], "delta_summary": "...", "severity_change": 0}`
3. **LLM call:** When an update is detected, send a shorter prompt: "Given this original
  briefing and these new articles, what changed? Summarize the update in 2-3 paragraphs."
   Don't regenerate the whole briefing — just produce the delta.
4. **Briefing card:** Show an "UPDATED · 2 updates" badge on the sidebar card (new CSS
  class `briefing-update-badge`). Card stays in its original position but gets bumped
   to top of list on update.
5. **Briefing view:** Add an "Updates" section at the bottom (above the ask bar) with
  a timeline: each update has a timestamp header and the delta summary. Original analysis
   stays intact above.
6. **Notification:** Fire `notify-send` when: (a) severity increased, (b) more than 3
  new sources corroborate, or (c) a new actor/development appeared.
7. **Refresh of top summary:** Re-generate ONLY the top-line summary to reflect the
  latest state. The rest of the briefing (developments, context, actors) is preserved
   as the original analysis. Updates section has the new info.

*Files:* `storage/database.py` (schema + migration), `scraping/scheduler.py` (detection
logic), `analysis/briefing.py` (update prompt template), `ui/window.py` (badge),
`ui/briefing_view.py` (updates timeline), `ui/style.css` (badge styling)
**ASK USER:** Should the summary refresh be automatic or require user to click
"Refresh summary"? Auto is smoother but uses more GPU time.

- **News category tabs (Geopolitics, Tech, Local, Markets, Custom — each like its own program)**
  Sidebar tabs: **Geopolitics** (default), **AI & Tech**, **Local News**, **Markets**, **Other/Custom**.
  Tabs can be **enabled or disabled in settings** (e.g. only Geopolitics + Markets). Each tab is
  treated **essentially as a separate program**: its own sources, topics, and **own briefing
  schedule** (own sentinel interval, own briefing interval). Data is stored per category.
  **Cross-tab reference:** Where relevant, data from one tab can be brought into another
  when generating a brief (e.g. Markets data injected into a Geopolitics brief to show how
  markets reacted to an event; or a Tech tab brief that references a Geopolitics event).
  Relevance can be topic/entity overlap or explicit "include markets in geopolitics
  briefs" option. **Context window max** (see below) applies when assembling the prompt
  so we don't exceed the LLM limit when mixing articles + markets + cross-tab data.

  *Implementation:*
  1. `categories` table: id, name, icon, sort_order, enabled (default true).
  2. Sources and topics linked to categories. Briefings have category_id.
  3. Scheduler runs **separate cycles per category** (each category has its own timer or
     slot in a single loop). Per-category config: sentinel_interval, briefing_interval.
  4. When generating a brief for category C, optionally pull in **reference data** from
     other categories (e.g. latest markets snapshot for Geopolitics; latest geopolitics
     headlines for Markets). Cap total input size (context window max).
  5. Default categories: Geopolitics, AI & Technology, Local News, Markets. User can
     add/rename/remove and enable/disable in settings.
  *Files:* `storage/database.py`, `storage/config.py`, `data/sources.yaml`, `ui/window.py`,
  `ui/settings_dialog.py`, `scraping/scheduler.py`

- **Source manager in settings**
Full source browser with tier assignment (Tier 1: sentinel, Tier 2: context/analysis).
*Implementation:* New settings page tab. Show all sources from `data/sources.yaml` plus
user-added custom sources. Each row: name, URL, tier dropdown (1/2/3), category dropdown,
enabled toggle, health indicator (green/red dot). "Add Source" row at bottom with URL
entry + auto-detect (try RSS parsing the URL). Store custom sources in DB, merge with
built-in sources at runtime.
*Files:* `ui/settings_dialog.py`, `storage/database.py`, `scraping/fetchers.py`
- **Markets watcher (currencies, commodities, indices, single names — feed into briefs)**
  A **Markets** tab and data pipeline for geopolitically relevant market data. **Data to
  fetch and store:** (1) **Currencies** — major pairs (e.g. USD/EUR, USD/JPY, USD/CNY,
  RUB, etc.). (2) **Commodities / raw materials** — oil (Brent, WTI), gas, key metals
  (e.g. copper, nickel). (3) **Indices** — S&P 500, tech-heavy indices, regional indices
  as relevant. (4) **Single names** — tech companies individually, other relevant sectors;
  collections (e.g. "big tech" basket). Data is **calculated/stored** (e.g. daily or
  intraday snapshots with open/close/change); historical series so we can show "how
  markets have responded" over time. **Goal:** Bring attention to how markets have
  responded to events. When generating a brief (especially Geopolitics or Markets tab),
  **inject this data into the mix** where applicable: e.g. "Oil up 3% since X; S&P
  sector Y down." Markets data is **separate** (own storage, own fetch schedule) but
  **where relevant**, historical and current data is included in the brief-generation
  prompt so the LLM can reference it. Markets tab has its own briefing schedule (own
  "program"); those briefs focus on market moves and can reference news from other tabs.
  *Data sources:* Free/freemium APIs (e.g. Yahoo Finance, Alpha Vantage, or similar) or
  scraped summary pages; avoid heavy or paid APIs unless necessary. Store in DB (e.g.
  `market_snapshots` table: symbol, timestamp, open, high, low, close, volume, change_pct).
  *Files:* New `scraping/markets.py` or `data/markets.py`, `storage/database.py`,
  `analysis/briefing.py` (prompt builder includes optional markets snippet), `scraping/scheduler.py`
  (markets fetch job + per-category brief gen that can pull in markets).
- **Context window max (cap prompt size for brief generation)**
  When building the prompt for brief generation we may include: many articles, markets
  data, cross-tab reference data, and (later) historical context. **Cap total input**
  so we don't exceed the model's context window (e.g. 8k–32k tokens depending on
  model). Implementation: (1) Config or constant `max_briefing_context_tokens` (or
  max chars, then approximate tokens). (2) When assembling the prompt (articles +
  optional markets + optional cross-tab snippet), truncate or summarize: e.g. take
  most recent/relevant articles up to a token budget, then append a short "markets
  snapshot" and "cross-tab highlights" if enabled. (3) If over limit, drop oldest
  articles or shorten article text (e.g. title + first N chars of summary only).
  Prevents API errors and unstable output for long context.
  *Files:* `storage/config.py`, `analysis/briefing.py` (prompt assembly), optionally
  a small `analysis/context_budget.py` helper.
- **"Go deeper" regeneration button**
Replace the header bar depth dropdown. In the briefing view, replace "Read full analysis..."
with a "Go Deeper" button that re-generates the briefing with extended depth.
*Implementation:*

1. Remove depth dropdown from `_build_ui()` in window.py.
2. Add `Adw.ComboRow` for default depth in settings AI Engine page.
3. In `briefing_view.py`, replace the `read_more_btn` with a "Go Deeper" button.
  On click: (a) show spinner, (b) fetch the original articles by `article_ids`,
   (c) re-run `generate_briefing()` with depth="extended", (d) update the briefing
   in DB, (e) reload the view.
4. The original "brief" content is replaced. If user wants to preserve history,
  combine with threaded updates (store the original as an "initial analysis" entry).

*Files:* `ui/window.py`, `ui/briefing_view.py`, `ui/settings_dialog.py`,
`scraping/scheduler.py` (needs a `regenerate_briefing(briefing_id, depth)` method)

- **Remote Ollama connection**
Allow connecting to an Ollama instance on another machine (LAN or remote).
*Implementation:* The code already supports arbitrary `base_url` in config. Just need:
(1) Add a URL entry row in Settings > AI Engine for Ollama URL (default localhost:11434).
(2) Add a "Test Connection" button next to it. (3) Update AI indicator to show
"Remote" label when URL is not localhost. (4) Validate on save.
*Note:* This is mostly UI work. The `OllamaManager`, `OllamaProvider`, and `create_provider`
all already use `base_url` from config.
*Files:* `ui/settings_dialog.py`, `storage/config.py`
- **Export briefings**
Save/share as markdown, PDF, or plain text. Copy to clipboard.
*Implementation:* Add export button (or menu) to briefing_view.py header area.
Markdown is trivial (format fields into md). Plain text: strip formatting. PDF: use
`weasyprint` or `reportlab`. Clipboard: `Gdk.Clipboard`.
*Files:* `ui/briefing_view.py`, new `export.py`
- **"Where can I follow this closely?" suggested question**
  Add a fixed suggested-question button (or option) on each briefing: **"Where can I
  follow this closely?"** When the user clicks it, the app suggests live streams,
  creators, X (Twitter) accounts, journalists, and similar sources that are reporting
  on the story. Implementation options: (A) **Chat-based:** Always show this button
  alongside LLM-generated suggested questions; on click, start chat with that exact
  question. Enrich the chat system prompt so that when the user asks where to follow
  the story, the model responds with concrete suggestions: live streams (e.g. YouTube,
  Twitch), X handles, YouTube channels, journalists or creators covering the topic.
  (B) **Structured in briefing:** Add a <<<FOLLOW>>> section to the briefing template
  so the LLM outputs a short list of follow sources (X accounts, streams, channels)
  at generation time; display as a "Follow this story" block with clickable links/handles.
  Option A is simpler (no prompt/schema change); option B gives a consistent block on
  every briefing. Can combine: fixed button opens chat with the question; optionally
  also ask the LLM for <<<FOLLOW>>> at brief gen time and show that block.
  *Files:* `ui/briefing_view.py` (add button), `ui/chat_view.py` (system prompt tweak
  when question is "where can I follow" or similar), optionally `analysis/briefing.py`
  (<<<FOLLOW>>> in template and parse_briefing_response).
- **Expert commentary (on demand): YouTube transcripts**
  When the user asks for "expert commentary" or similar, pull in YouTube video
  transcriptions (e.g. William Spaniel, Peter Zeihan, CFR, Chatham House, university
  lectures) as additional sources. Add source type `youtube_channel` / `youtube_playlist`:
  discover new videos via YouTube Data API or channel RSS, fetch transcript via
  `youtube-transcript-api` (or equivalent), normalize to article format (title, full_text
  = transcript, source_name = channel, url = video link). Run through same pipeline so
  the briefing can cite e.g. "William Spaniel, Game Theory 101, [video title]".
  Only used when user explicitly requests expert/deeper commentary. Respect YouTube
  ToS and rate limits; transcripts not always available.
  *Files:* `data/sources.yaml` (source type), `scraping/fetchers.py` (YouTube fetcher),
  `storage/database.py` (if needed for source type), briefing prompt logic to include
  expert sources when requested.
- **Expert commentary (on demand): think tanks, podcasts, historical context**
  When the user asks for "expert commentary", optionally pull in: (1) think tank
  reports/briefs (CFR, Chatham House, RAND, Brookings, Carnegie, Wilson Center —
  RSS or scrape), (2) podcasts with transcripts (War on the Rocks, Lawfare, Rational
  Security, etc.), (3) historical context via RAG over Wikipedia/Britannica or
  curated history briefs per region/topic. Label these as "expert" sources so the
  briefing can highlight or prefer them when generating. No dedicated "history AI"
  — use the same model with retrieved historical snippets injected into the prompt.
  Only used when user explicitly requests expert commentary.
  *Files:* `scraping/fetchers.py` (think tank / podcast sources), optional
  `analysis/retrieval.py` (RAG for history), `data/sources.yaml`, briefing prompt
  and config flag for "include expert/history sources".
- **Add a political leaning feature.** Much like blind spot for ground.news. If a user selects they are` leaning left (add scale?) then generate logical articles that also lean towards explaining consequenses, especially in relation to history and to established law. Ovmerride their leanings. - for right leaning, generate unbiasedly.
- **Scheduled brief at a set time (e.g. after lunch, morning brief)**
  User can set one or more times per day when a briefing should be ready (e.g. 13:00 for
  after lunch, 08:00 for morning). **Morning brief:** pull and clean data overnight (or in
  the hours before the set time); run `generate_briefing` so a latest-news brief is ready
  at that time. Same for "after lunch" — have a fresh brief ready at 13:00. Implementation:
  store preferred times in config (e.g. `scheduled_brief_times: ["08:00", "13:00"]`). In
  the scheduler, besides interval-based generation, check wall-clock: if we're within a
  window of a scheduled time and we haven't generated for that slot today, run a pull
  (if needed) + generate and mark that slot done. Use the same "pull, clean, keep" data
  so the brief is based on the latest cleaned content.
  *Files:* `storage/config.py`, `scraping/scheduler.py`, `ui/settings_dialog.py`
- **Do Not Disturb (DND)**
  User can define one or more time ranges (A–B) and add them to a list. During those
  times: (1) **no desktop notifications** (don't call notify-send), (2) **optional: no
  briefing generation** (skip _do_generate_briefing in the scheduler when current time
  falls inside any DND window). Scraping/pull can still run so data is ready when DND
  ends. Config: `do_not_disturb: { ranges: [["22:00", "07:00"], ["12:00", "13:00"]], skip_generation: true }`.
  Ranges are in local time; support overnight (e.g. 22:00–07:00). Settings UI: list of
  time-range rows (start time, end time), "Add" button, remove per row; toggle "Don't
  generate briefings during DND" (default true).
  *Files:* `storage/config.py`, `scraping/scheduler.py` (check current time before
  notify and before generation), `ui/settings_dialog.py` (Schedule or new DND section)
- **"What did I miss" morning digest**
  Consolidate overnight briefings into a single summary on app open. **Tie to scheduled
  morning brief:** overnight pull/clean + one generate_briefing run so a morning brief is
  ready at the user's set time (e.g. 08:00). On app activate, if >6 hours since last use,
  can also show a digest card of what was created in that window.
  *Implementation:* On app activate, check time since last user interaction. If >6 hours,
  gather all briefings created since then and generate a digest summary via LLM.
  Show as a special "digest" briefing card at the top.
  *Files:* `ui/window.py`, `analysis/briefing.py` (digest prompt template)
- **AI-powered triage**
Replace keyword-based `score_severity` with a lightweight LLM call.
*Implementation:* Send article title + summary to the LLM with a triage-only prompt
(one-shot, expecting just a number 1-5). Use a tiny/fast model for this. Fall back to
keyword scoring if LLM is unavailable.
**ASK USER:** This means every article gets an LLM call at ingest time. Could be 50+
calls per cycle. Worth the GPU time? Or only for articles that keyword-score >= 2?
*Files:* `analysis/triage.py`, `scraping/scheduler.py`
- **Map visualization**
Geopolitical news is geographic. Region highlight on briefings.
*Implementation:* Simplest approach: a static SVG world map with regions colorable via
CSS classes. Extract region/country from articles (LLM or keyword). Highlight relevant
regions on the briefing view. Could use a `Gtk.Picture` with a dynamically colored SVG.
*Files:* `ui/briefing_view.py`, new `data/world_map.svg`
- **Confidence calibration**
Track AI severity predictions vs actual developments over time.
*Implementation:* Long-term feature. Store predictions, let user rate accuracy
retrospectively. Build a calibration curve over weeks of data.
*Files:* `storage/database.py`, new `analysis/calibration.py`
- **JavaScript-rendered scraping**
Many modern news sites need JS to render content.
*Implementation:* Integrate Playwright as an optional scraper backend. Use it only for
sources flagged as `needs_js: true` in sources.yaml. Fall back to requests+BS4 if
Playwright not installed.
**ASK USER:** Playwright is a heavy dependency (~150MB). Make it optional (extras_require)?
*Files:* `scraping/fetchers.py`, `data/sources.yaml`, `requirements.txt`
- **Briefing history search**
Full-text search across past briefings.
*Implementation:* SQLite FTS5 virtual table mirroring briefings content. Rebuild index
on insert. Add search bar to sidebar. Results shown as filtered briefing list.
*Files:* `storage/database.py`, `ui/window.py`
- **Desktop notifications with actions**
Click notification to open the specific briefing.
*Implementation:* Pass `--action` to notify-send or use GIO notification API
(`Gio.Notification`) which supports actions natively with `Gio.Application`.
On action, launch app with `--briefing <ID>` (already supported in CLI args).
*Files:* `scraping/scheduler.py`, `ui/app.py`

---

## Architecture — Backend API Extraction

This is the key architectural step that unlocks cross-platform apps, remote access, and mobile.
Do this AFTER the core features above are stable.

- **Extract Python backend into a local REST API** (FastAPI)
*Implementation:*

1. New `api/` package with FastAPI app.
2. Endpoints: `GET/POST /briefings`, `GET /articles`, `POST /chat`, `GET/PUT /config`,
  `GET /status` (scheduler state, model info, GPU stats), `GET /models`.
3. WebSocket `/ws/events` for real-time push: new briefing, status change, update badge.
4. The GTK4 app talks to this API instead of importing storage/scraping directly.
5. `main.py` gains a `--serve` flag to run headless (API only, no GUI).
6. For backwards compat, the GTK app can still import directly if API isn't running
  (single-process mode).

*Files:* new `api/` package, `main.py`, refactor `ui/window.py` to use API client

- **Authentication for remote access**
Token-based auth when the API is exposed beyond localhost.
*Implementation:* Generate a random token on first run, store in config. API checks
`Authorization: Bearer <token>` header. Settings shows the token for copying to
remote clients. Optional: mTLS for serious deployments.
*Files:* `api/auth.py`, `storage/config.py`

---

## Platform Expansion (Paid)

**V2 desktop targets:** Windows and macOS (Tauri app) are in **V2 scope** above; mobile and cloud are later.

Strategy: Linux stays free (GTK4, open source). Other platforms get native paid apps
sharing the same Python backend API.

- **Tauri desktop app (Windows + macOS)**
Rust shell + Svelte/React web UI. Native window chrome, system tray, auto-updates.
Single codebase covers both platforms. Talks to the Python backend API (bundled or remote).
Distribute via website + potentially Microsoft Store / Mac App Store.
Charges: one-time purchase ($15-25 range) or yearly license.
*Note:* The Python backend can be bundled as a sidecar process via PyInstaller/Nuitka.
Tauri has built-in sidecar support.
- **Mobile app (iOS + Android)**
Flutter or React Native. Connects to a GeoPulse server running on user's home machine
(or future hosted service). Push notifications for breaking briefings.
Subscription model ($3-5/month).
*Note:* Requires the backend API extraction to be complete first. The mobile app is
a thin client — all scraping and LLM work happens on the server.
- **GeoPulse Cloud (future SaaS)**
Hosted scraping + API-based LLM analysis. No local setup required.
Free tier (limited briefings/day) + paid tier (unlimited, priority).
This is the long-term monetization play.

---

## Licensing

**Decision: all GPL-3. Single repo. Packaged binaries (Linux, Windows, macOS) can be sold.**

- Entire project (core, backend, Linux GTK client, and future Windows/macOS Tauri client) is **GPLv3**.
- One public repo; no separate closed or commercial repo for paid platforms.
- “Paid” = sold binaries and optional support; buyers receive the same GPLv3 code (e.g. via repo link). Selling is permitted under GPL.
- Keeps it open source, builds community; copyleft prevents others from closing your work.
- Cloud / hosted service remains a separate potential upsell (same license for the code they run).


# GeoPulse — Implementation order and v1 scope

This document defines what we build first and in what order, so the app stays shippable and we don’t do too much at once. It aligns with the principles in the main TODO (resource-effective, stable, no crashes) and with vibe coding (you’re product owner; we build in stages you can see and react to).

---

## Phase 0: Decisions first (no code)

Several items in the TODO are marked **ASK USER**. Resolving these now avoids rework later.

| **Article dedup** | Ingest-time vs generation-time | **Ingest-time.** Pipeline: (1) Pull raw data for the run; (2) process documents one-by-one to clean and drop irrelevant; (3) after all cleaned, dedup. Same facts/opinions → keep one. If facts or opinions differ across sources → keep/note both and briefing states “opinions differ” / “facts not entirely clear” / “differ from sources”; this affects Reliability score. Many small runs OK; batch = pull all for run, then batch process docs one by one (separated). |
| **Cap new briefings** | Per run vs per hour; default count | **Per run.** Max **5** new briefings per run (configurable in Settings). |
| **Tags on cards** | Show all vs 1 row + tooltip | **Config option:** “Show all tags” (wrap/flow) **or** “1 row + all on mouseover” (default). User prefers visible tags; OK with mouseover for “all”. |
| **Model validation** | Soft warn vs hard block | **Database of known-good / known-bad models.** If a known-bad model is loaded → top-left indicator **red** + visible note: “Current model will not work; please select another” (or similar). |
| **Summary refresh on update** | Auto vs manual | **Automatic** on update. Button can be added later. |

**Locked in as above** (user confirmed).

---

## What to rework or drop for v1

- **Nothing removed from the TODO** — the full roadmap stays. The list below is “v1” vs “v2/later” so we know what to implement first.
- **Defer to v2 (after v1 is stable and shipped):**
  - News category **tabs** (Geopolitics, Tech, Local, Markets, Custom) — big schema and scheduler change.
  - **Markets watcher** — depends on tabs and new data pipeline.
  - **Context window max** — most urgent when we have tabs + markets mixing data; can add a simple cap in v1 if we hit limits.
  - **Story update tracking** (threaded updates) — do after event-based briefings.
  - **Resource-aware deferral** (skip generation when GPU busy) — nice to have.
  - **Expert commentary** (YouTube, think tanks, history) — v2.
  - **Political leaning**, **map visualization**, **confidence calibration**, **JavaScript scraping**, **briefing search**, **notifications with actions** — v2.
  - **Backend API extraction**, **platform expansion** — later.

- **Clarification (no rework):** “Parsing and scraping efficiency” (one-at-a-time) and “Parallel scraping” can coexist: **parallel across sources** (e.g. 4 workers), **one-at-a-time processing per article** (fetch → clean → store → next) so we don’t hold many full HTML docs in memory. Rate limiting per domain stays.

---

## Version 1 scope (must-have for a stable, portfolio-ready app)

Goal: **Stable, efficient, single-category app** with reliable sources, robust parsing, bounded data, and a few high-value UX improvements. No tabs, no markets yet.

**In scope for v1:**

1. **Stability and data safety**
   - Database migration framework (schema version, numbered migrations).
   - Robust LLM prompt parsing (fallback chain so bad model output doesn’t leave empty briefs).
   - Data retention (keep last 30 briefings default, article retention days, cleanup, optional max MB).
   - Optional: minimal automated tests (migrations, parser).

2. **Reliability**
   - Fix source reliability (more sources, retry with backoff, skip after 5 failures).
   - Anti-spam: don’t hammer sites (rate limit + sensible intervals).

3. **UX (small, high impact)**
   - Move **depth** to Settings; replace header depth dropdown with **“Go deeper”** button in briefing view (re-generate with extended depth).
   - **Remote Ollama** URL in Settings (field + test connection).
   - **Briefing card actions** (right-click or menu): Regenerate, Go deeper, Delete, Mark unread.
   - **Tags** fully visible (wrapping or flow so they’re not clipped).

4. **Larger v1 features (both)**
   - **A) Event-based briefing** — One card per event (cluster articles by event, one brief per cluster, cap 5 per cycle; configurable).
   - **B) Scheduled brief + DND**
     - Brief ready time: aim to start scraping last data a few minutes before generation (no need to be exact).
     - **DND** (all options on by default when DND is on): no notify, no cleanup generation, no briefing generation. After DND off, next batch can be larger; **+1 extra briefing card per 2 hours** without a run (so you don’t miss news). Extra cards apply to scheduled briefs (morning digest, after lunch, afternoon batch).

**Locked in:** Both A and B for v1; Step 10 will implement A then B.

---

## Order of operations (v1)

Execute in this order so each step builds on the last and we can test as we go.

**Priority:** Get **source reliability** (Step 4) in good shape early — good data before more prompt work. Use **SOURCES.md** (in `sources/`, uppercase filenames) to track which sources work, rank them, and decide what to enable; then implement retry + skip-after-fail in code.

**Actual execution so far:** Step **4** (source reliability), **1** (migration framework), **2** (LLM prompt parsing), **3** (data retention), **5** (depth in Settings + “Go deeper”), **6** (Remote Ollama URL + Appearance + theme + briefing font/size + sound on briefing), **7** (briefing card context menu), **8** (tags visible).

| Step | What | Why first |
|------|------|------------|
| **1** | Database migration framework | Prevents future schema breakage; required before any new schema (e.g. retention, updates). **Done:** `schema_info` table, `CURRENT_SCHEMA_VERSION`, numbered `_MIGRATIONS` list; `get_schema_version()` for tests. |
| **2** | Robust LLM prompt parsing | Stops empty briefs when the model misbehaves. **Done:** Marker-based extraction; strip code fences; fallback chain (headline/summary/developments from first line, article titles/summaries); `validate_briefing()` raises if headline still empty so we don’t save or mark articles used; `_parse_json_list` tries JSON → bullet lines → quoted strings; providers always return `str`. **Note:** For consistent event/story classification we may later recommend or support a single “GeoPulse” model; different models can disagree on whether stories are the same event. |
| **3** | Data retention (max briefings 30, article_days, cleanup) | Bounds storage; Settings UI for retention. **Done:** `retention.max_briefings` (default 30) and `retention.article_retention_days` (default 14) in config; **Data** page in Settings with spin rows; `run_retention_cleanup()` removes oldest briefings (+ conversations) and articles older than N days; runs on startup and after each new briefing. |
| **4** | Fix source reliability (sources + retry + skip after 5 fails) | More sources working = more value; retry avoids transient failures. **Track status in SOURCES.md** (working/broken/untested, rank, use). |
| **5** | Depth in Settings + “Go deeper” button | You asked for it; removes header clutter, adds clear action. |
| **6** | Remote Ollama URL in Settings | Small change, high value for your setup. **Done:** URL entry + Test connection in Settings > AI Engine > Ollama; window and settings use `Config.llm().base_url` for OllamaManager. |
| **7** | Briefing card context menu (Regenerate, Go deeper, Delete, Mark unread) | Makes each card actionable. **Done:** Right-click on any briefing row opens Gtk.PopoverMenu with Regenerate, Go deeper, Mark unread, Delete. Regenerate uses current depth from config; Go deeper uses extended; Delete removes briefing + conversations; Mark unread sets is_read=0. |
| **8** | Tags visible (wrap or flow) | Finishes the card UX you asked for. **Done:** Topic tags on sidebar cards use Gtk.FlowBox so all tags wrap/flow; no more “+N” truncation. |
| **9** | Optional: minimal tests (migrations, parser) | Locks in stability before adding more features. |
| **10** | **Both:** event-based briefing **then** scheduled brief + DND (see v1 scope point 4) | Event-based improves content; scheduled + DND + “+1 card per 2h” improves routine and catch-up. |

After **10**, we have a solid v1. Then we can add story updates, then tabs + markets in v2.

**Adding a new migration:** In `storage/database.py`, add a function `_migration_N(conn)` that performs the schema change, then append `(N, _migration_N)` to `_MIGRATIONS` and set `CURRENT_SCHEMA_VERSION = N`. Run migrations only in `_run_migrations`; keep each migration idempotent where possible (e.g. ADD COLUMN in try/except).

---

## Phase 0 and v1 choices (locked in)

- **Dedup:** Ingest-time; clean first, then dedup; differing facts/opinions → note in brief and affect Reliability.
- **Cap:** 5 per run, configurable in Settings.
- **Tags:** Config option — show all or 1 row + mouseover.
- **Model validation:** DB of models; known-bad → red indicator + visible note.
- **Summary refresh:** Auto; button later.
- **Step 10:** Both A (event-based) and B (scheduled + DND); B includes +1 briefing per 2h gap for scheduled runs.

---

## What I need from you

1. **Phase 0:** Confirm or change the five recommendations (dedup, cap, tags, model warn, summary refresh).
2. **v1 feature choice:** For step 10, choose **A** (event-based), **B** (scheduled + DND), **both** (A then B), or **neither** for v1.
3. **Optional:** Any item in “v1 scope” you want to drop from v1, or any “v2” item you want in v1?

Once you answer, we can start with **Step 1 (migration framework)** and proceed in order, testing at each step and checking in at the decision points above.

*Phase 0 and v1 choices are now recorded above; no further answers needed to proceed with Step 1.*

# GeoPulse – Application flow

This document describes how GeoPulse works end-to-end: entry points, GUI structure, the background scheduler, briefing generation, and data flow.

---

## Table of contents

1. [Entry points and modes](#1-entry-points-and-modes)
2. [GUI startup and main window](#2-gui-startup-and-main-window)
3. [Main UI structure](#3-main-ui-structure)
4. [Scheduler (background)](#4-scheduler-background)
5. [Briefing generation and LLM](#5-briefing-generation-and-llm)
6. [User actions](#6-user-actions)
7. [Data and config](#7-data-and-config)

---

## 1. Entry points and modes

`main.py` parses CLI arguments and either runs a one-off command or launches the GTK GUI.

```mermaid
flowchart TB
    subgraph entry["main.py"]
        CLI[Parse args]
        CLI --> Fetch[--fetch]
        CLI --> Gen[--generate]
        CLI --> List[--list]
        CLI --> GUI[Launch GUI]
    end

    Fetch --> EnsureDirs[ensure_dirs + init_db]
    EnsureDirs --> RunIngest[run_one_ingestion]
    RunIngest --> Done1[Print count & exit]

    Gen --> EnsureDirs2[ensure_dirs + init_db]
    EnsureDirs2 --> GetArts[get_recent_articles]
    GetArts --> CreateProv[create_provider]
    CreateProv --> GenBrief[generate_briefing]
    GenBrief --> InsertB[insert_briefing + mark_articles_used]
    InsertB --> Retain[run_retention_cleanup]

    List --> EnsureDirs3[ensure_dirs + init_db]
    List --> GetBriefs[get_briefings]
    GetBriefs --> PrintList[Print table & exit]

    GUI --> Gtk[Load GTK4/Adw]
    Gtk --> App[GeoPulseApp]
    App --> Activate[activate]
    Activate --> Window[GeoPulseWindow]
```

- **`--fetch`**: One ingestion cycle (tiered fetch, store new articles), then exit.
- **`--generate`**: Build one briefing from recent articles via LLM, save to DB, run retention cleanup, then exit.
- **`--list`**: Print a table of recent briefings and exit.
- **No args (or `--briefing ID`)**: Start the GTK app; optionally open a specific briefing.

---

## 2. GUI startup and main window

When the GUI launches, `GeoPulseApp` handles `activate` and creates a single `GeoPulseWindow`. The window initializes the DB, runs retention cleanup, seeds default topics, and builds the UI.

```mermaid
flowchart TB
    subgraph window["GeoPulseWindow __init__"]
        EnsureDirs[ensure_dirs]
        InitDB[init_db]
        Retain[run_retention_cleanup]
        Seed[seed_default_topics]
        BuildUI[_build_ui]
        BuildMenu[_build_briefing_context_menu]
    end

    EnsureDirs --> InitDB --> Retain --> Seed --> BuildUI --> BuildMenu

    subgraph first_run["First run?"]
        First{is_first_run?}
        First -->|Yes| Welcome[Show WelcomeView]
        First -->|No| Main[Show main view]
    end

    BuildUI --> First
    Main --> LoadBrief[_load_briefings]
    Main --> StartSched[_start_scheduler]
```

- **First run**: Shows `WelcomeView` (Ollama check, model selection). On completion, switches to main view and starts the scheduler.
- **Later runs**: Show main view immediately, load briefing list, start scheduler and optional Ollama auto-start.

---

## 3. Main UI structure

The main view is a horizontal paned layout: sidebar (briefing list) + content stack.

```mermaid
flowchart LR
    subgraph root["Root stack"]
        Welcome[WelcomeView]
        Main[Main view]
    end

    subgraph main["Main view (Paned)"]
        Sidebar[Sidebar]
        Content[Content stack]
    end

    subgraph sidebar["Sidebar"]
        Header[BRIEFINGS header + unread badge]
        List[Briefing list - ListBox of BriefingRow]
        Status[Status bar - spinner + status label]
    end

    subgraph content["Content stack"]
        Quiet[QuietView - search / empty state]
        Briefing[BriefingDetailView]
        Chat[ChatView - Q&A with LLM]
    end

    root --> Welcome
    root --> main
    Sidebar --> Header
    Header --> List
    List --> Status
    Content --> Quiet
    Content --> Briefing
    Content --> Chat
```

- **Sidebar**: List of briefings (main cards and update sub-cards), severity bar, meta, headline, topic tags. Right-click context menu: Regenerate, Go deeper, Mark unread, Email, Delete.
- **QuietView**: Shown when no briefing is selected or list is empty; offers search.
- **BriefingDetailView**: Headline, summary, developments, context, actors, outlook, watch list, source chips, suggested questions, Ask bar.
- **ChatView**: Conversation for the current briefing; streamed LLM answers.

---

## 4. Scheduler (background)

`SmartScheduler` runs in the background once the main view is shown. It uses timers for sentinel checks and scheduled briefings, and optionally a morning briefing at a fixed time.

```mermaid
flowchart TB
    subgraph start["SmartScheduler.start()"]
        SentTimer[Sentinel timer - every sentinel_interval_min]
        BriefTimer[Briefing timer - every briefing_interval_min]
        MornTimer[Morning timer - optional fixed time]
    end

    SentTimer --> SentinelCycle["_sentinel_cycle()"]
    BriefTimer --> ScheduledBrief["_run_scheduled_briefing()"]
    MornTimer --> MorningBrief["_run_morning_briefing()"]
```

### Sentinel cycle (tiered ingestion)

Sentinel runs on an interval (e.g. every 15 minutes). It fetches **tier 1** (sentinel) sources first. Depending on severity of new articles, it may fetch **tier 2** and **tier 3** and/or generate a **breaking** briefing immediately.

```mermaid
flowchart TB
    subgraph sentinel["_sentinel_cycle()"]
        CheckTier[Can run tier 1?]
        CheckTier --> SetTime[set_source_check_time 1]
        SetTime --> FetchT1[fetch_sources_by_tier 1]
        FetchT1 --> Store1[insert_article for new]
        Store1 --> NewAny{New articles?}
        NewAny -->|No| StatusQuiet[on_status: All quiet]
        NewAny -->|Yes| MaxSev{Max severity}
        MaxSev -->|Low/Moderate| FetchT2[Fetch tier 2]
        MaxSev -->|Breaking 4-5| FetchT2
        MaxSev -->|Breaking 4-5| FetchT3[Fetch tier 3]
        MaxSev -->|Breaking 4-5| BreakBrief[generate_briefing - breaking]
        FetchT2 --> Store2[Store tier 2 articles]
        FetchT3 --> Store3[Store tier 3 articles]
        BreakBrief --> InsertB[insert_briefing]
        InsertB --> OnBrief[on_briefing id]
        Store2 --> ScheduleNext[_schedule_sentinel]
    end
```

### Scheduled briefing

On a timer (e.g. every 60 minutes), the scheduler fetches recent articles and runs a **novelty check** (LLM decides SKIP, NEW, or UPDATE &lt;id&gt;). It then either skips, generates a full briefing, or generates an update card linked to an existing briefing.

```mermaid
flowchart TB
    subgraph sched_brief["_run_scheduled_briefing()"]
        FetchRecent[get_recent_articles]
        FetchRecent --> Novelty[check_novelty - LLM: SKIP | NEW | UPDATE id]
        Novelty -->|SKIP| Done[on_status, schedule next]
        Novelty -->|NEW| FullBrief[generate_briefing]
        Novelty -->|UPDATE id| UpdBrief[generate_update_briefing]
        FullBrief --> InsertFull[insert_briefing]
        UpdBrief --> InsertUpd[insert_briefing - parent_briefing_id set]
        InsertFull --> MarkUsed[mark_articles_used]
        InsertUpd --> MarkUsed
        MarkUsed --> Retain[run_retention_cleanup]
        Retain --> OnBrief2[on_briefing]
        OnBrief2 --> OnRefresh[on_refresh]
    end
```

---

## 5. Briefing generation and LLM

Full briefings are produced in `analysis/briefing.py` by calling the configured LLM provider with a system prompt and a template that includes articles and depth instructions.

```mermaid
flowchart TB
    subgraph gen["generate_briefing()"]
        Depth[Resolve depth: brief | extended]
        Format[format_articles_for_prompt]
        Template[get_prompt briefing_template + depth instructions]
        SysPrompt[get_prompt system_prompt]
        Chat[provider.chat - system + user messages]
        Parse[parse_briefing_response - <<<MARKERS>>>]
        Fallback[apply_parsing_fallbacks]
        Validate[validate_briefing]
        Topics[Add article_ids, topics]
    end

    Depth --> Format
    Format --> Template
    SysPrompt --> Chat
    Template --> Chat
    Chat --> Parse --> Fallback --> Validate --> Topics
```

- **Depth**: From config (brief vs extended); controls instruction length for summary, developments, context, actors, outlook.
- **Parsing**: Model output is expected to use markers like `<<<SEVERITY>>>`, `<<<HEADLINE>>>`, etc.; `parse_briefing_response` extracts sections; fallbacks fill missing fields from articles or raw text.
- **Provider**: Chosen from config (`Config.llm()`); one of Ollama, OpenAI-compatible, or Anthropic.

```mermaid
flowchart LR
    subgraph provider["create_provider()"]
        Cfg[Config.llm]
        Cfg --> Ollama[OllamaProvider]
        Cfg --> OpenAI[OpenAIProvider]
        Cfg --> Anthropic[AnthropicProvider]
    end
```

---

## 6. User actions

Actions are handled in `GeoPulseWindow` and wired to the sidebar, content views, and context menu.

```mermaid
flowchart TB
    subgraph actions["User actions"]
        Select[Select briefing row]
        Refresh[Refresh button]
        Search[Search / QuietView]
        ChatBtn[Ask / suggested Q]
        Context[Context menu]
    end

    Select --> GetBrief[db.get_briefing]
    GetBrief --> BriefView[BriefingDetailView.load_briefing]
    BriefView --> MarkRead[db.mark_briefing_read]

    Refresh --> SchedRefresh[scheduler.refresh_now]
    Search --> SchedSearch[scheduler.search_now]

    ChatBtn --> RunFollowUp[_run_follow_up]
    RunFollowUp --> Conv[get/create conversation]
    Conv --> ProviderStream[provider.stream_chat]
    ProviderStream --> AppendMsg[db.append_message]
    AppendMsg --> ChatView[ChatView updates]

    Context --> Regenerate[_on_regenerate_briefing]
    Context --> GoDeeper[_on_go_deeper]
    Context --> Email[_on_email_briefing]
    Context --> Delete[db.delete_briefing]
    Context --> MarkUnread[db.mark_briefing_unread]

    Regenerate --> GenBrief[generate_briefing - config depth]
    GoDeeper --> GenBriefDeep[generate_briefing - depth=extended]
    GenBrief --> UpdateBrief[db.update_briefing]
    GenBriefDeep --> UpdateBrief
```

- **Select row**: Load briefing into detail view, mark as read.
- **Refresh**: Triggers scheduler’s immediate fetch/refresh.
- **Search**: Triggers scheduler search (e.g. Google News), then normal flow.
- **Ask / suggested Q**: Starts or continues a conversation for the current briefing; streams LLM response and appends to DB.
- **Context menu**: Regenerate (same depth), Go deeper (extended depth), Email (mailto or SMTP), Delete briefing, Mark unread.

---

## 7. Data and config

Storage and configuration are under `storage/`; scraping and analysis under `scraping/` and `analysis/`.

```mermaid
flowchart LR
    subgraph storage["storage/"]
        DB[(SQLite: articles, briefings, conversations, user_topics, source_check_log, scheduler_state)]
        Config[config - JSON file]
    end

    subgraph scraping["scraping/"]
        Fetchers[fetchers - RSS, scrape, Google News]
        Scheduler[SmartScheduler]
    end

    subgraph analysis["analysis/"]
        Triage[score_severity, match_topics, enrich_article]
        BriefingMod[generate_briefing, check_novelty, generate_update_briefing]
    end

    Scheduler --> Fetchers
    Fetchers --> DB
    Scheduler --> Triage
    Scheduler --> BriefingMod
    BriefingMod --> DB
    Config --> Scheduler
    Config --> BriefingMod
    Config --> Window[Window / Settings]
    Window --> DB
```

- **SQLite**: Articles (from feeds/scrape), briefings (with optional `parent_briefing_id` for update cards), conversations (per-briefing Q&A), user topics, source-check throttle times, scheduler state (e.g. last morning briefing date).
- **Config**: LLM provider/model, schedule intervals, retention limits, appearance, email, prompts; used by window, scheduler, and briefing generation.

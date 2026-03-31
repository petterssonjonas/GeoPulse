# data/context/

Persistent background context files for GeoPulse's AI session.

These are **not news**. They are slow-changing analytical background documents: historical primers, conceptual frameworks, analyst perspectives, and structural context. They are loaded as background RAG context when generating briefings and answering Q&A.

## How they are used

1. Files here are read at session start (or on demand) and fed to the AI as background context alongside the current briefing articles.
2. Long-form external content (YouTube transcripts, podcast transcripts, full-text essays) fetched from the web is cached via `diskcache` and stored separately in `~/.local/share/geopulse/content_cache/`. This directory holds the canonical authored versions.
3. Files are plain Markdown. Keep each file focused on one conceptual domain.

## File conventions

- Filename = conceptual domain in snake_case (e.g. `china_century_of_humiliation.md`)
- Keep files under ~2000 tokens each; split if larger
- Include a `# Source / Updated` line at the top of each file
- Files referenced from `Geopulse_constitution.md` should have a matching file here for the deep-dive version

## Current files

| File | Domain |
|------|--------|
| `china_historical_frame.md` | Century of Humiliation, Taiwan, sovereignty doctrine |
| `russia_ukraine_historical_frame.md` | Varangian Rus, Putin's temporal anchor, NATO expansion |
| `india_pakistan_partition.md` | 1947 Partition, Kashmir, nuclear dyad |
| `middle_east_ottoman_legacy.md` | Sykes-Picot, mandate states, sectarian politics |

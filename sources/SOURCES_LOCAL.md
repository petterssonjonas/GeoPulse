# GeoPulse — Local news sources

Sources for the **Local News** tab (when category tabs are implemented). Highly region-dependent: add feeds for your city, region, or country. Use this doc to list and rank local sources; add to the app when per-category sources are supported.

**Test:** For each RSS/Atom URL, run the same test as in `scripts/test_sources.py` or a one-off `feedparser.parse(requests.get(url, timeout=15).content)` and check `feed.entries`.

---

## How to fill this in

1. **Identify your region** (e.g. city, state, country).
2. **Find local outlets** that offer RSS: newspapers, local NPR/PBS, municipal/civic feeds.
3. **Add rows below** with name, URL, type, tier, status after testing.
4. **When the app supports it:** Add entries to `data/sources.yaml` (or `sources_local.yaml`) with `category: local` and your `region`.

---

## Tier 1 — Sentinel (local)

Fast local headlines (e.g. breaking, council, weather).

| Name | URL / type | Region | Status | Rank / notes | Use |
|------|------------|--------|--------|--------------|-----|
| (Add local outlet) | (RSS/Atom URL) | — | untested | — | — |

---

## Tier 2 — Context (local)

Deeper local coverage, civic, or regional analysis.

| Name | URL / type | Region | Status | Rank / notes | Use |
|------|------------|--------|--------|--------------|-----|
| (Add local outlet) | (RSS/Atom URL) | — | untested | — | — |

---

## Examples (replace with your region)

- **US local:** Many NPR stations have RSS; local newspapers often have a “news” or “local” RSS.
- **UK:** BBC Local (e.g. England regions), local newspaper feeds.
- **Other:** Search “[your city] news rss” or check outlet websites for “RSS” / “Feed”.

---

## Changelog

- **2025-03-04:** Doc added. Template for user-configured local sources; no feeds filled in.

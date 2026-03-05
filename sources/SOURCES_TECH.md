# GeoPulse — Tech & AI sources

Sources for the **AI & Technology** tab (when category tabs are implemented). Same tier idea: sentinel for fast tech news, context for depth. Track status and use here; add to `data/sources.yaml` (or a category-specific config) when the app supports per-tab sources.

**Test:** For any RSS/Atom URL you add, you can run a one-off check with Python:
`feedparser.parse(requests.get(url, timeout=15).content)` and check `feed.entries`.

---

## Tier 1 — Sentinel (tech)

Fast, frequently updated feeds for “something happening in tech?”

| Name | URL / type | Status | Rank / notes | Use |
|------|------------|--------|--------------|-----|
| The Verge | `https://www.theverge.com/rss/index.xml` (RSS) | untested | — | — |
| Ars Technica | `https://feeds.arstechnica.com/arstechnica/index` (RSS) | untested | — | — |
| TechCrunch | `https://techcrunch.com/feed/` (RSS) | untested | — | — |
| Wired | `https://www.wired.com/feed/rss` (RSS) | untested | — | — |
| MIT Technology Review | `https://www.technologyreview.com/feed/` (RSS) | untested | — | — |

---

## Tier 2 — Context (tech / AI)

Analysis, policy, and deeper coverage.

| Name | URL / type | Status | Rank / notes | Use |
|------|------------|--------|--------------|-----|
| IEEE Spectrum | `https://spectrum.ieee.org/feeds/content/blog/rss` (RSS) | untested | — | — |
| VentureBeat (AI) | `https://venturebeat.com/category/ai/feed/` (RSS) | untested | — | — |
| AI News / similar | (add as you find) | — | — | — |

---

## Adding to the app

When the app supports per-category sources (e.g. `data/sources_tech.yaml` or a `category` field in `sources.yaml`), add entries from the tables above with `name`, `url`, `type`, `tier`, `category: tech`, `region`, `enabled`.

---

## Changelog

- **2025-03-04:** Doc added. Tier 1: The Verge, Ars Technica, TechCrunch, Wired, MIT Tech Review. Tier 2: IEEE Spectrum, VentureBeat AI. All untested; run tests when wiring into app.

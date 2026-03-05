# GeoPulse — Markets sources

Sources for the **Markets** tab (when category tabs and markets watcher are implemented). Financial news, indices, and macro. Many major outlets (Bloomberg, FT) don’t offer free public RSS; workarounds include Google News filters or dedicated market data APIs later.

**Test:** For RSS/Atom URLs, use the same approach as in `scripts/test_sources.py` (requests + feedparser).

---

## Tier 1 — Sentinel (markets)

Fast-moving business and market headlines.

| Name | URL / type | Status | Rank / notes | Use |
|------|------------|--------|--------------|-----|
| Reuters Business | `https://feeds.reuters.com/reuters/businessNews` (RSS) | untested | Same DNS issues as Reuters World? | — |
| CNBC | `https://www.cnbc.com/id/100003114/device/rss/rss.html` (RSS) | untested | — | — |
| Yahoo Finance (RSS) | Various; e.g. market summary feeds | untested | — | — |
| Bloomberg | No public RSS | — | Google News: `when:24h+allinurl:bloomberg.com` | — |

---

## Tier 2 — Context (markets / macro)

Analysis and commentary.

| Name | URL / type | Status | Rank / notes | Use |
|------|------------|--------|--------------|-----|
| Financial Times | Often paywalled; limited free RSS | — | — | — |
| MarketWatch | `https://feeds.content.dowjones.io/public/rss/mw_topstories` (RSS) | untested | — | — |
| Investing.com / similar | (add as you find) | — | — | — |

---

## Market data (future)

The **Markets watcher** in the roadmap (currencies, commodities, indices) will likely use APIs (e.g. Alpha Vantage, Yahoo Finance API) or dedicated data feeds rather than RSS. This doc is for **news** about markets; data pipelines go in a separate design.

---

## Changelog

- **2025-03-04:** Doc added. Tier 1: Reuters Business, CNBC, Bloomberg (workaround). Tier 2: FT, MarketWatch. All untested. Market data APIs noted as future.

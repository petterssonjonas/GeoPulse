# GeoPulse — News sources (geopolitics / world)

One place to track **geopolitics & world news** sources: **main agencies** (reference), **tier** (sentinel / context / official), **status** (working / broken / untested), **rank**, and whether to **use** them. Use this doc to research and decide what to enable in `data/sources.yaml`. Good data before prompt work.

**How to test:** Run `python scripts/test_sources.py` from repo root to verify all sources in `data/sources.yaml`.

---

## Google News workaround (tested)

**Result:** The documented queries `**when:24h+allinurl:domain.com`** were tested against Google News RSS; they return **0 items** (empty feed). So that exact workaround **does not work**.

**What does work:** Using `**site:domain.com`** in the query returns up to 100 items per feed:


| Query              | RSS URL                                                                             | Test result   |
| ------------------ | ----------------------------------------------------------------------------------- | ------------- |
| `site:reuters.com` | `https://news.google.com/rss/search?q=site%3Areuters.com&hl=en-US&gl=US&ceid=US:en` | **100 items** |
| `site:apnews.com`  | `https://news.google.com/rss/search?q=site%3Aapnews.com&hl=en-US&gl=US&ceid=US:en`  | **100 items** |
| `site:afp.com`     | `https://news.google.com/rss/search?q=site%3Aafp.com&hl=en-US&gl=US&ceid=US:en`     | **100 items** |


So for Reuters, AP, and AFP you can add a **source** in `data/sources.yaml` with `type: rss` and the URL above (with `q=site%3A<domain>`). The app’s existing `search_google_news()` uses the same RSS endpoint; you could also add these as fixed “sources” so they run every sentinel cycle instead of only on search. Note: Google News RSS links are redirect URLs (news.google.com/rss/articles/...); readers open the real article when followed.

---

## Main sources (reference)

The big global wire agencies and major outlets. Not all offer public RSS; we list them for context and so sentinel choices are clear.


| Name                              | Notes                                                                                      | Public RSS?                                                     | Workaround                                                                                                             |
| --------------------------------- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **AFP** (Agence France-Presse)    | Major global agency. In main sources.                                                      | No — AFP News is subscriber/login.                              | Google News RSS **works** with `site:afp.com` (see “Google News workaround” below). Often syndicated (e.g. France 24). |
| **Reuters**                       | Major global agency.                                                                       | Yes, but `feeds.reuters.com` often DNS/unreachable in practice. | Google News RSS **works** with `site:reuters.com` (not `when:24h+allinurl` — that returns empty).                      |
| **AP** (Associated Press)         | Major global agency.                                                                       | No — apnews.com no longer offers public RSS.                    | Google News RSS **works** with `site:apnews.com`.                                                                      |
| **BBC**                           | Global broadcaster; public RSS.                                                            | Yes.                                                            | `http://feeds.bbci.co.uk/news/world/rss.xml` — **working**.                                                            |
| **Al Jazeera**                    | Not one of the “big three” wires, but strong for our use: fast, global, good sentinel fit. | Yes.                                                            | `https://www.aljazeera.com/xml/rss/all.xml` — **working**.                                                             |
| **Bloomberg**                     | Terminal/subscriber focus; no free public RSS.                                             | No.                                                             | Try Google News RSS with `site:bloomberg.com` (not tested). Best for markets/business angles.                          |
| **DPA** (Deutsche Presse-Agentur) | Real-time/pro services; no prominent public RSS.                                           | No.                                                             | Try `site:dpa.com` in Google News RSS (or hl=de, gl=DE for German).                                                    |
| **EFE**                           | Spanish-language focus; some English RSS.                                                  | Yes (English edition).                                          | `https://www.efe.com/efe/english/4/rss` or Google News `site:efe.com`.                                                 |


**Why the decline in official RSS?** Many agencies prioritize subscriptions, APIs, and direct traffic. Public RSS persists more at broadcasters (e.g. BBC). **Working workaround:** Google News RSS with `**site:domain.com`** returns items; `**when:24h+allinurl:domain`** was tested and returns **empty**.

---

## Tier 1 — Sentinel

Checked every sentinel interval. Need **fast, reliable** feeds. 


| Name           | URL / type                                                                                | Status (tested)              | Rank / notes                                      | Use (yaml)               |
| -------------- | ----------------------------------------------------------------------------------------- | ---------------------------- | ------------------------------------------------- | ------------------------ |
| BBC World News | `http://feeds.bbci.co.uk/news/world/rss.xml` (RSS)                                        | **working**                  | —                                                 | enabled                  |
| Al Jazeera     | `https://www.aljazeera.com/xml/rss/all.xml` (RSS)                                         | **working**                  | Often breaks news, good choice for sentinel tier. | enabled                  |
| Reuters World  | `https://news.google.com/rss/search?q=site%3Areuters.com&hl=en-US&gl=US&ceid=US:en` (RSS) | **broken** — DNS unreachable | Use Google News workaround (see Main sources).    | enabled (fix or disable) |
| AP News World  | `https://news.google.com/rss/search?q=site%3Aapnews.com&hl=en-US&gl=US&ceid=US:en` (RSS)  | **broken** — 404             | No public RSS; use Google News workaround.        | enabled (fix or disable) |


*AFP:* No direct public RSS. To add AFP to sentinel, use the **working** Google News RSS URL with `site:afp.com` (see “Google News workaround” above).

---

## Tier 2 — Context

Fetched when tier 1 shows notable activity. Analysis, think tanks, regional depth. 


| Name                           | URL / type                                                                                                                                                                                                | Status (tested) | Rank / notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Use (yaml) |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------- |
| Foreign Policy                 | `https://foreignpolicy.com/feed/` (RSS)                                                                                                                                                                   | **working**     | —                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | enabled    |
| The Economist International    | `https://www.economist.com/international/rss.xml` (RSS)                                                                                                                                                   | **working**     | —                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | enabled    |
| Council on Foreign Relations   | `Probably move this to different tier. split the different publications to corresponding tab. Consider if we want to use this at all.``Also other audio podcasts?``ukraine the latest, battle lines...` | untested        | current podcasts: [https://www.cfr.org/podcasts](https://www.cfr.org/podcasts)Podcasts available on the site, maybe dl there and transcribe? maybe too much work. example link: May need to pull transcripts from their youtube video podcasts. also available on apple and spotify. [https://www.cfr.org/reports](https://www.cfr.org/reports)[https://www.cfr.org/backgrounders](https://www.cfr.org/backgrounders) [https://www.cfr.org/task-force-reports https://www.cfr.org/expert-takes](https://www.cfr.org/task-force-reports/us-economic-security) perhaps good to pull these articles even if as html and clean up. | -          |
| War on the Rocks               | `https://warontherocks.com/feed/` (RSS)                                                                                                                                                                   | **working**     | —                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | enabled    |
| Bellingcat                     | `https://www.bellingcat.com/feed/` (RSS)                                                                                                                                                                  | **working**     | —                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | enabled    |
| The Diplomat                   | `https://thediplomat.com/feed/` (RSS)                                                                                                                                                                     | **working**     | —                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | enabled    |
| Middle East Eye                | `https://www.middleeasteye.net/rss` (RSS)                                                                                                                                                                 | **working**     | —                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | enabled    |
| Institute for the study of war | [https://understandingwar.org/research/](https://understandingwar.org/research/)                                                                                                                          | untested        | very in depth. not rss, hopefully can scrape. Interesting as "learn more" on a subject, perhaps send user there? often pictures etc too...                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |            |


---

## Tier 3 — Official

Fetched on breaking events (e.g. severity ≥ 4). Government / institutional feeds. 


| Name                       | URL / type                                                                                                      | Status (tested) | Rank / notes                                                                                                                                                               | Use (yaml)               |
| -------------------------- | --------------------------------------------------------------------------------------------------------------- | --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| United Nations News        | `https://news.un.org/feed/subscribe/en/news/all/rss.xml` (RSS)                                                  | **working**     | —                                                                                                                                                                          | enabled                  |
| UK Foreign Office          | `https://www.gov.uk/.../foreign-commonwealth-development-office.atom` (Atom)                                    | **working**     | —                                                                                                                                                                          | enabled                  |
| US State Department        | `https://www.state.gov/rss-feeds` (RSS)                                                                         | **untested**    | new url [https://www.state.gov/rss-feeds](https://www.state.gov/rss-feeds)                                                                                                 | enabled (fix or disable) |
| NATO News                  | `https://news.google.com/rss/search?q=site%3Anato.int&hl=en-US&gl=US&ceid=US:en` (RSS)                          | **untested**    | Google News RSS (use `site:nato.int`): [link](https://news.google.com/rss/search?q=site%3Anato.int&hl=en-US&gl=US&ceid=US:en).                                             | enabled (fix or disable) |
| EU External Action Service | `https://news.google.com/rss/search?q=site%3Aeeas.europa.eu&hl=en-US&gl=US&ceid=US:en` (RSS)                    | **untested**    | Google News RSS (use `site:eeas.europa.eu`): [link](https://news.google.com/rss/search?q=site%3Aeeas.europa.eu&hl=en-US&gl=US&ceid=US:en).                               | enabled (fix or disable) |
| IAEA News                  | `https://www.iaea.org/feeds/topnews` (RSS)                                                                      | untested        | Try alternative feeds: [topnews](https://www.iaea.org/feeds/topnews), [pressalerts](https://www.iaea.org/feeds/pressalerts).                                               | enabled (fix or disable) |
| Chinese MFA Press          | `https://news.google.com/rss/search?q=site%3Afmprc.gov.cn+OR+site%3Amfa.gov.cn&hl=en-US&gl=US&ceid=US:en` (RSS) | **untested**    | Google News RSS: `site:fmprc.gov.cn OR site:mfa.gov.cn` — [link](https://news.google.com/rss/search?q=site%3Afmprc.gov.cn+OR+site%3Amfa.gov.cn&hl=en-US&gl=US&ceid=US:en). | enabled (fix or disable) |


---

## Reliability notes (from codebase)

- **Retry / backoff:** Not yet implemented. Planned: 3 attempts with backoff per source; skip after 5 consecutive failures until next full cycle.
- **Per-source health:** No DB fields yet; source health dashboard in settings is on the roadmap.
- **RSS vs Atom:** Fetchers support both; feedparser handles Atom (e.g. UK FCO).
- **Scrape:** Chinese MFA uses `type: scrape`; more fragile (selectors, rate limits, DNS).

When you fix or add a source, run `scripts/test_sources.py`, update **Status** and **Rank / notes** here, then set `enabled: true/false` in `data/sources.yaml` to match.

---

## Adding or changing sources

1. **Add here first:** New row in the right tier with URL, type, status, rank/notes.
2. **In `data/sources.yaml`:** Add same source with `name`, `url`, `type` (rss | atom | scrape), `tier`, `category`, `region`, `enabled`. For scrape, add `scrape_config` with `article_selector` and optional `base_url`.
3. **Test:** `python scripts/test_sources.py`
4. **Sync:** Keep this doc and sources.yaml in sync.

---

## Other tabs

- **Tech / AI:** See `sources_tech.md`
- **Markets:** See `sources_markets.md`
- **Local:** See `sources_local.md` (user-configured or regional)
- **X (Twitter):** See `sources_x.md` — Twikit, max 30 min, select accounts; merged into next briefing.

---

## Changelog

- **2025-03-04:** Restructured. Main sources section (AFP, Reuters, AP, BBC, Al Jazeera, Bloomberg, DPA, EFE). AFP in main; Al Jazeera clarified as sentinel-fit. Tier tables updated with test results from `scripts/test_sources.py`. Working: BBC, Al Jazeera, FP, Economist, WOTR, Bellingcat, Diplomat, MEE, UN, UK FCO. Broken: Reuters (DNS), AP (404), CFR (404), State (parse), NATO, EEAS, IAEA (404), Chinese MFA (DNS). Added `scripts/test_sources.py`. Split tech/markets/local into separate docs.
- **2025-03-04:** Google News workaround tested. `when:24h+allinurl:domain` returns **0 items** (does not work). `**site:domain.com`** works: 100 items each for site:reuters.com, site:apnews.com, site:afp.com. Doc updated with working RSS URLs and Main sources table corrected.


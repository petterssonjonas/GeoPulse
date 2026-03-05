# GeoPulse — X (Twitter) sources

Tweets as a **separate source stream**: pulled on their own schedule (max every 30 min), from a **select few accounts** (OSINT, world leaders). Latest tweets are **integrated into the next briefing generation** run alongside articles.

**Library:** [Twikit](https://github.com/d60/twikit) — Python, no API key, login-based; good for small scale. Use a **dedicated X account** for the app (credentials in config or env).

---

## Design


| Aspect             | Choice                                                                                                                               |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Pull frequency** | Max every 30 minutes.                                                                                                                |
| **Scope**          | Select few accounts only: OSINT, world leaders, key official handles.                                                                |
| **Sentinel**       | Tweets are **not** sentinel in v1 (don’t trigger escalation). Optionally later: high-signal accounts could trigger an earlier brief. |
| **Integration**    | Latest tweet batch merged into the **next** briefing generation run; LLM can cite “X user @… said …”.                                |


---

## Accounts to follow (candidates)

Add or remove as you choose. Keep the list **short** to stay conservative.

### OSINT / conflict / verification


| Handle (example) | Notes                                                        |
| ---------------- | ------------------------------------------------------------ |
| (add)            | OSINT aggregators, conflict monitors, verification projects. |


### World leaders / official


| Handle (example) | Notes                                                      |
| ---------------- | ---------------------------------------------------------- |
| (add)            | e.g. @POTUS, @KremlinRussia_E, key MFA or leader accounts. |


### Other


| Handle (example) | Notes                                                        |
| ---------------- | ------------------------------------------------------------ |
| (add)            | Wire agencies, UN, NATO, etc. if they post breaking updates. |


---

## Config (when implemented)

- `x_enabled`: true/false  
- `x_interval_minutes`: 30  
- `x_accounts`: list of @screen_names  
- Credentials: app X account (username/email + password) — store in config or env, not in repo.

---

## Implementation ref

See **TODO.md** → New Features → **X (Twitter) sources via Twikit**: `scraping/x_fetcher.py`, `data/sources_x.yaml` (or config section), scheduler 30 min timer, merge tweets into briefing input.

---

## Changelog

- **2025-03:** Doc added. Twikit chosen for small-scale X scraping; dedicated app account; max 30 min pull; separate stream, merged into next briefing run.


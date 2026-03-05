#	| Item	| Why this order
1–2 |	Migration framework, Robust parsing	(Done) Foundation; everything else assumes stable schema and parseable briefs.
3	| Automated tests	Lock in 1–2 so we don’t regress; run after each later change.
4	| Fix source reliability	“Good data first”: retry, more sources, skip after 5 fails.
5	| Parsing/scraping efficiency	One-at-a-time, tiered pull; keeps memory low and fits with 4.
6	| Parallel scraping + rate limiting	After fetchers are reliable; parallel + limit avoids hammering sites.
7	| Anti-spam (user can’t spam update)	With 6: define safe intervals and caps.
8	| Data retention	Bounds growth; migration (1) is done so schema is safe.
9	| Source health dashboard	Needs retry/health data from 4 and a place to show it.
10	| Article deduplication	Ingest-time dedup after we have good sources and retention.
11–12|	Window resize, Sidebar resize lag	UX: fix “can’t resize” then “resize is laggy”.
13	| Tags fully visible	UX polish; config option already decided.
14	| Move depth to settings	UI reorg.
15	| Briefing card right-click menu	Feature that builds on a stable data path.
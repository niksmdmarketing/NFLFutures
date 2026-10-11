# College football first release

Separate `/cfb/` section, FBS only, calendar-season 2015–2026 initially (rolling latest 12 seasons). Excludes all-star and exhibition squads, preserves games against FCS opponents. Records and summaries include postseason. Conference grouping is season-specific, not a conference tiebreak simulation.

Source: SportsDataverse's ESPN-derived season CSV release archives. Nine dataset families: team reference, completed schedules, team summaries, passing/rushing/receiving summaries, team box scores, advanced team game stats and situational game stats. No odds files, API keys, paid sources or FotMob data. Missing advanced coverage stays missing. All raw archives stay in the Actions download cache; only selected human-readable exports are published to the protected site. No download buttons (this is not DRM: authorized visitors can still copy data their browser receives).

Source definitions: https://github.com/sportsdataverse/cfbfastR-cfb-data/blob/main/DATASETS.md

Season summaries are retrospective provider calculations, not historical as-of forecasts. They must not be used in a replay before the period they summarize. Player roles are separate rows to avoid summing passing/rushing/receiving EPA or comparing different denominators implicitly. Source-derived production can differ from official box totals.

Refresh: existing two-hour public pipeline, current-season nine files with two-hour cache; past seasons yearly cache. Initial maximum 108 successful archive downloads. Last-good fallback reports retrieval errors on Data coverage. A feed failure does not stop other sport builds. First-generation failure does not fabricate a section. No additional private scheduled jobs; protected publisher picks up the combined public revision on its existing schedule. Access controls are unchanged.

Not in this release: authenticated CFBD recruiting/returning production/transfers, comprehensive defensive individual stats, injury availability, poll history, future fixtures beyond the provider archive, or a fitted/tested title/conference/playoff model. Do not claim all possible college data collected.

Validation: four targeted unit tests, season/FBS exclusions, unique one-to-one merges, confirmed completion status, existing public test suite, JS syntax, per-season export counts/fields and live navigation after deployment.

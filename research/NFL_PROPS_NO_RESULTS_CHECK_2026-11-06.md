# NFL props no-results check, 6 Nov 2026

Inputs: OddsPapi NFL history (private repo collected_data/oddspapi_nfl/props, 129 fixtures), the frozen crosswalk
(research/nfl_market_crosswalk_2026-11-06.json), GPT's forecast export (fixtures.json, probabilities.jsonl.gz, 60-minute horizon).
No outcome, profit or edge was computed; prices were used only for presence and timestamps. Player names are not yet available
(NFL name runs start on game days from 9 Nov), so player matching is not checked here.

- Crosswalk rows: 35,970 across 126 fixtures and 358 OddsPapi player ids.
- Timing: no entry quote after its 60-minute cutoff; no close at or after kickoff.
- Entry quote present: Pinnacle 99.1%, FanDuel 88.5%, DraftKings 68.6% of rows.
- Fixtures matched to the forecast export: 121 of 126 (5 unmatched are January/February playoff games outside the export).
- Of the 121 matched fixtures, **19 have receipt-proved forecasts** (primary-eligible) and 102 only reconstructed ones (supplementary).
- Unique player lines (fixture, player, stat, line): pass attempts 4,191 (Sep-Nov 2026), receptions 11,638.

Implication: the primary NFL test rests on 19 games; with the window-A requirement unmet (no receipt-proved games in weeks 1-4),
the primary gates will be insufficient whatever the prices show. Supplementary (reconstructed) results are reported but cannot pass.

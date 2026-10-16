# NBA items that need in-season data (status 17 Oct 2026; the 2026-27 season has not tipped off)
Open: whole-season traded-player counting, depth reallocation when starters are out, continuity prior, Dort rating.
All four depend on dated roster/transaction history and games played this season, so none can be replayed honestly yet (see NBA_ROSTER_FADE_RULE.md: the roster term can only be bounded, not back-tested).
Plan once about 20 games per team are played: pull dated transactions and per-game availability from the collection already running (availability workflow), test each in a point-in-time replay of 2022-2026
against the live model with the same pre-registered style rule (combined race log loss, majority of seasons, nested selection, main and NOLEAK agree), one item at a time.
Closed already: roster fade (rejected 17 Oct), roster continuity for NBL/AFL (no gain), NFL non-QB injury layer (no gain, v5_notes.md), NHL roster continuity (research/nhl_continuity_test.py: no gain).

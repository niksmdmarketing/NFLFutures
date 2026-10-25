# NFL aligned-input challenger forward shadow — 26 October 2026 Sydney

## Frozen baseline and scope

Keep `nfl-player-props-v1-experimental`, its parameter file, existing `nfl-props-archive`, website output and baseline scoring unchanged. Run one separate shadow model and append it only to `nfl-props-challenger-archive`. Never use the challenger to change the baseline or select player availability/roles.

The sole challenger change is team pass-attempt feature alignment: for team A versus B, `own_att` and `own_plays` use A's recent team history, while `opp_att` uses B's recent opponent-attempts-allowed history and `opp_plays` uses B's recent own plays. Keep the frozen parameters, two-season history span, last-20 EWMA, player rates, roster, availability, target allocation, generation time and distribution families identical to the baseline. Unavailable pass EPA and Elo inputs remain at their frozen training means.

Filter weekly team-game history to games whose scheduled kickoff plus six hours is strictly before the forecast timestamp. A missing opponent state uses the frozen feature mean; never infer it from current-game or future data.

## Archiving and scoring

Use the existing NFL player-prop archive schedule and independent receipt-time scorer, but a distinct Git branch and directory. Preserve both 60-minute and 360-minute scoring horizons, and compare only identical game/team/player/stat rows. Existing baseline forecast bytes must remain unchanged. Archive full distributions, generation time, source hashes, model ID, and the feature-change note.

## Review gate

Do not adopt during the forward run. Review after at least one full regular season and at least 500 identical settled player-prop rows across both horizons, reporting conditional RPS and availability Brier separately by stat, season, horizon and role/volume groups. A favorable historical replay is supporting evidence only; adoption requires a later explicit decision after forward results and coverage are audited.

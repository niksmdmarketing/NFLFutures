"""Freeze the v1.2 matchup settings for 2026: beta and league shares fitted on 2018-2025 exactly as a 2026 fold of matchup_test.py.
Writes pipeline/nfl_props_v12_params.json. Rule: MATCHUP_RULE.md (amendment of 26 Oct 2026)."""
import json
from pathlib import Path

import core as C
from build import OUT, player_inputs
from conditional_audit import RECEIVERS
from run import make_priors
from matchup_test import defence_table, ratios, fit_beta, K_PSEUDO, PRIOR_SD, CAP, GROUP
import pandas as pd

g = pd.read_parquet(OUT / 'games.parquet'); players = pd.read_parquet(OUT / 'players.parquet')
st, _, _, _ = player_inputs(g)
dtab = defence_table(st, g)
train = players[players.season.between(2018, 2025) & players.app.notna() & players.actual_team_att.notna()]
pri = make_priors(train)
ra = train[train.position.isin(RECEIVERS) & train.app.eq(1)].reset_index(drop=True)
conc = C.fit_concentration(ra.receptions, ra.actual_team_att, C.rates(ra, pri, 'receptions'))
tgt = dtab[dtab.season.between(2018, 2025)]; tot = tgt.total.sum()
league = {c: float(tgt[c].sum() / tot) for c in ('WR', 'TE', 'RB')}
beta = fit_beta(ra.receptions, ra.actual_team_att.astype(int), C.rates(ra, pri, 'receptions'), ratios(ra, dtab, league), conc)
out = dict(model_id='nfl-player-props-v1.2-matchup-shadow', fitted_seasons=[2018, 2025], beta=beta, league_shares=league,
           k_pseudo_targets=K_PSEUDO, beta_prior_sd=PRIOR_SD, cap=list(CAP), groups=GROUP, window_games=20, half_life=5,
           research_concentration=conc, rule='research/nfl_games_props/MATCHUP_RULE.md')
p = Path(__file__).resolve().parents[2] / 'pipeline/nfl_props_v12_params.json'
p.write_text(json.dumps(out, indent=2)); print(json.dumps(out, indent=2))

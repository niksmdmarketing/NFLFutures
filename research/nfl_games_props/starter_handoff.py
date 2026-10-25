"""Seal the dated-depth pilot, its limitations and data-free code handoff."""
import json,zipfile
from pathlib import Path
import pandas as pd
from starter_test import DEST,OUT,sha,now

def main():
    final=DEST/'HANDOFF_MANIFEST.json'
    if final.exists():raise FileExistsError(final)
    src=Path(__file__).parent
    m=json.loads((DEST/'manifest_complete.json').read_text());r=json.loads((DEST/'results.json').read_text())
    assert sha(src/'STARTER_RULE.md')==m['rule_sha256']
    assert all(sha(src/k)==v for k,v in m['code_sha256'].items())
    for fit in r['rolling_fits']:
        assert pd.Timestamp(fit['last_training_game_ready'])<pd.Timestamp(fit['cutoff'])
    p=pd.read_parquet(DEST/'paired_scores.parquet')
    assert not p.duplicated(['game_id','team','aid','stat']).any()
    assert p.week.between(5,18).all()
    s=r['results'];coverage=r['coverage'];diag=json.loads((DEST/'FIRST_PASSER_DIAGNOSTIC.json').read_text())
    current=json.loads((DEST/'CURRENT_STARTER_SCENARIOS.json').read_text())
    text=f'''# Dated QB depth and newly active backups — 24 October 2026 Sydney

## Verdict

The next layer is built and tested locally. Dated depth charts improve player coverage and average QB attempts forecasts, but do not demonstrate a reliable fix for takeovers. Keep this experimental; no live model, site, workflow or repository publication changed.

## Results

2025 regular season, weeks 5–18 after a four-week calibration warm-up. Both versions receive exactly the same expanded QB candidates and involvement probabilities. The only forecasting difference is the dated-depth role signal, calibrated using earlier games only.

| Check | Baseline | Dated-depth candidate |
|---|---:|---:|
| Conditional attempts RPS, lower better | {s['baseline']:.6f} | {s['candidate']:.6f} |
| Relative error-score improvement | — | {100*s['relative_gain']:.2f}% |
| Weeks with lower error | — | {s['weeks_better']}/14 |
| Predicted overs at fixed formula lines | {100*s['over']['baseline']:.1f}% | {100*s['over']['candidate']:.1f}% |
| Actual overs at those lines | {100*s['over']['actual']:.1f}% | {100*s['over']['actual']:.1f}% |

The count-distribution PIT screen passed, but the over-probability gap remains material. This is not evidence of a betting edge or readiness to bet.

Coverage of actual primary passers, as an outcome-only audit on all {coverage['total_team_games']} team-games: original candidate list {coverage['legacy_primary_covered']}; expanded dated-depth list {coverage['expanded_primary_covered']}. Added {r['added_rows']} QB candidate rows across the season. This does not mean the starter was predicted correctly in every game; it means the actual primary was present among candidates. {r['unknown_outcomes']} candidate outcomes remained unknown rather than being guessed as DNP.

The paired score comparison covers {s['n']} involved QB appearances in the evaluation weeks. New-candidate subgroup gain: {100*s['subgroups']['True']['relative_gain']:.2f}% on {s['subgroups']['True']['n']} appearances. Existing-candidate subgroup gain: {100*s['subgroups']['False']['relative_gain']:.2f}% on {s['subgroups']['False']['n']} appearances. These subgroups use candidate provenance, not target performance, to define membership.

## Why this is still not a takeover fix

Among {s['actual_new_primary_diagnostic']['n']} involved QBs who became the primary after not being the previous game's primary, the candidate was {100*(-s['actual_new_primary_diagnostic']['relative_gain']):.2f}% worse. This is an outcome-defined diagnostic, not a pregame selection rule.

The separate play-by-play check found 44 of those new primaries were the first observed passing QB; 11 were not. The depth signal was slightly worse for the former and substantially worse for the latter. Thirty of the 55 remained below rank one in the pregame chart. A depth chart is not a reliable substitute for an injury-aware, game-specific starter announcement. First observed passer is only an outcome proxy, not an independently verified announced starter or medical reason for a substitution.

The local 2025 injury file has no publication timestamps, so its statuses were deliberately not used. Consequently this pilot does not test the full joint depth-plus-injury system that current sources might support. It also cannot establish how much future confirmed-starter reporting would help.

## Logic and safeguards

- Latest source snapshot strictly before kickoff minus one hour, no more than 72 hours old. All 544 team-games had an eligible snapshot in this file.
- Exact GSIS IDs or an unambiguous ESPN-to-GSIS crosswalk. No names-only historical mapping.
- New QBs use lagged prior history where available, otherwise an explicit neutral fallback. They are never selected from the target box score. Their primary-role workload comes from the pooled primary distribution, not tiny historical backup counts.
- Fit the existing role and involvement models on 2020–2024. Fit team volume on earlier 2018–2024 seasons. No market inputs, QB-style volume adjustment or future games.
- One regularised depth coefficient fitted at each cutoff using earlier 2025 appearances only; never same-game or later same-week outcomes. Weeks 1–4 are the fixed warm-up, not a post-result chosen exclusion.
- Twenty unit tests pass, including source cutoffs, stale charts, ambiguous rank one, target-result independence, and provenance/conflict checks for explicit starter records.

## Current source adapter

`CURRENT_STARTER_SCENARIOS.json` contains projected-role contexts for all 32 teams and covers 43 listed QBs previously missing from the original recent-activity candidate list. It reuses the earlier session's source bytes, explicitly dated; it is not a fresh source check or independent forward archive.

Rank order plus elimination of explicitly Out players is labelled an **assumption**, never confirmation. Questionable/Doubtful stays uncertain, and blank/missing status is not healthy. Injury reports only apply when their week matches the upcoming game.

`starter_models.confirmed_signal` is an integration hook for an explicit game/team/player starter record with a source URL and a version-observation time before cutoff. It rejects late records, wrong games, generic 'expected to play' and conflicts with an Out report. It does not manufacture or scrape confirmed announcements. The existing feeds have not yet been shown to provide a complete historical archive of those game-specific records. No confirmed record was invented for this pilot.

## Evidence limits and decision

Only one revised-data season has suitable dated charts locally. Source update timestamps are not independently archived historical retrievals. The original files can contain revisions. Warm-up and rolling calibration use the season sequentially; this is not an untouched validation season. There is no multi-season or independent forward proof.

The pilot meets its written overall promising screen, but the takeover diagnostic and remaining over gap mean it should not replace the current forecasts. Do not tune another depth form on these results. The useful next operational input is an explicit game-level starter announcement or a transparently recorded human assumption, followed by prospective scoring. Mid-game replacements need uncertainty, not hindsight certainty about who starts.

## Handoff

- `results.json`: metrics, fold states, every rolling coefficient and timing.
- `paired_scores.parquet`, `expanded_features.parquet`: private evidence.
- `snapshot_coverage.json`: per-game source timestamps and eligibility.
- `FIRST_PASSER_DIAGNOSTIC.json`: labelled outcome-only check.
- `CURRENT_STARTER_SCENARIOS.json`: assumption-labelled current contexts, not forecasts eligible for adoption.
- `STARTER_FOUNDATION_CODE_ONLY.zip`: source/rules/tests, no raw data or fitted output.
- `manifest_complete.json`, `HANDOFF_MANIFEST.json`: provenance and checks.

The previous code-only packages predate this step; use the new starter package for handoff. All outputs are create-only. Nothing was published.
'''
    report=DEST/'REPORT.md';report.write_text(text,encoding='utf-8')
    package=DEST/'STARTER_FOUNDATION_CODE_ONLY.zip'
    with zipfile.ZipFile(package,'x',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(src.iterdir()):
            if path.is_file() and path.suffix in ('.py','.md'):z.write(path,'research/nfl_games_props/'+path.name)
    output=dict(sealed=now(),rule_and_scored_code_hashes_verified=True,rolling_cutoffs_verified=True,paired_rows_unique=True,
        unit_tests_passed=20,deployed=False,published=False,
        output_sha256={p.name:sha(p) for p in DEST.iterdir() if p.is_file()},
        source_sha256={p.name:sha(p) for p in src.iterdir() if p.is_file() and p.suffix in ('.py','.md')})
    with final.open('x') as f:json.dump(output,f,indent=2)
    print(str(report))

if __name__=='__main__':main()

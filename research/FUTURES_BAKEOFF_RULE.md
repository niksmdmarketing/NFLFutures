# Futures bake-off (DeepSeek leads; Claude implements and runs; TypeSafe prioritises). Rule, draft v1 (NOT YET FROZEN)

Written 8 Nov 2026 (Sydney), before any arm exists or any arm result. Amendments below, dated; nothing above them is edited. Source: private relay packets 012-015 (replies in deepseek_relay/inbox, private repo).

## Objective and limits
Most accurate and most profitable FUTURES forecasts (NBA, NHL, AFL, NBL; NFL descriptive only, 4 replay seasons). No historical futures prices are held, so historical PROFIT cannot be measured; the pre-registered measure is calibration of replayed playoff/division/title probabilities, and profit is judged forward (selection paper test, mid-January 2027 earliest, and daily price capture). A calibrated model has zero edge against a calibrated price: the forward record must log the book's de-vigged tail beside ours.
No market price is ever a model input. Model count cap: TWO (TypeSafe 99%: stop at two and put the effort into daily futures price capture). Structural fixes count as models.

## Agreed so far (DeepSeek, checked by Claude; TypeSafe on M2 build form 88%)
- Decision-capable markets (at least 60 independent outcomes in the evaluation window): NBA playoff (112), AFL playoff (56-64), NHL playoff (80). Everything else (title anywhere, NHL r2/r3/finals alone, seed1, AFL/NBL divisions, all of NBL and NFL) is descriptive; no pass can be earned.
- Evaluation seasons after 2018; replays are NBA 2013-2026, NHL 2015-2025 (no 2019-20), AFL 2013-2026, NBL 2013-2025, NFL 2022-2025.
- Metric: calibration slope of the outcome on logit(p), intercept free. Log loss kept only as a no-harm check (second-order).
- Rows at p = 0 or 1 (certain outcomes; up to 24% of AFL Q3 playoff, 21% of NBA Q3 playoff): CLIP at 0.001/0.999 as primary (dropping depends on the arm's own output and breaks the pairing); the drop slope is reported as a robustness check; opposite signs between constructions means INSUFFICIENT, not fail. Sensitivity floor 0.0001 reported, not gating. Known: AFL Q3 playoff slope is 0.69 clipped (pack) and 0.63 dropped.
- Interval: season-cluster Bayesian (exponential-weight) bootstrap, 10,000 draws, seed 20261108, both arms on the same draws; point estimate is the full-sample fit, never the bootstrap mean; report the 10th/50th/90th contrast percentiles; fixed small L2 penalty in every fit (lambda to be fixed by a null live-versus-live run so that |slope| < 5 in at least 99% of draws); fraction of draws with |slope| above 5 or non-convergent above 5% means INSUFFICIENT. Rademacher wild weights are invalid for a likelihood and are not used.
- Success per test: slope moves toward 1, paired 90% interval excludes 0; holds with 2019-20 and 2020-21 dropped (NBA) / 2020 dropped (AFL); no-harm log-loss lower bound above -0.002 and no decision market worse than live by more than 0.002; a null arm run and printed beside every arm. A pass authorises a SHADOW season, never a live change.
- M2: AFL playoff slope crosses 1 within one season (1.10 at Q1 to 0.63-0.69 at Q3; contrast -0.47 [-0.67, -0.27]) so one constant tau cannot fix it. Build form: three-constant tau schedule keyed to games played (TypeSafe 88%), not the Kalman filter. Confirmatory: AFL Q3 playoff slope (powered), NBA preseason playoff slope (conditional on the paired half-width being below the 0.50 live displacement). Exact schedule, cut points, grid, gates and registered prediction: awaiting DeepSeek (its packet-015 reply was cut off before that section).
- M1 (concave series transform): DOWNGRADED to a DIAGNOSTIC by DeepSeek; a single exponent cannot move NHL r2 (0.89, too extreme) and r3 (1.51, too flat) in the needed opposite directions; the r3-r2 contrast (+0.62 [+0.17, +1.15]) looks like a bracket/seeding effect. Its full diagnostic spec is also awaiting.

## Still to do before freezing
Complete M2 schedule spec and M1 diagnostic spec; null-arm lambda; paired minimum detectable movements (needs an arm); stamp the NBA top-6/play-in block (16 Oct provenance); regenerate the pack at 10,000 draws as the baseline.

---
## Amendment 1 (8 Nov 2026): M2 and M1 specs received, win totals added, code facts checked. Original text above is unchanged.
Source: DeepSeek replies 016 and 018 (private relay), checked by Claude. No results exist yet.

### M2 frozen (AFL first; NBA only if AFL passes)
- Form: tau_eff(gp) = m(gp) x tau_live(gp); m1 for gp <= 6, m2 for 7-15, m3 for gp >= 16 (AFL G = 23, cuts round(0.25G)=6, round(0.65G)=15). NBA/NHL (G = 82) would use 20 and 53. Only AFL runs now.
- Direction: slope > 1 = too flat = too much tau; slope < 1 = too extreme = too little tau.
- Fit on AFL 2013-2018 (6 seasons, 108 team-season playoff outcomes); evaluate 2019-2026, primary with 2020 dropped.
- Grid m in {0.7, 1.0, 1.4}^3 = 27, chosen by pooled discovery playoff log loss, ties to fewest non-unit constants; one step outward allowed if optimum is on an edge (reported). Weak fit, stated.
- Gate G1: m = (1,1,1) must reproduce the live AFL replay byte-for-byte on all 14 seasons, or no arm is scored. Gate G2: floor 0.001/0.999 and lambda_sep identical in live and arm; frozen minimum detectable shift 0.20 on eval seasons.
- Registered prediction: m1 = 1.0, m2 in [0.85, 1.0], m3 in [1.2, 1.4]; Q3 playoff slope 0.69 -> 0.85-1.00; Q1 moves < 0.10; last-quarter playoff 0.77 -> toward 1; Q3-Q1 contrast -0.47 -> toward -0.10; no harm on top4 and finals.
- Falsification (overrides every other number): AFL Q3 playoff slope, paired Bayesian season-cluster 90% interval, eval seasons, clip construction, 2020 dropped. Falsified if the point estimate moves away from 1, or moves toward 1 with the interval containing 0 and half-width below 0.20. If falsified: tau mechanism falsified, bake-off ends at two models, NBA not run, M2 not re-parametrised here.
- Claude's checks of DeepSeek's questions: (a) the AFL rating IS refit at every checkpoint (replay_afl.py srs_w / A.srs on games played), so tau mainly carries unmodelled rating error plus the finals bracket; this is the risk DeepSeek named and the registered prediction stands to be tested, not assumed. (b) tau is drawn once per simulation for the whole remaining season (afl_site.py line 337: Rs = R + rng.normal(0, tau, (m, T))), not per game. Multiplying tau by m leaves the random stream unchanged. (c) tau = TAU0 x (1 - min(n_played, 23) / TAU_FADE), TAU0 14, TAU_FADE 30 (replay_afl.py line 107, same as live). (d) Runtime: one AFL replay season at BT_SIMS 1500 takes about 7 seconds on one core, so 27 configs x 6 seasons (162 replay-seasons) is about 20 minutes; the grid does NOT need cutting to 9.
- G1 baseline note: the stored model/replay/afl_*.csv pre-date the grand-final-neutral change (AFL_FINALS_HOME_RULE.md), so p_title differs by up to 0.024 on regeneration; every other column matches. G1 compares the arm at m = (1,1,1) against a live replay REGENERATED with current code, not against the old stored files.

### M1 diagnostic (not a decision)
Concave series transform plus round-1 intercept shift, measuring whether the NHL r3-r2 contrast (+0.62 [+0.17, +1.15]) moves. Prediction: moves < 0.15 either way, meaning the contrast is a bracket/seeding effect and the NHL game model is not implicated. Movement >= 0.15 toward 0 with interval excluding 0 earns a second look only under a new dated rule.

### Win totals (second main market, accuracy only; no historical lines held, so never profit)
- S1 mean error: reported, never tested (wins are zero-sum within a season). S2: slope of realised wins on predicted mean wins across teams within season. S3: randomised PIT of realised wins against the stored per-team distribution (only statistic that sees spread, hence the only one tau can move). S4: P(over) calibration at the live arm's median and +/-2 wins, same thresholds for both arms.
- Unit: team-season; resample whole seasons (Bayesian bootstrap, 10,000 draws, seed 20261108), paired live vs arm.
- Status: SECONDARY. Not in M2's pass rule (a third decision statistic would raise the family false-pass rate from about 27% to 34%). Promotion only by dated amendment.
- Prediction: tau widens the distribution and leaves mean wins unchanged to first order; S2/S4 move < 0.1 win, S3 moves measurably, most at preseason. Falsifier (overrides S3 gains, arm not scored): any team's mean wins shifting by more than 0.25 wins.
- MDM: DeepSeek's rough figures (NBA about +/-1.0 win on S2, AFL about +/-0.5) are placeholders; Claude replaces them with realised sd and the null live-vs-live spread from the run.
- Fields to add to each replay (new columns only, existing columns untouched): team, gp, w_mean, w_sd, w_q05, w_q25, w_q50, w_q75, w_q95, w_hist (compact string 0..G), y_wins. Claude confirmed: replay_afl.py saves none of w_mean/wins_hist today (simulate returns them); replay_nba.py saves only mean_wins (win_dist unsaved). To be added BEFORE the AFL grid run.
